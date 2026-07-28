"""
Модуль анализа цвета чешуи рыб и подводных объектов.

Использует 6-канальный спектральный датчик AS7262 для измерения
спектральной отражательной способности в видимом диапазоне (450-650 нм).

Научные методы:
- Преобразование спектра в CIE L*a*b* и RGB цветовые пространства
- Анализ свежести по насыщенности цвета (метод TVB-N корреляции)
- Классификация цвета по доминирующей длине волны
- Коррекция поглощения света водой на глубине (Beer-Lambert law)
- Компенсация иридесценции чешуи (усреднение по углам)

Иридесценция чешуи рыб:
- Вызвана многослойной структурой кристаллов гуанина
- Цвет зависит от угла наблюдения (интерференция тонких плёнок)
- Рекомендуется усреднение нескольких измерений под разными углами

Ссылки:
- https://www.sciencedirect.com/science/article/pii/S2772753X22001174
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9265959/
- Denton, E.J. (1970) "On the organization of reflecting surfaces in some
  marine animals" Phil. Trans. R. Soc. Lond. B 258:285-313
- Mobley, C.D. (1994) "Light and Water: Radiative Transfer in Natural
  Waters", Academic Press
- Pope, R.M. & Fry, E.S. (1997) "Absorption spectrum (380-700 nm) of pure
  water. II. Integrating cavity measurements", Applied Optics 36(33):8710
- Solonenko, M.G. & Mobley, C.D. (2015) "Inherent optical properties of
  Jerlov water types", Applied Optics 54(17):5392-5401, PMID:26192839
- Gur, D. et al. (2013) "Guanine-Based Photonic Crystals in Fish Scales
  Form from an Amorphous Precursor", Angew. Chem. Int. Ed. 52(1):388-391,
  PMID:22951999
- Funt, N. et al. (2017) "Koi Fish-Scale Iridophore Cells Orient Guanine
  Crystals to Maximize Light Reflection", ChemPlusChem, PMID:31961575

Правила проекта (обязательный научный источник, эвристика выбора решений,
12-фазный HLD-план) — см. CLAUDE.md.
"""

import json
import math
import struct
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import smbus

# =============================================================================
# Константы датчика AS7262
# =============================================================================

AS7262_I2C_ADDRESS = 0x49
REG_STATUS = 0x00
REG_WRITE = 0x01
REG_READ = 0x02

# Виртуальные регистры AS7262
DEVICE_CONTROL = 0x04
INTEGRATION_TIME = 0x05
DEVICE_TEMP = 0x06
LED_CONTROL = 0x07

# Регистры калиброванных данных (float32)
CAL_VIOLET = 0x14  # 450 нм
CAL_BLUE = 0x18    # 500 нм
CAL_GREEN = 0x1C   # 550 нм
CAL_YELLOW = 0x20  # 570 нм
CAL_ORANGE = 0x24  # 600 нм
CAL_RED = 0x28     # 650 нм

# Спектральные каналы AS7262 с длинами волн (нм) и FWHM ±40нм
CHANNELS = {
    'violet': {'wavelength': 450, 'fwhm': 40, 'cal_reg': CAL_VIOLET},
    'blue': {'wavelength': 500, 'fwhm': 40, 'cal_reg': CAL_BLUE},
    'green': {'wavelength': 550, 'fwhm': 40, 'cal_reg': CAL_GREEN},
    'yellow': {'wavelength': 570, 'fwhm': 40, 'cal_reg': CAL_YELLOW},
    'orange': {'wavelength': 600, 'fwhm': 40, 'cal_reg': CAL_ORANGE},
    'red': {'wavelength': 650, 'fwhm': 40, 'cal_reg': CAL_RED},
}

# Уровни усиления
GAIN_1X = 0b00
GAIN_3_7X = 0b01
GAIN_16X = 0b10
GAIN_64X = 0b11


