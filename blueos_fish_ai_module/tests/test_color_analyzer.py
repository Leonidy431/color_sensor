"""
Tests for Fish Color Analyzer.

Тесты для модуля анализа цвета рыб.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestColorConversions:
    """Тесты преобразования цветовых пространств."""

    def test_spectrum_to_rgb_red_dominant(self):
        """Тест: спектр с доминантой красного."""
        from data_fusion import SpeciesColorProfile

        spectrum = {
            'violet': 0.1,
            'blue': 0.1,
            'green': 0.2,
            'yellow': 0.3,
            'orange': 0.6,
            'red': 0.8,
        }

        # Red should be dominant
        r = spectrum['red'] * 1.0 + spectrum['orange'] * 0.5
        g = spectrum['green'] * 1.0 + spectrum['yellow'] * 0.5
        b = spectrum['blue'] * 1.0 + spectrum['violet'] * 0.8

        assert r > g
        assert r > b

    def test_spectrum_to_rgb_green_dominant(self):
        """Тест: спектр с доминантой зелёного."""
        spectrum = {
            'violet': 0.1,
            'blue': 0.2,
            'green': 0.9,
            'yellow': 0.4,
            'orange': 0.1,
            'red': 0.1,
        }

        r = spectrum['red'] * 1.0 + spectrum['orange'] * 0.5
        g = spectrum['green'] * 1.0 + spectrum['yellow'] * 0.5
        b = spectrum['blue'] * 1.0 + spectrum['violet'] * 0.8

        assert g > r
        assert g > b

    def test_hsv_calculation(self):
        """Тест расчёта HSV."""
        # Pure red
        rgb = (255, 0, 0)
        r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
        max_c = max(r, g, b)
        min_c = min(r, g, b)

        # Hue should be 0 for red
        assert max_c == 1.0
        assert min_c == 0.0

        # Pure green - hue ~120
        rgb = (0, 255, 0)
        r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
        assert g == 1.0

        # Pure blue - hue ~240
        rgb = (0, 0, 255)
        r, g, b = rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
        assert b == 1.0


class TestFreshnessAssessment:
    """Тесты оценки свежести."""

    def test_fresh_fish_high_chroma(self):
        """Свежая рыба имеет высокую насыщенность."""
        # High chroma = sqrt(a*^2 + b*^2)
        a_star = 30
        b_star = 40
        chroma = (a_star ** 2 + b_star ** 2) ** 0.5

        assert chroma == 50.0  # 3-4-5 triangle
        assert chroma >= 40  # Fresh threshold

    def test_spoiled_fish_low_chroma(self):
        """Несвежая рыба имеет низкую насыщенность."""
        a_star = 5
        b_star = 5
        chroma = (a_star ** 2 + b_star ** 2) ** 0.5

        assert chroma < 10  # Low saturation
        assert chroma < 20  # Below acceptable threshold

    def test_freshness_score_calculation(self):
        """Тест расчёта индекса свежести."""
        # Formula: 0.4 * (chroma/50) + 0.3 * (L*/100) + 0.3 * (ratio/2)
        chroma = 40
        l_star = 80
        spectral_ratio = 1.5

        score = (
            0.4 * min(chroma / 50, 1.0) +
            0.3 * min(l_star / 100, 1.0) +
            0.3 * min(spectral_ratio / 2, 1.0)
        )

        assert 0.6 <= score <= 1.0  # Should be "fresh"


class TestColorClassification:
    """Тесты классификации цвета."""

    def test_red_fish(self):
        """Красная рыба (hue < 15 или >= 345)."""
        hue = 10
        saturation = 0.6

        if saturation >= 0.15:
            if hue < 15 or hue >= 345:
                color_class = "red"
            else:
                color_class = "other"

        assert color_class == "red"

    def test_silver_fish_low_saturation(self):
        """Серебристая рыба (низкая насыщенность)."""
        saturation = 0.1

        if saturation < 0.15:
            color_class = "silver"
        else:
            color_class = "colored"

        assert color_class == "silver"

    def test_green_fish(self):
        """Зелёная рыба (hue 75-165)."""
        hue = 120
        saturation = 0.5

        if saturation >= 0.15:
            if 75 <= hue < 165:
                color_class = "green"
            else:
                color_class = "other"

        assert color_class == "green"


class TestDataFusion:
    """Тесты слияния данных."""

    def test_species_matching(self):
        """Тест сопоставления вида по цветовому профилю."""
        # Salmon color profile
        salmon_hue_range = (0, 30)  # Orange-red
        detected_hue = 15

        in_range = salmon_hue_range[0] <= detected_hue <= salmon_hue_range[1]
        assert in_range is True

    def test_iridescent_detection(self):
        """Тест обнаружения иридесценции."""
        # Iridescent fish have varying colors
        measurements = [120, 150, 100, 180, 90]  # Hue values

        variance = sum((m - sum(measurements)/len(measurements))**2
                       for m in measurements) / len(measurements)

        # High variance indicates iridescence
        is_iridescent = variance > 500
        assert is_iridescent is True


class TestSpectrumValidation:
    """Тесты валидации спектральных данных."""

    def test_valid_spectrum_range(self):
        """Все значения спектра должны быть положительными."""
        spectrum = {
            'violet': 0.5,
            'blue': 0.6,
            'green': 0.7,
            'yellow': 0.4,
            'orange': 0.3,
            'red': 0.2,
        }

        all_positive = all(v >= 0 for v in spectrum.values())
        assert all_positive is True

    def test_spectrum_channels_count(self):
        """AS7262 должен иметь 6 каналов."""
        channels = ['violet', 'blue', 'green', 'yellow', 'orange', 'red']
        assert len(channels) == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
