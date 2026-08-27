"""
Калибровка гиперспектрального куба: тёмный кадр, белый эталон,
коррекция столба воды.

Тот же метрологический принцип, что и в Фазе 2 color_fish_analyzer.py
(CLAUDE.md), обобщённый с 6 каналов AS7262 на произвольное число
спектральных каналов HSI-камеры (обычно 100-300).

Научные источники:
- Mobley, C.D. (1994) "Light and Water: Radiative Transfer in Natural
  Waters", Academic Press
- Pope, R.M. & Fry, E.S. (1997) "Absorption spectrum (380-700 nm) of
  pure water. II. Integrating cavity measurements", Applied Optics
  36(33):8710
- Labsphere/Edmund Optics технические данные по эталонам Spectralon
  (метод отношений для калибровки отражательной способности)
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class HyperspectralCube:
    """
    Гиперспектральный куб данных.

    Attributes:
        data: Массив (высота, ширина, число_каналов) - интенсивность
            или отражательная способность по каждому каналу.
        wavelengths_nm: Список длин волн для каждого канала (нм),
            той же длины, что и последняя ось data.
        depth_m: Глубина съёмки (м), для коррекции столба воды.
    """

    data: np.ndarray
    wavelengths_nm: List[float]
    depth_m: float = 0.0

    def __post_init__(self) -> None:
        if self.data.shape[-1] != len(self.wavelengths_nm):
            raise ValueError(
                "Число каналов data (%d) не совпадает с числом длин "
                "волн (%d)" % (self.data.shape[-1], len(self.wavelengths_nm))
            )

    def band_index(self, wavelength_nm: float) -> int:
        """Индекс канала, ближайшего к заданной длине волны (нм)."""
        diffs = [abs(w - wavelength_nm) for w in self.wavelengths_nm]
        return diffs.index(min(diffs))

    def band(self, wavelength_nm: float) -> np.ndarray:
        """2D-срез куба (высота, ширина) для ближайшего канала к λ."""
        return self.data[:, :, self.band_index(wavelength_nm)]


class HSICalibrator:
    """
    Радиометрическая калибровка гиперспектрального куба.

    Порядок коррекций: тёмный кадр -> белый эталон (отражательная
    способность) -> столб воды (истинный спектр объекта на дне).
    """

    # Литературные "якорные" коэффициенты поглощения воды (1/м) на тех
    # же 6 длинах волн, что и WATER_ABSORPTION_COEF в Фазе 1
    # color_fish_analyzer.py (Mobley 1994, Pope & Fry 1997). Между
    # якорями коэффициент для произвольной длины волны HSI-камеры
    # получается линейной интерполяцией - это ГРУБАЯ оценка по
    # умолчанию (форма кривой верна, абсолютные значения зависят от
    # мутности/CDOM конкретной акватории, см. CLAUDE.md §2), требующая
    # замены через calibrate_water_column() для конкретного места
    # работы.
    _ANCHOR_WAVELENGTHS_NM = [450, 500, 550, 570, 600, 650]
    _ANCHOR_ABSORPTION_COEF = [0.0196, 0.0257, 0.0638, 0.0890, 0.2400, 0.3490]

    def __init__(self) -> None:
        self._dark_reference: Optional[np.ndarray] = None
        self._white_reference: Optional[np.ndarray] = None
        self._white_reflectance: Optional[np.ndarray] = None
        self._calibrated_absorption_coef: Optional[Dict[float, float]] = None

    def set_dark_reference(self, dark_frame: np.ndarray) -> None:
        """
        Установка тёмного кадра (факт 11).

        Снимается с закрытой крышкой объектива перед погружением, чтобы
        вычесть температурный шум матрицы (Dark Current).

        Args:
            dark_frame: Куб/кадр, снятый в темноте, той же формы, что
                и рабочие измерения (высота, ширина, каналы) либо
                усреднённый спектр (каналы,).
        """
        self._dark_reference = np.asarray(dark_frame, dtype=np.float64)

    def subtract_dark_current(self, cube_data: np.ndarray) -> np.ndarray:
        """
        Вычитание тёмного тока из сырых данных.

        Args:
            cube_data: Сырой куб (высота, ширина, каналы).

        Returns:
            Куб после вычитания тёмного кадра, отрицательные значения
            обрезаются до 0 (нефизичны).

        Raises:
            RuntimeError: если тёмный кадр не установлен.
        """
        if self._dark_reference is None:
            raise RuntimeError(
                "Тёмный кадр не установлен: вызовите "
                "set_dark_reference() перед калибровкой."
            )
        corrected = cube_data.astype(np.float64) - self._dark_reference
        return np.clip(corrected, 0.0, None)

    def calibrate_white_reference(
        self,
        white_frame: np.ndarray,
        reference_reflectance: float = 0.99
    ) -> None:
        """
        Калибровка по эталонной мишени (метод отношений, факт 10).

        Тефлоновая (Spectralon-подобная) белая мишень снимается на той
        же глубине перед основной съёмкой. Отражательная способность
        произвольного пикселя далее вычисляется как отношение его
        интенсивности к интенсивности эталона.

        Args:
            white_frame: Куб/спектр эталона, УЖЕ после вычитания
                тёмного кадра (subtract_dark_current).
            reference_reflectance: Известная отражательная способность
                эталона (0-1), обычно 0.99 для белого Spectralon.
        """
        self._white_reference = np.asarray(white_frame, dtype=np.float64)
        self._white_reflectance = reference_reflectance

    @property
    def is_white_calibrated(self) -> bool:
        """Признак наличия калибровки по эталонной мишени."""
        return self._white_reference is not None

    def apply_white_reference(self, cube_data: np.ndarray) -> np.ndarray:
        """
        Нормализация в относительную отражательную способность.

        Args:
            cube_data: Куб после вычитания тёмного тока.

        Returns:
            Куб отражательной способности (0-1 по каждому каналу).

        Raises:
            RuntimeError: если калибровка по эталону не выполнена.
        """
        if not self.is_white_calibrated:
            raise RuntimeError(
                "Калибровка по эталонной мишени не выполнена: "
                "вызовите calibrate_white_reference()."
            )
        white = np.where(self._white_reference > 0, self._white_reference, 1.0)
        return (cube_data / white) * self._white_reflectance

    def _interpolated_default_coef(self, wavelength_nm: float) -> float:
        """Линейная интерполяция литературного коэффициента (1/м)."""
        return float(
            np.interp(
                wavelength_nm,
                self._ANCHOR_WAVELENGTHS_NM,
                self._ANCHOR_ABSORPTION_COEF,
            )
        )

    def correct_water_column(
        self,
        reflectance_cube: np.ndarray,
        wavelengths_nm: List[float],
        depth_m: float,
    ) -> np.ndarray:
        """
        Коррекция столба воды по закону Бера-Ламберта (факты 25-26).

        Формула по каждому каналу: R_corrected = R_measured * exp(2*α*d)
        Множитель 2 - двойной путь света (источник -> дно -> объектив).

        Использует калиброванные по месту коэффициенты, если доступны
        (см. calibrate_water_column()), иначе - грубую литературную
        интерполяцию по умолчанию.

        Args:
            reflectance_cube: Куб отражательной способности (высота,
                ширина, каналы).
            wavelengths_nm: Длины волн каналов (нм).
            depth_m: Глубина съёмки (м).

        Returns:
            Скорректированный куб (истинный спектр дна/объекта).
        """
        if depth_m <= 0:
            return reflectance_cube.copy()

        factors = np.empty(len(wavelengths_nm), dtype=np.float64)
        for i, wl in enumerate(wavelengths_nm):
            if self._calibrated_absorption_coef is not None:
                alpha = self._calibrated_absorption_coef.get(
                    wl, self._interpolated_default_coef(wl)
                )
            else:
                alpha = self._interpolated_default_coef(wl)
            factors[i] = math.exp(2 * alpha * depth_m)

        return reflectance_cube * factors

    def calibrate_water_column(
        self,
        reference_measurements: List[tuple],
        wavelengths_nm: List[float],
    ) -> Dict[float, float]:
        """
        Эмпирическая калибровка коэффициентов поглощения по месту.

        Обобщение calibrate_absorption() из Фазы 1 color_fish_analyzer.py
        на произвольное число каналов HSI-камеры: измерить один и тот же
        эталонный объект на нескольких известных глубинах, найти
        коэффициент методом наименьших квадратов из линеаризованной
        модели ln(I(d)) = ln(I0) - 2*alpha*d.

        Args:
            reference_measurements: Список (глубина_м, спектр) - спектр
                это список интенсивностей той же длины, что и
                wavelengths_nm.
            wavelengths_nm: Длины волн каналов (нм).

        Returns:
            Словарь {длина_волны_нм: коэффициент_поглощения_1/м}.

        Raises:
            ValueError: если передано менее 2 измерений.
        """
        if len(reference_measurements) < 2:
            raise ValueError(
                "Нужно минимум 2 измерения на разных глубинах, "
                "получено: %d" % len(reference_measurements)
            )

        calibrated: Dict[float, float] = {}

        for band_idx, wl in enumerate(wavelengths_nm):
            depths = []
            log_intensities = []

            for depth_m, spectrum in reference_measurements:
                value = spectrum[band_idx]
                if value > 0:
                    depths.append(depth_m)
                    log_intensities.append(math.log(value))

            if len(depths) < 2:
                calibrated[wl] = self._interpolated_default_coef(wl)
                continue

            n = len(depths)
            mean_d = sum(depths) / n
            mean_ln_i = sum(log_intensities) / n

            numerator = sum(
                (d - mean_d) * (ln_i - mean_ln_i)
                for d, ln_i in zip(depths, log_intensities)
            )
            denominator = sum((d - mean_d) ** 2 for d in depths)

            if denominator == 0:
                calibrated[wl] = self._interpolated_default_coef(wl)
                continue

            slope = numerator / denominator  # = -2 * alpha
            calibrated[wl] = max(0.0, -slope / 2.0)

        self._calibrated_absorption_coef = calibrated
        return calibrated

    @property
    def is_water_column_calibrated(self) -> bool:
        """Признак использования калиброванных (не литературных)
        коэффициентов поглощения воды."""
        return self._calibrated_absorption_coef is not None
