"""
Unit-тесты датчика глубины MS5837 (Фаза 3 HLD).

Без физического датчика проверяется:
- Гидростатическая формула глубина<->давление (точный round-trip).
- Самосогласованность алгоритма CRC4 (корректная сумма принимается,
  испорченные данные отклоняются).
- Мост синхронизации DepthSyncBridge (staleness guard).

НЕ проверяется (требует реального железа - см. предупреждение в
docstring depth_sensor.py): численное совпадение формулы компенсации
давления/температуры 2-го порядка с эталонными значениями производителя.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import types  # noqa: E402

if 'smbus' not in sys.modules:
    fake_smbus = types.ModuleType('smbus')

    class _FakeSMBus:
        def __init__(self, bus_number):
            pass

    fake_smbus.SMBus = _FakeSMBus
    sys.modules['smbus'] = fake_smbus

from depth_sensor import (  # noqa: E402
    ATMOSPHERIC_PRESSURE_MBAR,
    DepthReading,
    DepthSyncBridge,
    MS5837Sensor,
    STANDARD_GRAVITY_M_S2,
)


class TestDepthPressureConversion:
    """Гидростатическая формула P = P_atm + rho*g*h."""

    def test_round_trip_seawater(self):
        rho = 1029.0
        true_depth = 27.5  # объект "Ниссия"
        pressure = (
            ATMOSPHERIC_PRESSURE_MBAR
            + rho * STANDARD_GRAVITY_M_S2 * true_depth / 100.0
        )
        computed = MS5837Sensor.calculate_depth(pressure, rho)
        assert computed == pytest.approx(true_depth, abs=1e-6)

    def test_round_trip_black_sea_brackish_density(self):
        # Пониженная солёность Чёрного моря - другая плотность.
        rho = 1012.0
        true_depth = 15.0
        pressure = (
            ATMOSPHERIC_PRESSURE_MBAR
            + rho * STANDARD_GRAVITY_M_S2 * true_depth / 100.0
        )
        computed = MS5837Sensor.calculate_depth(pressure, rho)
        assert computed == pytest.approx(true_depth, abs=1e-6)

    def test_surface_pressure_gives_zero_depth(self):
        assert MS5837Sensor.calculate_depth(ATMOSPHERIC_PRESSURE_MBAR) == 0.0

    def test_below_atmospheric_clamped_to_zero(self):
        assert MS5837Sensor.calculate_depth(900.0) == 0.0


class TestCRC4:
    """Самосогласованность контрольной суммы PROM (алгоритм из даташита)."""

    @staticmethod
    def _compute_crc4(prom_no_crc):
        n_prom = list(prom_no_crc)
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
        return (n_rem >> 12) & 0x000F

    def test_correct_checksum_accepted(self):
        prom = [0x1234, 42000, 54000, 30000, 20000, 30000, 25000, 0]
        crc = self._compute_crc4(prom)
        prom[0] = (prom[0] & 0xFF00) | crc
        assert MS5837Sensor._check_crc4(prom) is True

    def test_corrupted_data_rejected(self):
        prom = [0x1234, 42000, 54000, 30000, 20000, 30000, 25000, 0]
        crc = self._compute_crc4(prom)
        prom[0] = (prom[0] & 0xFF00) | crc
        corrupted = list(prom)
        corrupted[3] ^= 0xFFFF
        assert MS5837Sensor._check_crc4(corrupted) is False


class _DummySensor:
    """Фиктивный датчик для тестов DepthSyncBridge без реального I2C."""

    def __init__(self, depth_m: float):
        self.depth_m = depth_m

    def read(self) -> DepthReading:
        return DepthReading(
            pressure_mbar=1100.0,
            temperature_c=15.0,
            depth_m=self.depth_m,
            timestamp=time.time(),
        )


class TestDepthSyncBridge:
    """Мост синхронизации глубины со спектральными измерениями."""

    def test_no_data_returns_zero(self):
        bridge = DepthSyncBridge(_DummySensor(8.7))
        assert bridge.get_synced_depth_m() == 0.0

    def test_after_poll_returns_reading(self):
        bridge = DepthSyncBridge(_DummySensor(8.7))
        bridge.poll()
        assert bridge.get_synced_depth_m() == pytest.approx(8.7)

    def test_stale_reading_raises(self):
        bridge = DepthSyncBridge(_DummySensor(8.7), max_staleness_s=0.05)
        bridge.poll()
        time.sleep(0.1)
        with pytest.raises(RuntimeError):
            bridge.get_synced_depth_m()
