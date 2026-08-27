"""
Unit-тесты Fresnel-модели тонкоплёночной иридесценции (Фаза 4 HLD).

Проверяет физическую корректность модели на синтетических данных с
известным результатом:
- Условие конструктивной интерференции действительно даёт максимум
  отражения (а не минимум - для геометрии "гуанин плотнее обеих
  соседних сред" знаки коэффициентов Френеля границ противоположны,
  что меняет условие максимума с δ=2πm на δ=(2m-1)π; см. докстринг
  _peak_condition_denominator в color_fish_analyzer.py).
- Голубое смещение пика с ростом угла (главный наблюдаемый факт
  иридесценции).
- Регрессия calibrate_crystal_thickness() точно восстанавливает
  истинную толщину кристалла по синтетическим наблюдениям.
"""

import random
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if 'smbus' not in sys.modules:
    fake_smbus = types.ModuleType('smbus')

    class _FakeSMBus:
        def __init__(self, bus_number):
            pass

    fake_smbus.SMBus = _FakeSMBus
    sys.modules['smbus'] = fake_smbus

from color_fish_analyzer import ColorAnalyzer  # noqa: E402


@pytest.fixture
def analyzer():
    return ColorAnalyzer()


class TestPeakConditionSign:
    """Знаменатель условия максимума зависит от знака r1*r2."""

    def test_monotonic_index_profile_uses_2m(self, analyzer):
        # n0 < n1 < n2 (например, стекло на подложке с более высоким
        # индексом) - r1, r2 одного знака.
        denom = analyzer._peak_condition_denominator(1, 1.0, 1.5, 2.0)
        assert denom == 2.0

    def test_guanine_geometry_uses_2m_minus_1(self, analyzer):
        # n0 < n1 > n2 (гуанин плотнее и воды, и цитоплазмы) -
        # r1, r2 противоположных знаков.
        denom = analyzer._peak_condition_denominator(
            1,
            analyzer.WATER_REFRACTIVE_INDEX,
            analyzer.GUANINE_REFRACTIVE_INDEX,
            analyzer.CYTOPLASM_REFRACTIVE_INDEX,
        )
        assert denom == 1.0


class TestConstructiveInterference:
    """Предсказанный пик действительно даёт максимум отражения."""

    def test_reflectance_maximal_at_predicted_peak(self, analyzer):
        thickness_nm = 100.0
        angle_deg = 0.0
        peak_wl = analyzer.predict_peak_wavelength(thickness_nm, angle_deg)

        r_peak = analyzer.thin_film_reflectance(peak_wl, thickness_nm, angle_deg)
        r_higher = analyzer.thin_film_reflectance(
            peak_wl * 1.15, thickness_nm, angle_deg
        )
        r_lower = analyzer.thin_film_reflectance(
            peak_wl * 0.85, thickness_nm, angle_deg
        )

        assert r_peak > r_higher
        assert r_peak > r_lower

    def test_reflectance_in_valid_range(self, analyzer):
        for wl in [400, 500, 600, 700]:
            r = analyzer.thin_film_reflectance(wl, 100.0, 30.0)
            assert 0.0 <= r <= 1.0


class TestAngleDependentBlueShift:
    """Главный наблюдаемый факт иридесценции: пик сдвигается с углом."""

    def test_peak_blue_shifts_with_increasing_angle(self, analyzer):
        thickness_nm = 100.0
        peaks = [
            analyzer.predict_peak_wavelength(thickness_nm, angle)
            for angle in [0, 15, 30, 45, 60]
        ]
        # Монотонное убывание длины волны пика с ростом угла.
        assert all(peaks[i] > peaks[i + 1] for i in range(len(peaks) - 1))


class TestCrystalThicknessCalibration:
    """Регрессия восстанавливает истинную толщину по синтетическим
    наблюдениям (тот же принцип, что calibrate_absorption /
    calibrate_temperature)."""

    def test_exact_recovery_noiseless(self, analyzer):
        true_thickness = 95.0
        observations = [
            (float(angle), analyzer.predict_peak_wavelength(true_thickness, angle))
            for angle in [0, 15, 30, 45, 60]
        ]
        estimated = analyzer.calibrate_crystal_thickness(observations)
        assert estimated == pytest.approx(true_thickness, abs=1e-6)

    def test_noisy_observations_within_tolerance(self, analyzer):
        random.seed(42)
        true_thickness = 95.0
        observations = [
            (
                float(angle),
                analyzer.predict_peak_wavelength(true_thickness, angle)
                + random.uniform(-5, 5),
            )
            for angle in [0, 15, 30, 45, 60]
        ]
        estimated = analyzer.calibrate_crystal_thickness(observations)
        assert estimated == pytest.approx(true_thickness, abs=5.0)

    def test_empty_observations_raises(self, analyzer):
        with pytest.raises(ValueError):
            analyzer.calibrate_crystal_thickness([])

    def test_single_observation_works(self, analyzer):
        true_thickness = 80.0
        peak = analyzer.predict_peak_wavelength(true_thickness, 20.0)
        estimated = analyzer.calibrate_crystal_thickness([(20.0, peak)])
        assert estimated == pytest.approx(true_thickness, abs=1e-6)