class AS7262Sensor:
    """
    Драйвер для 6-канального спектрального датчика AS7262.

    Датчик измеряет спектральную интенсивность в 6 каналах видимого
    диапазона: 450, 500, 550, 570, 600, 650 нм (±40 нм FWHM).

    Attributes:
        bus: Объект I2C шины SMBus.
        address: I2C адрес датчика (по умолчанию 0x49).
        integration_time: Время интеграции в мс (2.8-714 мс).
        gain: Уровень усиления (1x, 3.7x, 16x, 64x).
    """

    def __init__(
        self,
        bus_number: int = 1,
        address: int = AS7262_I2C_ADDRESS,
        integration_time: int = 50,
        gain: int = GAIN_3_7X
    ):
        """
        Инициализация датчика AS7262.

        Args:
            bus_number: Номер I2C шины (1 для Raspberry Pi).
            address: I2C адрес датчика.
            integration_time: Время интеграции в единицах 2.8 мс (1-255).
            gain: Уровень усиления (GAIN_1X, GAIN_3_7X, GAIN_16X, GAIN_64X).
        """
        self.bus = smbus.SMBus(bus_number)
        self.address = address
        self._integration_time = integration_time
        self._gain = gain
        self._configure()

    def _write_virtual_reg(self, reg: int, value: int) -> None:
        """Запись в виртуальный регистр через I2C."""
        while True:
            status = self.bus.read_byte_data(self.address, REG_STATUS)
            if (status & 0x02) == 0:  # TX buffer empty
                break
            time.sleep(0.001)

        self.bus.write_byte_data(self.address, REG_WRITE, reg | 0x80)

        while True:
            status = self.bus.read_byte_data(self.address, REG_STATUS)
            if (status & 0x02) == 0:
                break
            time.sleep(0.001)

        self.bus.write_byte_data(self.address, REG_WRITE, value)

    def _read_virtual_reg(self, reg: int) -> int:
        """Чтение из виртуального регистра через I2C."""
        while True:
            status = self.bus.read_byte_data(self.address, REG_STATUS)
            if (status & 0x02) == 0:
                break
            time.sleep(0.001)

        self.bus.write_byte_data(self.address, REG_WRITE, reg)

        while True:
            status = self.bus.read_byte_data(self.address, REG_STATUS)
            if (status & 0x01) != 0:  # RX data ready
                break
            time.sleep(0.001)

        return self.bus.read_byte_data(self.address, REG_READ)

    def _configure(self) -> None:
        """Начальная конфигурация датчика."""
        self._write_virtual_reg(INTEGRATION_TIME, self._integration_time)
        control = (self._gain << 4) | 0x03  # Gain + Mode 3 (все каналы)
        self._write_virtual_reg(DEVICE_CONTROL, control)

    def set_led(self, current_ma: int = 0) -> None:
        """
        Управление встроенным LED для подсветки.

        Args:
            current_ma: Ток LED в мА (0, 12.5, 25, 50, 100).
        """
        led_map = {0: 0, 12: 1, 25: 2, 50: 3, 100: 4}
        closest = min(led_map.keys(), key=lambda x: abs(x - current_ma))
        led_value = led_map[closest]
        self._write_virtual_reg(LED_CONTROL, (led_value << 4) | 0x08)

    def read_calibrated(self) -> Dict[str, float]:
        """
        Чтение калиброванных значений со всех 6 каналов.

        Returns:
            Словарь {название_канала: калиброванное_значение}.
            Значения в единицах μW/cm².
        """
        # Запуск однократного измерения
        control = self._read_virtual_reg(DEVICE_CONTROL)
        control = (control & 0xFC) | 0x0C  # Mode 3, одноразовый
        self._write_virtual_reg(DEVICE_CONTROL, control)

        # Ожидание готовности данных
        while True:
            status = self._read_virtual_reg(DEVICE_CONTROL)
            if status & 0x02:  # Data ready
                break
            time.sleep(0.01)

        # Чтение калиброванных float32 значений
        result = {}
        for name, info in CHANNELS.items():
            raw_bytes = []
            for i in range(4):
                raw_bytes.append(self._read_virtual_reg(info['cal_reg'] + i))
            value = struct.unpack('>f', bytes(raw_bytes))[0]
            result[name] = value

        return result

    def get_temperature(self) -> int:
        """Чтение температуры датчика в °C."""
        return self._read_virtual_reg(DEVICE_TEMP)


