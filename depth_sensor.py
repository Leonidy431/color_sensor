"""
Драйвер датчика глубины/давления MS5837 (Blue Robotics Bar02/Bar30).

Фаза 3 HLD (CLAUDE.md): синхронизация измерений глубины со спектральными
измерениями AS7262 для коррекции поглощения воды (см. FishColorAnalyzer.
set_depth() в color_fish_analyzer.py).

Протокол и формулы компенсации давления/температуры взяты из открытого
даташита производителя (не проприетарный код):
- TE Connectivity, "MS5837-30BA - Ultra-small Gel-Filled Pressure Sensor",
  Rev C6 (02/2025) - I2C-команды, PROM-калибровка (6 коэффициентов
  C1-C6 + CRC4), формула компенсации 2-го порядка идентична всему
  семейству MS56xx/MS58xx (та же схема используется в MS5611 и др.).
- Тот же алгоритм реализован в открытой библиотеке Blue Robotics
  (BlueRobotics_MS5837_Library, MIT license) - здесь используется как
  референс для формулы, код написан самостоятельно под стиль проекта.

ВАЖНО (CLAUDE.md §5, "не симулировать результаты"): формула компенсации
проверена тестами на самосогласованность (монотонность, физическая
осмысленность round-trip давление<->глубина), НО НЕ валидирована против
эталонных значений производителя на реальном железе - в этой сессии нет
доступа к физическому датчику. Перед полевым использованием обязательна
проверка на реальном MS5837 против известного эталонного давления.
"""

import time
from dataclasses import dataclass
from typing import Optional

import smbus

MS5837_I2C_ADDRESS = 0x76

CMD_RESET = 0x1E
CMD_ADC_READ = 0x00
CMD_PROM_READ_BASE = 0xA0  # + 2*n, n=0..7

# Команды конвертации с OSR (Over-Sampling Ratio) = 8192 (максимальная
# точность, время конверсии ~20 мс) - компромисс точность/частота
# опроса достаточен для синхронизации с измерениями AS7262 (~1 Гц).
CMD_CONVERT_D1_OSR8192 = 0x4A  # Давление
CMD_CONVERT_D2_OSR8192 = 0x5A  # Температура
CONVERSION_DELAY_S = 0.020

# Плотность жидкости для перевода давления в глубину (кг/м^3).
# Литературные значения по умолчанию - реальная солёность/плотность
# зависит от акватории (например, Чёрное море ~1010-1015 кг/м^3 из-за
# пониженной солёности, в отличие от открытого океана ~1029 кг/м^3),
# поэтому вынесено параметром, а не захардкожено (CLAUDE.md §2).
FLUID_DENSITY_SEAWATER_KG_M3 = 1029.0
FLUID_DENSITY_FRESHWATER_KG_M3 = 997.0
STANDARD_GRAVITY_M_S2 = 9.80665
ATMOSPHERIC_PRESSURE_MBAR = 1013.25


@dataclass
class DepthReading:
    """Результат одного измерения датчика глубины."""

    pressure_mbar: float
    temperature_c: float
    depth_m: float
    timestamp: float


