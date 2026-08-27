"""Unit-тесты для гиперспектральной калибровки и спектрального анализа."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from hsi_calibration import HSICalibrator, HyperspectralCube  # noqa: E402
from spectral_analysis import (  # noqa: E402
    SpectralAnalyzer,
    SpectralLibrary,
    spectral_angle,
)


WAVELENGTHS = [450.0, 500.0, 550.0, 600.0, 650.0]


class TestSpectralAngleMapper:
    """Тесты алгоритма Spectral Angle Mapper (факт 29)."""

    def test_identical_shape_zero_angle(self):
        a = np.array([0.1, 0.3, 0.5, 0.2])
        b = a * 3.0
        assert spectral_angle(a, b) < 1e-9

    def test_different_shape_nonzero_angle(self):
        a = np.array([0.1, 0.3, 0.5, 0.2])
        c = np.array([0.5, 0.1, 0.1, 0.5])
        assert spectral_angle(a, c) > 0.1

    def test_zero_vector_max_angle(self):
        a = np.zeros(4)
        b = np.array([1.0, 2.0, 3.0, 4.0])
        assert spectral_angle(a, b) == pytest.approx(math.pi / 2)


class TestHSICalibrator:
    """Тесты тёмного кадра, белого эталона, коррекции столба воды."""

    def test_dark_current_subtraction(self):
        cal = HSICalibrator()
        cal.set_dark_reference(np.array([5.0, 5.0, 5.0]))
        result = cal.subtract_dark_current(np.array([105.0, 205.0, 305.0]))
        assert np.allclose(result, [100.0, 200.0, 300.0])

    def test_dark_current_clips_negative(self):
        cal = HSICalibrator()
        cal.set_dark_reference(np.array([10.0]))
        result = cal.subtract_dark_current(np.array([5.0]))
        assert result[0] == 0.0

    def test_dark_current_requires_reference(self):
        cal = HSICalibrator()
        with pytest.raises(RuntimeError):
            cal.subtract_dark_current(np.array([1.0]))

    def test_white_reference_ratio_method(self):
        cal = HSICalibrator()
        cal.set_dark_reference(np.array([5.0, 5.0, 5.0]))
        white = cal.subtract_dark_current(np.array([505.0, 505.0, 505.0]))
        cal.calibrate_white_reference(white, reference_reflectance=0.99)

        sample = cal.subtract_dark_current(np.array([105.0, 205.0, 305.0]))
        reflectance = cal.apply_white_reference(sample)
        expected = (sample / 500.0) * 0.99
        assert np.allclose(reflectance, expected)

    def test_water_column_calibration_recovers_true_alpha(self):
        true_alpha = {450.0: 0.02, 500.0: 0.025, 550.0: 0.06,
                      600.0: 0.24, 650.0: 0.35}
        i0 = 100.0
        samples = []
        for d in [0, 2, 4, 6, 8]:
            spectrum = np.array([
                i0 * math.exp(-2 * true_alpha[wl] * d) for wl in WAVELENGTHS
            ])
            samples.append((float(d), spectrum))

        cal = HSICalibrator()
        calibrated = cal.calibrate_water_column(samples, WAVELENGTHS)

        for wl, alpha in true_alpha.items():
            assert calibrated[wl] == pytest.approx(alpha, abs=1e-6)
        assert cal.is_water_column_calibrated

    def test_water_column_correction_round_trip(self):
        true_alpha = {450.0: 0.02, 500.0: 0.025, 550.0: 0.06,
                      600.0: 0.24, 650.0: 0.35}
        i0 = 100.0
        samples = []
        for d in [0, 2, 4, 6, 8]:
            spectrum = np.array([
                i0 * math.exp(-2 * true_alpha[wl] * d) for wl in WAVELENGTHS
            ])
            samples.append((float(d), spectrum))

        cal = HSICalibrator()
        cal.calibrate_water_column(samples, WAVELENGTHS)

        measured_at_5 = np.array([[[
            i0 * math.exp(-2 * true_alpha[wl] * 5) for wl in WAVELENGTHS
        ]]])
        corrected = cal.correct_water_column(measured_at_5, WAVELENGTHS, 5.0)
        assert np.allclose(corrected[0, 0, :], [i0] * 5, atol=1e-3)

    def test_no_correction_at_surface(self):
        cal = HSICalibrator()
        cube = np.ones((1, 1, 5))
        result = cal.correct_water_column(cube, WAVELENGTHS, depth_m=0.0)
        assert np.allclose(result, cube)


class TestSpectralAnalyzer:
    """Тесты классификации и диагностических индексов."""

    def test_degradation_index(self):
        analyzer = SpectralAnalyzer()
        spectrum = np.array([0.3, 0.4, 0.5, 0.6, 0.9])
        idx = analyzer.degradation_index(
            spectrum, WAVELENGTHS, band_a_nm=600, band_b_nm=500
        )
        assert idx == pytest.approx(0.6 / 0.4)

    def test_classify_pure_endmember(self):
        analyzer = SpectralAnalyzer()
        lib = SpectralLibrary.seed_illustrative_library(WAVELENGTHS)
        name, angle = analyzer.classify_pixel(
            lib.endmembers['iron_oxide_rust'], lib
        )
        assert name == 'iron_oxide_rust'
        assert angle < 1e-9

    def test_classify_cube_four_materials(self):
        analyzer = SpectralAnalyzer()
        lib = SpectralLibrary.seed_illustrative_library(WAVELENGTHS)

        cube = np.zeros((2, 2, len(WAVELENGTHS)))
        cube[0, 0, :] = lib.endmembers['oak_wood_healthy']
        cube[0, 1, :] = lib.endmembers['iron_oxide_rust']
        cube[1, 0, :] = lib.endmembers['sand_silt']
        cube[1, 1, :] = lib.endmembers['chlorophyll_biofouling']

        result = analyzer.classify_cube(cube, lib)
        assert result['class_map'][0, 0] == 'oak_wood_healthy'
        assert result['class_map'][0, 1] == 'iron_oxide_rust'
        assert result['class_map'][1, 0] == 'sand_silt'
        assert result['class_map'][1, 1] == 'chlorophyll_biofouling'

    def test_unknown_class_above_threshold(self):
        analyzer = SpectralAnalyzer()
        lib = SpectralLibrary.seed_illustrative_library(WAVELENGTHS)
        # Спектр-"пила", максимально не похожий по форме ни на один
        # из гладких эталонов -> угол SAM должен превысить строгий порог.
        odd_spectrum = np.array([0.0, 1.0, 0.0, 1.0, 0.0])
        cube = odd_spectrum.reshape(1, 1, -1)
        result = analyzer.classify_cube(cube, lib, max_angle_rad=0.01)
        assert result['class_map'][0, 0] == 'unknown'
        assert result['angle_map'][0, 0] > 0.01

    def test_spectral_library_load_measured_overrides(self):
        lib = SpectralLibrary.seed_illustrative_library(WAVELENGTHS)
        real_spectrum = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        lib.load_measured('oak_wood_healthy', real_spectrum)
        assert np.allclose(lib.endmembers['oak_wood_healthy'], real_spectrum)

    def test_spectral_library_load_measured_wrong_length_raises(self):
        lib = SpectralLibrary.seed_illustrative_library(WAVELENGTHS)
        with pytest.raises(ValueError):
            lib.load_measured('bad', np.array([0.1, 0.2]))


class TestHyperspectralCube:
    """Тесты структуры данных куба."""

    def test_band_index_nearest(self):
        cube = HyperspectralCube(
            data=np.zeros((1, 1, len(WAVELENGTHS))),
            wavelengths_nm=WAVELENGTHS,
        )
        assert cube.band_index(605) == 3
        assert cube.band_index(450) == 0

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            HyperspectralCube(
                data=np.zeros((1, 1, 3)),
                wavelengths_nm=WAVELENGTHS,
            )