class ColorAnalyzer:
    """
    Анализатор цвета на основе спектральных данных.

    Реализует научные методы анализа цвета:
    - Преобразование спектра в RGB и CIE L*a*b*
    - Расчёт индекса свежести рыбы по спектральным характеристикам
    - Классификация цвета подводных объектов

    Методы основаны на исследованиях:
    - Colorimetric analysis with ANN (ScienceDirect, 2022)
    - Spectral freshness assessment (PMC, 2022)
    """

    # Коэффициенты для преобразования спектра AS7262 в XYZ
    # Аппроксимация на основе CIE 1931 цветовых функций
    SPECTRUM_TO_XYZ = {
        'violet': {'x': 0.3639, 'y': 0.0403, 'z': 1.7826},
        'blue': {'x': 0.0049, 'y': 0.3230, 'z': 0.2720},
        'green': {'x': 0.4334, 'y': 0.9950, 'z': 0.0087},
        'yellow': {'x': 0.7621, 'y': 0.9520, 'z': 0.0021},
        'orange': {'x': 1.0263, 'y': 0.6310, 'z': 0.0008},
        'red': {'x': 0.2835, 'y': 0.1070, 'z': 0.0000},
    }

    # Пороги для классификации свежести рыбы
    # На основе корреляции с TVB-N (Total Volatile Basic Nitrogen)
    FRESHNESS_THRESHOLDS = {
        'fresh': {'saturation_min': 0.6, 'brightness_min': 0.4},
        'acceptable': {'saturation_min': 0.4, 'brightness_min': 0.3},
        'spoiled': {'saturation_min': 0.0, 'brightness_min': 0.0},
    }

    # Коэффициенты поглощения света водой (1/м) по длинам волн.
    #
    # ЛИТЕРАТУРНЫЕ ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ (не для точных измерений!):
    # порядок величины и относительное соотношение каналов взяты из
    # общепринятых океанографических источников:
    # - Mobley, C.D. (1994) "Light and Water: Radiative Transfer in
    #   Natural Waters", Academic Press - спектральная форма поглощения
    #   в видимом диапазоне (красный поглощается на порядок сильнее синего).
    # - Pope, R.M. & Fry, E.S. (1997) "Absorption spectrum (380-700 nm)
    #   of pure water. II. Integrating cavity measurements",
    #   Applied Optics 36(33):8710-8723 - эталонный спектр чистой воды.
    # - Solonenko, M.G. & Mobley, C.D. (2015) "Inherent optical properties
    #   of Jerlov water types", Applied Optics 54(17):5392-5401, PMID:26192839
    #   - коэффициенты сильно зависят от типа воды (Jerlov I/IA/IB/II/III
    #     для океана, 1-9 для прибрежных вод); табличные константы одного
    #     типа воды НЕ применимы ко всем акваториям.
    #
    # Согласно правилу проекта (CLAUDE.md, раздел 2) эти значения — только
    # fallback. Для полевой работы использовать calibrate_absorption()
    # с эталонной мишенью на известных глубинах в месте эксплуатации.
    WATER_ABSORPTION_COEF = {
        'violet': 0.0196,  # 450 нм - минимальное поглощение
        'blue': 0.0257,    # 500 нм
        'green': 0.0638,   # 550 нм
        'yellow': 0.0890,  # 570 нм
        'orange': 0.2400,  # 600 нм - значительное поглощение
        'red': 0.3490,     # 650 нм - максимальное поглощение
    }

    # Параметры иридесценции чешуи (многослойные кристаллы гуанина).
    #
    # Научное обоснование механизма (не даёт числовых порогов, но
    # обосновывает необходимость многоугловых измерений):
    # - Gur, D. et al. (2013) "Guanine-Based Photonic Crystals in Fish
    #   Scales Form from an Amorphous Precursor", Angew. Chem. Int. Ed.
    #   52(1):388-391, PMID:22951999 - многослойные кристаллы гуанина
    #   создают интерференционные цвета, зависящие от угла падения света.
    # - Funt, N. et al. (2017) "Koi Fish-Scale Iridophore Cells Orient
    #   Guanine Crystals to Maximize Light Reflection", ChemPlusChem,
    #   PMID:31961575 - >95% кристаллов ориентированы параллельно
    #   поверхности чешуи; положение и интенсивность интерференционного
    #   пика зависят от угла наклона и межслойного расстояния кристаллов.
    #
    # Число измерений для усреднения выбрано инженерно (компромисс между
    # подавлением угловой дисперсии и временем цикла измерения), а не из
    # конкретной статьи - см. calibrate_iridescence_samples() для
    # эмпирической настройки под конкретный вид/датчик.
    IRIDESCENCE_MIN_SAMPLES = 3
    IRIDESCENCE_OPTIMAL_SAMPLES = 5

    def __init__(self) -> None:
        """Инициализация анализатора с пустой калибровкой поглощения."""
        # Если задано (через calibrate_absorption), заменяет
        # WATER_ABSORPTION_COEF реальными измеренными коэффициентами.
        self._calibrated_absorption_coef: Optional[Dict[str, float]] = None

    def spectrum_to_xyz(
        self,
        spectrum: Dict[str, float]
    ) -> Tuple[float, float, float]:
        """
        Преобразование спектра в CIE XYZ цветовое пространство.

        Args:
            spectrum: Словарь спектральных значений от датчика.

        Returns:
            Кортеж (X, Y, Z) координат.
        """
        x_sum = y_sum = z_sum = 0.0

        for channel, value in spectrum.items():
            if channel in self.SPECTRUM_TO_XYZ:
                coef = self.SPECTRUM_TO_XYZ[channel]
                x_sum += value * coef['x']
                y_sum += value * coef['y']
                z_sum += value * coef['z']

        return (x_sum, y_sum, z_sum)

    def xyz_to_lab(
        self,
        xyz: Tuple[float, float, float],
        illuminant: str = 'D65'
    ) -> Tuple[float, float, float]:
        """
        Преобразование XYZ в CIE L*a*b* цветовое пространство.

        Args:
            xyz: Кортеж (X, Y, Z) координат.
            illuminant: Тип освещения ('D65' для дневного света).

        Returns:
            Кортеж (L*, a*, b*) координат.
        """
        # Референсные значения белой точки D65
        ref_white = {'D65': (95.047, 100.0, 108.883)}
        xn, yn, zn = ref_white.get(illuminant, ref_white['D65'])

        x_r, y_r, z_r = xyz[0] / xn, xyz[1] / yn, xyz[2] / zn

        def f(t: float) -> float:
            delta = 6 / 29
            if t > delta ** 3:
                return t ** (1 / 3)
            return t / (3 * delta ** 2) + 4 / 29

        l_star = 116 * f(y_r) - 16
        a_star = 500 * (f(x_r) - f(y_r))
        b_star = 200 * (f(y_r) - f(z_r))

        return (l_star, a_star, b_star)

    def spectrum_to_rgb(
        self,
        spectrum: Dict[str, float]
    ) -> Tuple[int, int, int]:
        """
        Преобразование спектра в sRGB значения.

        Использует аппроксимированное отображение 6 спектральных
        каналов на RGB компоненты.

        Args:
            spectrum: Словарь спектральных значений.

        Returns:
            Кортеж (R, G, B) в диапазоне 0-255.
        """
        # Взвешенное суммирование каналов
        r = (
            spectrum.get('red', 0) * 1.0 +
            spectrum.get('orange', 0) * 0.5
        )
        g = (
            spectrum.get('green', 0) * 1.0 +
            spectrum.get('yellow', 0) * 0.5
        )
        b = (
            spectrum.get('blue', 0) * 1.0 +
            spectrum.get('violet', 0) * 0.8
        )

        # Нормализация
        max_val = max(r, g, b, 0.001)
        r, g, b = r / max_val, g / max_val, b / max_val

        # Гамма-коррекция sRGB
        def gamma(c: float) -> int:
            if c <= 0.0031308:
                c = 12.92 * c
            else:
                c = 1.055 * (c ** (1 / 2.4)) - 0.055
            return max(0, min(255, int(c * 255)))

        return (gamma(r), gamma(g), gamma(b))

    def calculate_hsv(
        self,
        rgb: Tuple[int, int, int]
    ) -> Tuple[float, float, float]:
        """
        Преобразование RGB в HSV цветовое пространство.

        Args:
            rgb: Кортеж (R, G, B) в диапазоне 0-255.

        Returns:
            Кортеж (H, S, V) где H в градусах (0-360), S и V в 0-1.
        """
        r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        delta = max_c - min_c

        # Hue
        if delta == 0:
            h = 0
        elif max_c == r:
            h = 60 * (((g - b) / delta) % 6)
        elif max_c == g:
            h = 60 * ((b - r) / delta + 2)
        else:
            h = 60 * ((r - g) / delta + 4)

        # Saturation
        s = 0 if max_c == 0 else delta / max_c

        # Value
        v = max_c

        return (h, s, v)

    def classify_fish_color(
        self,
        hsv: Tuple[float, float, float]
    ) -> str:
        """
        Классификация цвета рыбы по HSV значениям.

        Использует диапазоны оттенков характерные для различных
        видов рыб и состояний свежести.

        Args:
            hsv: Кортеж (H, S, V).

        Returns:
            Название цветовой категории на русском.
        """
        h, s, v = hsv

        # Низкая насыщенность - серый/белый
        if s < 0.15:
            return "Серебристая/Белая"

        # Классификация по оттенку
        if h < 15 or h >= 345:
            return "Красная"
        elif 15 <= h < 45:
            return "Оранжевая"
        elif 45 <= h < 75:
            return "Жёлтая"
        elif 75 <= h < 165:
            return "Зелёная"
        elif 165 <= h < 195:
            return "Голубая"
        elif 195 <= h < 255:
            return "Синяя"
        elif 255 <= h < 285:
            return "Фиолетовая"
        else:
            return "Пурпурная"

    def correct_depth_absorption(
        self,
        spectrum: Dict[str, float],
        depth_m: float
    ) -> Dict[str, float]:
        """
        Коррекция спектра с учётом поглощения света водой.

        Применяет закон Бера-Ламберта для компенсации затухания
        различных длин волн на заданной глубине.

        Формула: I_corrected = I_measured * exp(α * d)
        где α - коэффициент поглощения, d - глубина (м)

        Важно: красный свет (650 нм) поглощается в ~18 раз сильнее
        чем синий (450 нм), поэтому на глубине >5м красные оттенки
        практически неразличимы без коррекции.

        Args:
            spectrum: Измеренные спектральные значения.
            depth_m: Глубина измерения в метрах.

        Returns:
            Скорректированный спектр (истинные цвета объекта).
        """
        if depth_m <= 0:
            return spectrum.copy()

        # Калиброванные по месту эксплуатации коэффициенты имеют приоритет
        # над литературными значениями по умолчанию (см. calibrate_absorption).
        coefficients = self._calibrated_absorption_coef or self.WATER_ABSORPTION_COEF

        corrected = {}
        for channel, value in spectrum.items():
            if channel in coefficients:
                alpha = coefficients[channel]
                # Коррекция по закону Бера-Ламберта
                # Учитываем двойной путь света (туда и обратно)
                correction_factor = math.exp(2 * alpha * depth_m)
                corrected[channel] = value * correction_factor
            else:
                corrected[channel] = value

        return corrected

    def calibrate_absorption(
        self,
        reference_measurements: List[Tuple[float, Dict[str, float]]]
    ) -> Dict[str, float]:
        """
        Эмпирическая калибровка коэффициентов поглощения воды по месту.

        Реализует Правило "299/48/32" проекта (CLAUDE.md, раздел 2/3):
        табличные океанографические коэффициенты (Jerlov-типы, Mobley 1994)
        сильно зависят от конкретной акватории (мутность, планктон,
        растворённое органическое вещество), поэтому вместо единственного
        "лучшего" литературного значения предусмотрена процедура измерения
        на месте — она всегда точнее любой таблицы для конкретных условий.

        Метод: измерить один и тот же эталонный объект известной
        отражательной способности (например, серую/белую мишень) на
        нескольких известных глубинах. Поглощение подчиняется закону
        Бера-Ламберта, поэтому логарифм измеренной интенсивности линейно
        убывает с глубиной:

            ln(I(d)) = ln(I0) - 2 * alpha * d

        Коэффициент alpha для каждого канала находится методом наименьших
        квадратов (линейная регрессия ln(I) от d).

        Args:
            reference_measurements: Список (глубина_м, спектр) для одного
                и того же эталонного объекта на разных глубинах.
                Минимум 2 точки, рекомендуется 4+ на разных глубинах.

        Returns:
            Словарь откалиброванных коэффициентов поглощения (1/м) по
            каналам. Также сохраняется внутри анализатора и автоматически
            используется в correct_depth_absorption().

        Raises:
            ValueError: если передано менее 2 измерений.
        """
        if len(reference_measurements) < 2:
            raise ValueError(
                "Для калибровки нужно минимум 2 измерения на разных "
                "глубинах, получено: %d" % len(reference_measurements)
            )

        channels = reference_measurements[0][1].keys()
        calibrated: Dict[str, float] = {}

        for channel in channels:
            depths = []
            log_intensities = []

            for depth_m, spectrum in reference_measurements:
                value = spectrum.get(channel, 0)
                if value > 0:
                    depths.append(depth_m)
                    log_intensities.append(math.log(value))

            if len(depths) < 2:
                # Недостаточно валидных точек для этого канала - оставляем
                # литературное значение по умолчанию без изменений.
                calibrated[channel] = self.WATER_ABSORPTION_COEF.get(
                    channel, 0.0
                )
                continue

            # Линейная регрессия методом наименьших квадратов:
            # log_intensity = intercept - 2 * alpha * depth
            n = len(depths)
            mean_d = sum(depths) / n
            mean_ln_i = sum(log_intensities) / n

            numerator = sum(
                (d - mean_d) * (ln_i - mean_ln_i)
                for d, ln_i in zip(depths, log_intensities)
            )
            denominator = sum((d - mean_d) ** 2 for d in depths)

            if denominator == 0:
                calibrated[channel] = self.WATER_ABSORPTION_COEF.get(
                    channel, 0.0
                )
                continue

            slope = numerator / denominator  # = -2 * alpha
            alpha = max(0.0, -slope / 2.0)
            calibrated[channel] = alpha

        self._calibrated_absorption_coef = calibrated
        return calibrated

    @property
    def is_absorption_calibrated(self) -> bool:
        """Признак того, что используются калиброванные, а не табличные
        коэффициенты поглощения."""
        return self._calibrated_absorption_coef is not None

    def compensate_iridescence(
        self,
        spectrum_samples: List[Dict[str, float]]
    ) -> Dict[str, Any]:
        """
        Компенсация иридесценции чешуи рыб.

        Иридесценция (переливчатость) вызвана многослойной структурой
        кристаллов гуанина в чешуе. Цвет зависит от угла наблюдения
        из-за интерференции в тонких плёнках.

        Метод: усреднение нескольких измерений под разными углами
        для получения стабильной оценки истинного цвета.

        Args:
            spectrum_samples: Список спектральных измерений
                              (минимум 3, оптимально 5+).

        Returns:
            Словарь с усреднённым спектром и метриками стабильности.
        """
        n_samples = len(spectrum_samples)

        if n_samples == 0:
            return {
                'averaged_spectrum': {},
                'stability_index': 0.0,
                'iridescence_detected': False,
                'samples_count': 0,
                'warning': 'Нет данных для анализа',
            }

        if n_samples < self.IRIDESCENCE_MIN_SAMPLES:
            return {
                'averaged_spectrum': spectrum_samples[0],
                'stability_index': 0.0,
                'iridescence_detected': False,
                'samples_count': n_samples,
                'warning': f'Недостаточно измерений ({n_samples} < {self.IRIDESCENCE_MIN_SAMPLES})',
            }

        # Вычисление среднего значения по каждому каналу
        channels = spectrum_samples[0].keys()
        averaged = {}
        std_devs = {}

        for channel in channels:
            values = [s.get(channel, 0) for s in spectrum_samples]
            mean_val = sum(values) / len(values)
            averaged[channel] = mean_val

            # Стандартное отклонение
            variance = sum((v - mean_val) ** 2 for v in values) / len(values)
            std_devs[channel] = math.sqrt(variance)

        # Индекс стабильности (обратный коэффициент вариации)
        # Высокий индекс = стабильный цвет, низкий = сильная иридесценция
        total_mean = sum(averaged.values())
        total_std = sum(std_devs.values())

        if total_mean > 0:
            cv = total_std / total_mean  # Coefficient of variation
            stability_index = max(0, 1 - cv)
        else:
            stability_index = 0.0

        # Детекция иридесценции
        # Если CV > 0.15, считаем что иридесценция значительная
        iridescence_detected = (1 - stability_index) > 0.15

        # Определение доминирующего переливающегося канала
        max_variation_channel = max(std_devs, key=std_devs.get)

        return {
            'averaged_spectrum': {k: round(v, 4) for k, v in averaged.items()},
            'stability_index': round(stability_index, 3),
            'iridescence_detected': iridescence_detected,
            'samples_count': n_samples,
            'channel_std_devs': {k: round(v, 4) for k, v in std_devs.items()},
            'max_variation_channel': max_variation_channel,
            'recommendation': (
                'Иридесценция обнаружена. Рекомендуется больше измерений.'
                if iridescence_detected and n_samples < self.IRIDESCENCE_OPTIMAL_SAMPLES
                else 'Стабильное измерение'
            ),
        }

    def assess_freshness(
        self,
        spectrum: Dict[str, float],
        lab: Tuple[float, float, float]
    ) -> Dict[str, Any]:
        """
        Оценка свежести рыбы по спектральным характеристикам.

        Метод основан на корреляции цветовых параметров с TVB-N
        (Total Volatile Basic Nitrogen) - индикатором порчи.

        Научная основа:
        - a* снижается при хранении (потеря красного)
        - b* снижается (пожелтение → посерение)
        - L* изменяется нелинейно

        Args:
            spectrum: Спектральные данные.
            lab: CIE L*a*b* координаты.

        Returns:
            Словарь с оценкой свежести и метриками.
        """
        l_star, a_star, b_star = lab

        # Индекс насыщенности цвета (chroma)
        chroma = (a_star ** 2 + b_star ** 2) ** 0.5

        # Спектральный индекс свежести
        # Отношение красного/оранжевого к синему/зелёному
        red_orange = spectrum.get('red', 0) + spectrum.get('orange', 0)
        blue_green = spectrum.get('blue', 0) + spectrum.get('green', 0)
        spectral_ratio = red_orange / (blue_green + 0.001)

        # Комплексная оценка
        freshness_score = (
            0.4 * min(chroma / 50, 1.0) +
            0.3 * min(l_star / 100, 1.0) +
            0.3 * min(spectral_ratio / 2, 1.0)
        )

        # Классификация
        if freshness_score >= 0.6:
            status = "Свежая"
            status_en = "fresh"
        elif freshness_score >= 0.4:
            status = "Допустимая"
            status_en = "acceptable"
        else:
            status = "Несвежая"
            status_en = "spoiled"

        return {
            'status': status,
            'status_en': status_en,
            'score': round(freshness_score, 3),
            'chroma': round(chroma, 2),
            'spectral_ratio': round(spectral_ratio, 3),
            'l_star': round(l_star, 2),
        }


