"""
Спектральный анализ гиперспектрального куба: классификация материалов,
индексы деградации.

Научные источники:
- Kruse, F.A. et al. (1993) "The spectral image processing system
  (SIPS) - interactive visualization and analysis of imaging spectrometer
  data", Remote Sensing of Environment 44(2-3):145-163 - алгоритм
  Spectral Angle Mapper (SAM), используется как основной метод
  попиксельной классификации в этом модуле.
- Johnsen, M.G. et al. (2018) "Underwater hyperspectral imaging: a new
  tool for marine archaeology", Applied Optics 57(12):3214 - применение
  UHI для идентификации материалов на объектах подводной археологии.

Правило проекта (CLAUDE.md §2): числовые спектральные кривые
("endmembers") ниже - ИЛЛЮСТРАТИВНЫЕ заготовки для структуры библиотеки,
основанные на качественных признаках из литературы (положения пиков
поглощения), а НЕ откалиброванные лабораторные измерения. Перед боевым
использованием должны быть заменены реальными измерениями чистых
образцов на месте (Endmembers, см. `SpectralLibrary.load_measured`).
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


def spectral_angle(
    test_spectrum: np.ndarray,
    reference_spectrum: np.ndarray,
) -> float:
    """
    Spectral Angle Mapper (SAM) - угол между двумя спектрами.

    Оба спектра рассматриваются как векторы в n-мерном пространстве
    (n = число каналов). Угол между ними инвариантен к освещённости
    (умножению на константу), что делает SAM устойчивым к неравномерной
    подсветке дна.

    Формула: θ = arccos( (t · r) / (|t| * |r|) )

    Args:
        test_spectrum: Спектр исследуемого пикселя (n,).
        reference_spectrum: Эталонный спектр материала (n,).

    Returns:
        Угол в радианах (0 = идеальное совпадение, π/2 = максимальное
        расхождение).
    """
    t = np.asarray(test_spectrum, dtype=np.float64)
    r = np.asarray(reference_spectrum, dtype=np.float64)

    norm_t = np.linalg.norm(t)
    norm_r = np.linalg.norm(r)

    if norm_t == 0 or norm_r == 0:
        return math.pi / 2  # неопределено - максимальное расхождение

    cos_theta = np.dot(t, r) / (norm_t * norm_r)
    cos_theta = min(1.0, max(-1.0, cos_theta))  # защита от ошибок округления
    return math.acos(cos_theta)


@dataclass
class SpectralLibrary:
    """
    Библиотека эталонных спектров (endmembers) для классификации.

    Attributes:
        wavelengths_nm: Длины волн, на которых заданы эталонные спектры.
        endmembers: Словарь {название_материала: спектр (той же длины,
            что wavelengths_nm)}.
    """

    wavelengths_nm: List[float]
    endmembers: Dict[str, np.ndarray]

    @classmethod
    def seed_illustrative_library(
        cls,
        wavelengths_nm: List[float]
    ) -> "SpectralLibrary":
        """
        Иллюстративная библиотека-заготовка на основе качественных
        признаков из литературы (положения пиков/провалов поглощения).

        НЕ является метрологически калиброванной библиотекой. Каждая
        кривая построена как гладкий базовый спектр с локальными
        провалами/пиками поглощения в задокументированных положениях
        (см. докстринги ниже), интерполированный на wavelengths_nm
        камеры. Использовать для проверки работоспособности пайплайна
        SAM-классификации и как отправную точку для замены реальными
        измерениями через load_measured().

        Args:
            wavelengths_nm: Длины волн каналов конкретной камеры.

        Returns:
            SpectralLibrary с иллюстративными эталонами.
        """
        wl = np.asarray(wavelengths_nm, dtype=np.float64)
        endmembers: Dict[str, np.ndarray] = {}

        # Здоровая древесина: ровный (пологий) спектр отражения
        # (факт 8: "здоровая древняя древесина имеет ровный спектр").
        endmembers['oak_wood_healthy'] = 0.35 + 0.05 * (wl - wl.min()) / (
            wl.max() - wl.min() + 1e-9
        )

        # Гниющая древесина: резкие провалы в зонах поглощения
        # целлюлозы/лигнина (факт 8); упрощённо - локальный провал
        # около 600-650 нм (факт 14 - индекс деградации использует
        # именно эту пару).
        endmembers['oak_wood_degraded'] = endmembers[
            'oak_wood_healthy'
        ] - 0.15 * np.exp(-((wl - 620) ** 2) / (2 * 25 ** 2))

        # Оксид железа (ржавчина): пики поглощения на 850 и 900 нм
        # (факт 17).
        base_iron = 0.4 - 0.1 * np.exp(-((wl - 850) ** 2) / (2 * 20 ** 2))
        base_iron = base_iron - 0.1 * np.exp(-((wl - 900) ** 2) / (2 * 20 ** 2))
        endmembers['iron_oxide_rust'] = base_iron

        # Хлорофилл-а (биообрастание): два пика поглощения, 430 и
        # 662 нм (факт 7).
        base_chl = 0.5 - 0.2 * np.exp(-((wl - 430) ** 2) / (2 * 15 ** 2))
        base_chl = base_chl - 0.25 * np.exp(-((wl - 662) ** 2) / (2 * 15 ** 2))
        endmembers['chlorophyll_biofouling'] = base_chl

        # Песок/ил: близкий к нейтральному, слабо растущий к красному
        # спектру (типичное поведение минерального осадка).
        endmembers['sand_silt'] = 0.45 + 0.02 * (wl - wl.min()) / (
            wl.max() - wl.min() + 1e-9
        )

        return cls(wavelengths_nm=wavelengths_nm, endmembers=endmembers)

    def load_measured(self, name: str, spectrum: np.ndarray) -> None:
        """
        Замена/добавление эталона реальным измерением (calibrate-over-
        hardcode, CLAUDE.md §2).

        Args:
            name: Название материала.
            spectrum: Реально измеренный спектр той же длины, что
                wavelengths_nm.
        """
        spectrum = np.asarray(spectrum, dtype=np.float64)
        if len(spectrum) != len(self.wavelengths_nm):
            raise ValueError(
                "Длина спектра (%d) не совпадает с числом каналов "
                "библиотеки (%d)" % (len(spectrum), len(self.wavelengths_nm))
            )
        self.endmembers[name] = spectrum

    def resample_to(self, target_wavelengths_nm: List[float]) -> "SpectralLibrary":
        """
        Пересчёт (линейная интерполяция) эталонов на другую сетку длин
        волн - для случая, когда библиотека и камера используют разные
        спектральные каналы.

        Args:
            target_wavelengths_nm: Целевые длины волн.

        Returns:
            Новая SpectralLibrary на целевой сетке.
        """
        resampled = {
            name: np.interp(target_wavelengths_nm, self.wavelengths_nm, spectrum)
            for name, spectrum in self.endmembers.items()
        }
        return SpectralLibrary(
            wavelengths_nm=target_wavelengths_nm, endmembers=resampled
        )


class SpectralAnalyzer:
    """Классификация пикселей/куба по спектральной библиотеке и расчёт
    диагностических индексов."""

    def classify_pixel(
        self,
        pixel_spectrum: np.ndarray,
        library: SpectralLibrary,
    ) -> Tuple[str, float]:
        """
        Классификация одного пикселя методом SAM.

        Args:
            pixel_spectrum: Спектр пикселя, на той же сетке длин волн,
                что и library.wavelengths_nm.
            library: Спектральная библиотека эталонов.

        Returns:
            (название_материала_с_минимальным_углом, угол_в_радианах).
        """
        best_name: Optional[str] = None
        best_angle = math.inf

        for name, reference in library.endmembers.items():
            angle = spectral_angle(pixel_spectrum, reference)
            if angle < best_angle:
                best_angle = angle
                best_name = name

        return best_name, best_angle

    def classify_cube(
        self,
        cube_data: np.ndarray,
        library: SpectralLibrary,
        max_angle_rad: float = 0.35,
    ) -> Dict[str, np.ndarray]:
        """
        Попиксельная SAM-классификация всего куба.

        Args:
            cube_data: Куб отражательной способности (высота, ширина,
                каналы), той же спектральной сетки, что и library.
            library: Спектральная библиотека эталонов.
            max_angle_rad: Порог отсечения (пиксели с углом выше порога
                до ВСЕХ эталонов помечаются как "unknown" - нет
                достаточно похожего материала в библиотеке).

        Returns:
            Словарь с картой классов ('class_map': массив строк той же
            формы высота x ширина) и картой углов ('angle_map': float).
        """
        height, width, _ = cube_data.shape
        class_map = np.full((height, width), 'unknown', dtype=object)
        angle_map = np.full((height, width), math.pi / 2, dtype=np.float64)

        for y in range(height):
            for x in range(width):
                name, angle = self.classify_pixel(cube_data[y, x, :], library)
                angle_map[y, x] = angle
                if angle <= max_angle_rad:
                    class_map[y, x] = name

        return {'class_map': class_map, 'angle_map': angle_map}

    @staticmethod
    def degradation_index(
        spectrum: np.ndarray,
        wavelengths_nm: List[float],
        band_a_nm: float = 600.0,
        band_b_nm: float = 500.0,
    ) -> float:
        """
        Индекс деградации лигнина в древесине (факт 14).

        Отношение отражения на band_a_nm (по умолчанию 600 нм) к
        отражению на band_b_nm (по умолчанию 500 нм). Более высокое
        значение соответствует более выраженной деградации лигнина в
        дубовых шпангоутах (согласно предметному описанию задачи;
        точный порог "здорово/разрушено" требует калибровки по
        образцам известного возраста на конкретном объекте - тот же
        принцип, что и в остальных методах проекта).

        Args:
            spectrum: Спектр пикселя.
            wavelengths_nm: Длины волн каналов.
            band_a_nm: Числитель отношения (нм).
            band_b_nm: Знаменатель отношения (нм).

        Returns:
            Безразмерное отношение отражения (band_a / band_b).
        """
        idx_a = int(np.argmin(np.abs(np.asarray(wavelengths_nm) - band_a_nm)))
        idx_b = int(np.argmin(np.abs(np.asarray(wavelengths_nm) - band_b_nm)))

        value_b = spectrum[idx_b]
        if value_b == 0:
            return math.inf
        return float(spectrum[idx_a] / value_b)

    @staticmethod
    def spectral_derivative(
        spectrum: np.ndarray,
        wavelengths_nm: List[float],
    ) -> np.ndarray:
        """
        Первая производная спектра по длине волны (факт 74).

        Помогает выявить скрытые пики поглощения, незаметные на графике
        самого отражения (наклон меняется резче, чем абсолютный
        уровень).

        Args:
            spectrum: Спектр пикселя (n,).
            wavelengths_nm: Длины волн каналов (n,).

        Returns:
            Производная dR/dλ (n-1,).
        """
        spectrum = np.asarray(spectrum, dtype=np.float64)
        wl = np.asarray(wavelengths_nm, dtype=np.float64)
        return np.diff(spectrum) / np.diff(wl)