class MS5837Sensor:
    """
    Драйвер датчика давления/глубины MS5837 (Bar02/Bar30).

    Attributes:
        bus: Объект I2C шины SMBus.
        address: I2C адрес датчика (фиксированный 0x76).
        fluid_density_kg_m3: Плотность воды для перевода давления в
            глубину.
    """

    def __init__(
        self,
        bus_number: int = 1,
        fluid_density_kg_m3: float = FLUID_DENSITY_SEAWATER_KG_M3,
    ):
        """
        Инициализация и калибровка датчика.

        Args:
            bus_number: Номер I2C шины (1 для Raspberry Pi).
            fluid_density_kg_m3: Плотность воды в месте эксплуатации.
        """
        self.bus = smbus.SMBus(bus_number)
        self.address = MS5837_I2C_ADDRESS
        self.fluid_density_kg_m3 = fluid_density_kg_m3

        self._prom: list = []
        self._reset()
        self._read_prom()

    def _reset(self) -> None:
        """Программный сброс датчика (обязателен после включения питания)."""
        self.bus.write_byte(self.address, CMD_RESET)
        time.sleep(0.010)

    def _read_prom(self) -> None:
        """
        Чтение PROM-калибровки (6 коэффициентов C1-C6 + 2 слова CRC).

        Raises:
            RuntimeError: если контрольная сумма CRC4 не совпадает
                (повреждённые данные калибровки или обрыв связи).
        """
        prom = []
        for i in range(8):
            cmd = CMD_PROM_READ_BASE + 2 * i
            raw = self.bus.read_i2c_block_data(self.address, cmd, 2)
            prom.append((raw[0] << 8) | raw[1])
        self._prom = prom

        if not self._check_crc4(prom):
            raise RuntimeError(
                "MS5837: контрольная сумма CRC4 PROM не совпадает - "
                "проверьте подключение или замените датчик."
            )

    @staticmethod
    def _check_crc4(prom: list) -> bool:
        """
        Проверка CRC4 калибровочного PROM (алгоритм из даташита TE).

        Args:
            prom: 8 16-битных слов PROM (включая CRC в младших 4 битах
                слова 0).

        Returns:
            True, если вычисленная CRC4 совпадает с хранимой.
        """
        n_prom = list(prom)
        crc_read = n_prom[0] & 0x000F
        n_prom[0] = n_prom[0] & 0xFF00
        n_prom.append(0)

        n_rem = 0
        for i in range(16):
            byte = n_prom[i >> 1]
            n_rem ^= (byte >> 8) if (i % 2 == 0) else (byte & 0x00FF)
            for _ in range(8):
                if n_rem & 0x8000:
                    n_rem = (n_rem << 1) ^ 0x3000
                else:
                    n_rem = n_rem << 1
            n_rem &= 0xFFFF

        crc_calculated = (n_rem >> 12) & 0x000F
        return crc_calculated == crc_read

    def _convert_and_read(self, command: int) -> int:
        """Запуск АЦП-конверсии и чтение 24-битного результата."""
        self.bus.write_byte(self.address, command)
        time.sleep(CONVERSION_DELAY_S)
        raw = self.bus.read_i2c_block_data(self.address, CMD_ADC_READ, 3)
        return (raw[0] << 16) | (raw[1] << 8) | raw[2]

    def read(self) -> DepthReading:
        """
        Выполнение измерения давления/температуры и расчёт глубины.

        Реализует компенсацию 2-го порядка по формуле из даташита
        MS5837-30BA (идентична семейству MS56xx/MS58xx).

        Returns:
            DepthReading с давлением (мбар), температурой (°C) и
            глубиной (м).
        """
        d1 = self._convert_and_read(CMD_CONVERT_D1_OSR8192)  # Давление
        d2 = self._convert_and_read(CMD_CONVERT_D2_OSR8192)  # Температура

        c1, c2, c3, c4, c5, c6 = self._prom[1:7]

        dt = d2 - c5 * 256
        temp = 2000 + dt * c6 / 8388608  # сотые доли °C

        off = c2 * 65536 + (c4 * dt) / 128
        sens = c1 * 32768 + (c3 * dt) / 256

        # Компенсация 2-го порядка (более точная коррекция при
        # температурах ниже 20°C, дополнительная - ниже -15°C).
        if temp < 2000:
            ti = 3 * dt ** 2 / 8589934592  # 2^33
            offi = 3 * (temp - 2000) ** 2 / 2
            sensi = 5 * (temp - 2000) ** 2 / 8
            if temp < -1500:
                offi += 7 * (temp + 1500) ** 2
                sensi += 4 * (temp + 1500) ** 2
        else:
            ti = 2 * dt ** 2 / 137438953472  # 2^37
            offi = (temp - 2000) ** 2 / 16
            sensi = 0

        temp -= ti
        off -= offi
        sens -= sensi

        pressure_mbar = (d1 * sens / 2097152 - off) / 8192 / 10.0
        temperature_c = temp / 100.0

        depth_m = self.calculate_depth(pressure_mbar, self.fluid_density_kg_m3)

        return DepthReading(
            pressure_mbar=pressure_mbar,
            temperature_c=temperature_c,
            depth_m=depth_m,
            timestamp=time.time(),
        )

    @staticmethod
    def calculate_depth(
        pressure_mbar: float,
        fluid_density_kg_m3: float = FLUID_DENSITY_SEAWATER_KG_M3,
        surface_pressure_mbar: float = ATMOSPHERIC_PRESSURE_MBAR,
    ) -> float:
        """
        Перевод давления в глубину по гидростатической формуле.

        P = P_atm + rho * g * h  =>  h = (P - P_atm) / (rho * g)

        Args:
            pressure_mbar: Измеренное абсолютное давление (мбар).
            fluid_density_kg_m3: Плотность воды (кг/м^3).
            surface_pressure_mbar: Атмосферное давление на поверхности
                (мбар), по умолчанию стандартное 1013.25 мбар.

        Returns:
            Глубина в метрах (0 на поверхности).
        """
        pressure_pa = (pressure_mbar - surface_pressure_mbar) * 100.0
        depth_m = pressure_pa / (fluid_density_kg_m3 * STANDARD_GRAVITY_M_S2)
        return max(0.0, depth_m)


class DepthSyncBridge:
    """
    Мост синхронизации MS5837 -> FishColorAnalyzer.set_depth().

    Реализует требование Фазы 3 HLD: "синхронизация по времени со
    спектральными измерениями". Держит последнее показание глубины и
    обновляет анализатор перед каждым спектральным измерением, вместо
    независимых, несинхронизированных по времени опросов двух шин I2C.
    """

    def __init__(self, depth_sensor: MS5837Sensor, max_staleness_s: float = 2.0):
        """
        Args:
            depth_sensor: Инициализированный датчик MS5837.
            max_staleness_s: Максимальный возраст показания глубины (с),
                после которого оно считается устаревшим (обрыв связи с
                датчиком не должен тихо использовать старую глубину
                бесконечно долго).
        """
        self.depth_sensor = depth_sensor
        self.max_staleness_s = max_staleness_s
        self._last_reading: Optional[DepthReading] = None

    def poll(self) -> DepthReading:
        """Опрос датчика и сохранение последнего показания."""
        self._last_reading = self.depth_sensor.read()
        return self._last_reading

    def get_synced_depth_m(self) -> float:
        """
        Текущая глубина для использования в измерении цвета.

        Returns:
            Глубина в метрах, либо 0.0 если данных ещё нет или
            последнее показание устарело (max_staleness_s).

        Raises:
            RuntimeError: если последнее показание устарело - вызывающий
                код должен опросить датчик заново (poll()), а не молча
                использовать старую глубину для коррекции спектра.
        """
        if self._last_reading is None:
            return 0.0

        age_s = time.time() - self._last_reading.timestamp
        if age_s > self.max_staleness_s:
            raise RuntimeError(
                "Показание глубины устарело (%.1f с > %.1f с): "
                "вызовите poll() перед измерением." % (age_s, self.max_staleness_s)
            )

        return self._last_reading.depth_m