class FishColorAnalyzer:
    """
    Комплексный анализатор цвета рыб для BlueOS/подводных систем.

    Объединяет работу с датчиком AS7262 и алгоритмы анализа цвета
    для определения характеристик чешуи рыб и подводных объектов.

    Поддерживает:
    - Коррекцию поглощения света водой на глубине
    - Компенсацию иридесценции чешуи (многоугловое усреднение)

    Attributes:
        sensor: Объект датчика AS7262.
        analyzer: Объект анализатора цвета.
        data_queue: Очередь последних измерений.
        iridescence_buffer: Буфер для компенсации иридесценции.
        current_depth_m: Текущая глубина для коррекции (от датчика давления).
        running: Флаг работы фонового потока.
    """

    def __init__(
        self,
        bus_number: int = 1,
        led_current: int = 25,
        queue_size: int = 10,
        iridescence_samples: int = 5
    ):
        """
        Инициализация анализатора.

        Args:
            bus_number: Номер I2C шины.
            led_current: Ток подсветки в мА.
            queue_size: Размер буфера измерений.
            iridescence_samples: Кол-во измерений для компенсации иридесценции.
        """
        self.sensor = AS7262Sensor(bus_number=bus_number)
        self.sensor.set_led(led_current)
        self.analyzer = ColorAnalyzer()
        self.data_queue: deque = deque(maxlen=queue_size)
        self.iridescence_buffer: deque = deque(maxlen=iridescence_samples)
        self.current_depth_m: float = 0.0
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def set_depth(self, depth_m: float) -> None:
        """
        Установка текущей глубины для коррекции поглощения.

        Должна вызываться при получении данных от датчика давления/глубины.

        Args:
            depth_m: Глубина в метрах (0 = поверхность).
        """
        self.current_depth_m = max(0.0, depth_m)

    def measure_and_analyze(self, apply_depth_correction: bool = True) -> Dict:
        """
        Выполнение измерения и полного анализа.

        Args:
            apply_depth_correction: Применять ли коррекцию глубины.

        Returns:
            Словарь со всеми результатами анализа.
        """
        # Чтение спектра
        raw_spectrum = self.sensor.read_calibrated()

        # Сохранение в буфер иридесценции
        self.iridescence_buffer.append(raw_spectrum)

        # Коррекция поглощения на глубине
        if apply_depth_correction and self.current_depth_m > 0:
            spectrum = self.analyzer.correct_depth_absorption(
                raw_spectrum, self.current_depth_m
            )
            depth_corrected = True
        else:
            spectrum = raw_spectrum
            depth_corrected = False

        # Цветовые преобразования
        xyz = self.analyzer.spectrum_to_xyz(spectrum)
        lab = self.analyzer.xyz_to_lab(xyz)
        rgb = self.analyzer.spectrum_to_rgb(spectrum)
        hsv = self.analyzer.calculate_hsv(rgb)

        # Классификация
        color_class = self.analyzer.classify_fish_color(hsv)
        freshness = self.analyzer.assess_freshness(spectrum, lab)

        return {
            'timestamp': time.time(),
            'spectrum_raw': raw_spectrum,
            'spectrum_corrected': spectrum,
            'depth_m': self.current_depth_m,
            'depth_corrected': depth_corrected,
            'rgb': rgb,
            'hsv': {
                'hue': round(hsv[0], 1),
                'saturation': round(hsv[1], 3),
                'value': round(hsv[2], 3),
            },
            'lab': {
                'L': round(lab[0], 2),
                'a': round(lab[1], 2),
                'b': round(lab[2], 2),
            },
            'color_class': color_class,
            'freshness': freshness,
            'temperature_c': self.sensor.get_temperature(),
        }

    def measure_with_iridescence_compensation(
        self,
        num_samples: int = 5,
        delay_between_ms: int = 100
    ) -> Dict:
        """
        Измерение с компенсацией иридесценции чешуи.

        Выполняет несколько измерений и усредняет результаты
        для компенсации переливчатости от кристаллов гуанина.

        Args:
            num_samples: Количество измерений для усреднения.
            delay_between_ms: Задержка между измерениями (мс).

        Returns:
            Словарь с усреднёнными результатами и метриками иридесценции.
        """
        samples = []

        for i in range(num_samples):
            raw_spectrum = self.sensor.read_calibrated()

            # Коррекция глубины для каждого измерения
            if self.current_depth_m > 0:
                spectrum = self.analyzer.correct_depth_absorption(
                    raw_spectrum, self.current_depth_m
                )
            else:
                spectrum = raw_spectrum

            samples.append(spectrum)

            if i < num_samples - 1:
                time.sleep(delay_between_ms / 1000.0)

        # Компенсация иридесценции
        iridescence_result = self.analyzer.compensate_iridescence(samples)
        averaged_spectrum = iridescence_result['averaged_spectrum']

        # Анализ усреднённого спектра
        xyz = self.analyzer.spectrum_to_xyz(averaged_spectrum)
        lab = self.analyzer.xyz_to_lab(xyz)
        rgb = self.analyzer.spectrum_to_rgb(averaged_spectrum)
        hsv = self.analyzer.calculate_hsv(rgb)

        color_class = self.analyzer.classify_fish_color(hsv)
        freshness = self.analyzer.assess_freshness(averaged_spectrum, lab)

        return {
            'timestamp': time.time(),
            'spectrum_averaged': averaged_spectrum,
            'iridescence': {
                'detected': iridescence_result['iridescence_detected'],
                'stability_index': iridescence_result['stability_index'],
                'samples_count': iridescence_result['samples_count'],
                'max_variation_channel': iridescence_result['max_variation_channel'],
                'recommendation': iridescence_result['recommendation'],
            },
            'depth_m': self.current_depth_m,
            'rgb': rgb,
            'hsv': {
                'hue': round(hsv[0], 1),
                'saturation': round(hsv[1], 3),
                'value': round(hsv[2], 3),
            },
            'lab': {
                'L': round(lab[0], 2),
                'a': round(lab[1], 2),
                'b': round(lab[2], 2),
            },
            'color_class': color_class,
            'freshness': freshness,
            'temperature_c': self.sensor.get_temperature(),
        }

    def get_iridescence_analysis(self) -> Dict:
        """
        Анализ иридесценции на основе накопленных измерений.

        Returns:
            Результат анализа иридесценции из буфера.
        """
        samples = list(self.iridescence_buffer)
        return self.analyzer.compensate_iridescence(samples)

    def _sensor_loop(self) -> None:
        """Фоновый цикл измерений."""
        while self.running:
            try:
                result = self.measure_and_analyze()
                self.data_queue.append(result)
            except Exception as e:
                print(f"Ошибка измерения: {e}")
            time.sleep(1.0)

    def start(self) -> None:
        """Запуск фонового потока измерений."""
        if not self.running:
            self.running = True
            self._thread = threading.Thread(
                target=self._sensor_loop,
                daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Остановка фонового потока."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def get_latest(self) -> Optional[Dict]:
        """Получение последнего результата анализа."""
        return self.data_queue[-1] if self.data_queue else None

    def get_history(self, count: int = 10) -> List[Dict]:
        """Получение истории измерений."""
        return list(self.data_queue)[-count:]


def main() -> None:
    """Точка входа для автономной работы модуля."""
    print("Инициализация анализатора цвета рыб AS7262...")

    analyzer = FishColorAnalyzer(led_current=25)
    analyzer.start()

    print("Анализатор запущен. Нажмите Ctrl+C для остановки.")

    try:
        while True:
            latest = analyzer.get_latest()
            if latest:
                output = {
                    'color': latest['color_class'],
                    'rgb': latest['rgb'],
                    'freshness': latest['freshness']['status'],
                    'score': latest['freshness']['score'],
                }
                print(json.dumps(output, ensure_ascii=False))
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nОстановка анализатора...")
        analyzer.stop()


if __name__ == "__main__":
    main()
