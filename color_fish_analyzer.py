"""
Модуль анализа цвета чешуи рыб и подводных объектов.

Использует 6-канальный спектральный датчик AS7262 для измерения
спектральной отражательной способности в видимом диапазоне (450-650 нм).

Научные методы:
- Преобразование спектра в CIE L*a*b* и RGB цветовые пространства
- Анализ свежести по насыщенности цвета (метод TVB-N корреляции)
- Классификация цвета по доминирующей длине волны

Ссылки:
- https://www.sciencedirect.com/science/article/pii/S2772753X22001174
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9265959/
"""

import json
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

    Attributes:
        sensor: Объект датчика AS7262.
        analyzer: Объект анализатора цвета.
        data_queue: Очередь последних измерений.
        running: Флаг работы фонового потока.
    """

    def __init__(
        self,
        bus_number: int = 1,
        led_current: int = 25,
        queue_size: int = 10
    ):
        """
        Инициализация анализатора.

        Args:
            bus_number: Номер I2C шины.
            led_current: Ток подсветки в мА.
            queue_size: Размер буфера измерений.
        """
        self.sensor = AS7262Sensor(bus_number=bus_number)
        self.sensor.set_led(led_current)
        self.analyzer = ColorAnalyzer()
        self.data_queue: deque = deque(maxlen=queue_size)
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def measure_and_analyze(self) -> Dict:
        """
        Выполнение измерения и полного анализа.

        Returns:
            Словарь со всеми результатами анализа.
        """
        # Чтение спектра
        spectrum = self.sensor.read_calibrated()

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
            'spectrum': spectrum,
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
