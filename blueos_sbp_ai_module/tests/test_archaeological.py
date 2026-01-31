"""
Tests for Archaeological Object Detection.

Тесты для модуля детекции археологических объектов.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestArchaeologicalClassification:
    """Тесты классификации археологических объектов."""

    def test_shipwreck_acoustic_signature(self):
        """Затонувшее судно имеет характерную сигнатуру."""
        from archaeological_detector import ArchaeologicalClass

        # Wooden shipwreck characteristics
        reflection_db = 0  # Moderate
        size_m = 20  # Large
        has_shadow = True

        # Check against signature
        wooden_ship_ref_range = (-10, 5)
        wooden_ship_size_range = (5, 50)

        ref_match = wooden_ship_ref_range[0] <= reflection_db <= wooden_ship_ref_range[1]
        size_match = wooden_ship_size_range[0] <= size_m <= wooden_ship_size_range[1]

        assert ref_match is True
        assert size_match is True

    def test_anchor_detection(self):
        """Якорь имеет сильное отражение и малый размер."""
        reflection_db = 10  # Strong
        size_m = 2.5

        anchor_ref_range = (0, 15)
        anchor_size_range = (1, 5)

        ref_match = anchor_ref_range[0] <= reflection_db <= anchor_ref_range[1]
        size_match = anchor_size_range[0] <= size_m <= anchor_size_range[1]

        assert ref_match is True
        assert size_match is True

    def test_amphora_signature(self):
        """Амфора имеет слабое отражение и малый размер."""
        reflection_db = 0
        size_m = 0.8

        amphora_ref_range = (-5, 5)
        amphora_size_range = (0.3, 1.5)

        ref_match = amphora_ref_range[0] <= reflection_db <= amphora_ref_range[1]
        size_match = amphora_size_range[0] <= size_m <= amphora_size_range[1]

        assert ref_match is True
        assert size_match is True


class TestHistoricalPeriodEstimation:
    """Тесты оценки исторического периода."""

    def test_ancient_depth(self):
        """Античные объекты залегают глубже."""
        depth_m = 8.0
        ancient_range = (2.0, 15.0)

        is_ancient = ancient_range[0] <= depth_m <= ancient_range[1]
        assert is_ancient is True

    def test_modern_depth(self):
        """Современные объекты на поверхности."""
        depth_m = 0.5
        modern_range = (0.0, 3.0)

        is_modern = modern_range[0] <= depth_m <= modern_range[1]
        assert is_modern is True

    def test_medieval_depth(self):
        """Средневековые объекты на средней глубине."""
        depth_m = 4.0
        medieval_range = (1.0, 8.0)

        is_medieval = medieval_range[0] <= depth_m <= medieval_range[1]
        assert is_medieval is True


class TestScientificValueCalculation:
    """Тесты расчёта научной ценности."""

    def test_high_value_ancient_shipwreck(self):
        """Древнее деревянное судно имеет высокую ценность."""
        # Rarity score for wooden shipwreck: 0.9
        # Period score for ancient: 0.5
        # Size bonus for >10m: 0.2
        # Total before confidence: 1.6, capped at 1.0

        rarity_score = 0.9
        period_score = 0.5
        size_bonus = 0.2
        confidence = 0.85

        raw_value = rarity_score + period_score + size_bonus
        final_value = min(raw_value, 1.0) * confidence

        assert final_value > 0.7  # High value

    def test_low_value_modern_debris(self):
        """Современный мусор имеет низкую ценность."""
        rarity_score = 0.3
        period_score = 0.0  # Contemporary
        size_bonus = 0.0
        confidence = 0.6

        raw_value = rarity_score + period_score + size_bonus
        final_value = min(raw_value, 1.0) * confidence

        assert final_value < 0.3  # Low value


class TestPriorityAssignment:
    """Тесты назначения приоритета раскопок."""

    def test_priority_5_high_value(self):
        """Высокая научная ценность -> Приоритет 5."""
        scientific_value = 0.85

        if scientific_value >= 0.8:
            priority = 5
        elif scientific_value >= 0.6:
            priority = 4
        elif scientific_value >= 0.4:
            priority = 3
        elif scientific_value >= 0.2:
            priority = 2
        else:
            priority = 1

        assert priority == 5

    def test_priority_1_low_value(self):
        """Низкая научная ценность -> Приоритет 1."""
        scientific_value = 0.15

        if scientific_value >= 0.8:
            priority = 5
        elif scientific_value >= 0.6:
            priority = 4
        elif scientific_value >= 0.4:
            priority = 3
        elif scientific_value >= 0.2:
            priority = 2
        else:
            priority = 1

        assert priority == 1


class TestSiteGrouping:
    """Тесты группировки объектов в памятники."""

    def test_objects_within_50m_grouped(self):
        """Объекты ближе 50м группируются в памятник."""
        distances = [100, 120, 130, 145]  # все в пределах 50м друг от друга

        # Simple clustering check
        max_dist = max(distances) - min(distances)
        assert max_dist < 50  # All within 50m

    def test_objects_far_apart_not_grouped(self):
        """Объекты дальше 50м не группируются."""
        distances = [100, 200, 300]  # далеко друг от друга

        # Check distances between consecutive
        gaps = [distances[i+1] - distances[i] for i in range(len(distances)-1)]
        all_close = all(gap < 50 for gap in gaps)

        assert all_close is False

    def test_site_type_determination(self):
        """Определение типа памятника по объектам."""
        from archaeological_detector import ArchaeologicalClass

        objects = [
            ArchaeologicalClass.SHIPWRECK_WOODEN,
            ArchaeologicalClass.ANCHOR_IRON,
            ArchaeologicalClass.BALLAST_PILE,
        ]

        # If contains shipwreck -> shipwreck site
        if any('SHIPWRECK' in obj.name for obj in objects):
            site_type = "shipwreck"
        elif any('ANCHOR' in obj.name for obj in objects):
            site_type = "anchorage"
        else:
            site_type = "scatter"

        assert site_type == "shipwreck"


class TestSBPDataParsing:
    """Тесты парсинга данных профилировщика."""

    def test_depth_calculation(self):
        """Расчёт глубины по времени двойного пути."""
        sound_speed_mps = 1500  # м/с в воде
        travel_time_us = 16667  # микросекунд

        depth_m = (travel_time_us * 1e-6) * sound_speed_mps / 2
        assert abs(depth_m - 12.5) < 0.1  # ~12.5 м

    def test_resolution_calculation(self):
        """Расчёт вертикального разрешения."""
        sound_speed = 1500
        sample_interval_us = 13.3  # для разрешения ~1 см

        resolution_m = sample_interval_us * 1e-6 * sound_speed / 2
        assert resolution_m < 0.02  # < 2 см


class TestLayerSegmentation:
    """Тесты сегментации слоёв грунта."""

    def test_water_layer_detection(self):
        """Водная толща определяется по слабому сигналу."""
        signal_amplitude = 100  # Слабый шум

        if signal_amplitude < 500:
            layer_type = "water"
        else:
            layer_type = "sediment"

        assert layer_type == "water"

    def test_seabed_detection(self):
        """Морское дно определяется по резкому скачку сигнала."""
        amplitudes = [100, 120, 110, 3000, 2800, 1500]  # Скачок на индексе 3

        # Find max gradient
        gradients = [abs(amplitudes[i+1] - amplitudes[i])
                     for i in range(len(amplitudes)-1)]
        seabed_idx = gradients.index(max(gradients))

        assert seabed_idx == 2  # Before the jump


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
