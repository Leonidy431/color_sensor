"""
Data Fusion Module.

Объединяет данные визуальной детекции (Hailo) и
спектрального анализа цвета (AS7262) для комплексной
идентификации рыб.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from .hailo_inference import Detection, ClassificationResult


@dataclass
class ColorData:
    """Данные анализа цвета от AS7262."""

    spectrum: Dict[str, float]  # Спектральные значения
    rgb: Tuple[int, int, int]   # RGB представление
    hsv: Tuple[float, float, float]  # HSV
    lab: Tuple[float, float, float]  # CIE L*a*b*
    dominant_hue: float         # Доминирующий оттенок
    saturation: float           # Насыщенность
    freshness_score: float      # Индекс свежести
    color_class: str            # Классификация цвета
    timestamp: float = field(default_factory=time.time)


@dataclass
class FusedResult:
    """Результат слияния данных от всех сенсоров."""

    # Идентификация
    fish_detected: bool
    species_id: Optional[int]
    species_name: Optional[str]
    species_confidence: float

    # Визуальные данные
    detection: Optional[Detection]
    classification: Optional[ClassificationResult]

    # Цветовые данные
    color: Optional[ColorData]
    color_match_score: float

    # Состояние
    freshness: str
    freshness_score: float

    # Метаданные
    fused_confidence: float
    processing_time_ms: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для JSON."""
        return {
            "fish_detected": self.fish_detected,
            "species": {
                "id": self.species_id,
                "name": self.species_name,
                "confidence": round(self.species_confidence, 3),
            },
            "detection": {
                "bbox": self.detection.bbox if self.detection else None,
                "confidence": self.detection.confidence if self.detection else 0,
            },
            "color": {
                "rgb": self.color.rgb if self.color else None,
                "hsv": {
                    "h": round(self.color.hsv[0], 1) if self.color else 0,
                    "s": round(self.color.hsv[1], 3) if self.color else 0,
                    "v": round(self.color.hsv[2], 3) if self.color else 0,
                },
                "class": self.color.color_class if self.color else None,
                "match_score": round(self.color_match_score, 3),
            },
            "freshness": {
                "status": self.freshness,
                "score": round(self.freshness_score, 3),
            },
            "confidence": round(self.fused_confidence, 3),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class SpeciesColorProfile:
    """Цветовой профиль вида рыбы."""

    species_id: int
    species_name: str
    hue_range: Tuple[float, float]
    saturation_range: Tuple[float, float]
    is_iridescent: bool
    pattern: str


class DataFusionEngine:
    """
    Движок слияния данных.

    Объединяет результаты детекции, классификации и
    анализа цвета для точной идентификации рыб.
    """

    def __init__(
        self,
        species_profiles: Optional[List[SpeciesColorProfile]] = None,
        visual_weight: float = 0.7,
        color_weight: float = 0.3,
    ):
        """
        Инициализация движка слияния.

        Args:
            species_profiles: Цветовые профили видов рыб.
            visual_weight: Вес визуальной классификации.
            color_weight: Вес цветового анализа.
        """
        self.species_profiles = species_profiles or []
        self.visual_weight = visual_weight
        self.color_weight = color_weight

        # Кэш результатов
        self._last_detection: Optional[Detection] = None
        self._last_color: Optional[ColorData] = None

        # Параметры временного выравнивания
        self.max_time_diff_ms = 100  # Максимальная разница timestamps

    def add_species_profile(self, profile: SpeciesColorProfile) -> None:
        """Добавление цветового профиля вида."""
        self.species_profiles.append(profile)

    async def fuse(
        self,
        detection: Optional[Detection],
        classification: Optional[ClassificationResult],
        color: Optional[ColorData],
    ) -> FusedResult:
        """
        Слияние данных от всех источников.

        Args:
            detection: Результат детекции.
            classification: Результат классификации.
            color: Данные анализа цвета.

        Returns:
            Объединённый результат.
        """
        start_time = time.perf_counter()

        # Проверка наличия рыбы
        fish_detected = (
            detection is not None and
            detection.class_name == "fish" and
            detection.confidence > 0.5
        )

        if not fish_detected:
            return FusedResult(
                fish_detected=False,
                species_id=None,
                species_name=None,
                species_confidence=0.0,
                detection=detection,
                classification=None,
                color=color,
                color_match_score=0.0,
                freshness="unknown",
                freshness_score=0.0,
                fused_confidence=0.0,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Базовая классификация
        species_id = classification.class_id if classification else None
        species_name = classification.class_name if classification else "Unknown"
        visual_confidence = classification.confidence if classification else 0.0

        # Сопоставление цвета с профилем вида
        color_match_score = 0.0
        if color and species_id is not None:
            color_match_score = self._match_color_to_species(color, species_id)

        # Уточнение классификации по цвету
        if color and color_match_score < 0.4:
            # Низкое совпадение - попробовать найти лучший match
            best_match = self._find_best_species_by_color(color)
            if best_match and best_match[1] > color_match_score + 0.2:
                species_id = best_match[0].species_id
                species_name = best_match[0].species_name
                color_match_score = best_match[1]
                logger.debug(f"Species refined by color: {species_name}")

        # Слияние confidence
        fused_confidence = (
            self.visual_weight * visual_confidence +
            self.color_weight * color_match_score
        )

        # Оценка свежести
        freshness, freshness_score = self._assess_freshness(color)

        processing_time = (time.perf_counter() - start_time) * 1000

        return FusedResult(
            fish_detected=True,
            species_id=species_id,
            species_name=species_name,
            species_confidence=visual_confidence,
            detection=detection,
            classification=classification,
            color=color,
            color_match_score=color_match_score,
            freshness=freshness,
            freshness_score=freshness_score,
            fused_confidence=fused_confidence,
            processing_time_ms=processing_time,
        )

    def _match_color_to_species(
        self,
        color: ColorData,
        species_id: int,
    ) -> float:
        """
        Сопоставление цвета с профилем вида.

        Returns:
            Оценка совпадения (0-1).
        """
        profile = next(
            (p for p in self.species_profiles if p.species_id == species_id),
            None
        )

        if not profile:
            return 0.5  # Нет профиля - нейтральная оценка

        score = 0.0
        weights_sum = 0.0

        # Проверка оттенка (hue)
        hue = color.dominant_hue
        hue_min, hue_max = profile.hue_range

        # Обработка wraparound для hue (0-360)
        if hue_min > hue_max:  # Например (330, 30) для красного
            hue_in_range = hue >= hue_min or hue <= hue_max
        else:
            hue_in_range = hue_min <= hue <= hue_max

        if hue_in_range:
            score += 0.5
        else:
            # Частичное совпадение
            if hue_min > hue_max:
                dist = min(
                    abs(hue - hue_min),
                    abs(hue - hue_max),
                    abs(hue - (hue_min - 360)),
                    abs(hue - (hue_max + 360))
                )
            else:
                dist = min(abs(hue - hue_min), abs(hue - hue_max))
            score += max(0, 0.5 - dist / 60)

        weights_sum += 0.5

        # Проверка насыщенности
        sat = color.saturation
        sat_min, sat_max = profile.saturation_range

        if sat_min <= sat <= sat_max:
            score += 0.3
        else:
            dist = min(abs(sat - sat_min), abs(sat - sat_max))
            score += max(0, 0.3 - dist)

        weights_sum += 0.3

        # Бонус за иридесценцию
        if profile.is_iridescent and sat > 0.4:
            score += 0.2
        elif not profile.is_iridescent and sat < 0.3:
            score += 0.1

        weights_sum += 0.2

        return min(score / weights_sum, 1.0) if weights_sum > 0 else 0.5

    def _find_best_species_by_color(
        self,
        color: ColorData,
    ) -> Optional[Tuple[SpeciesColorProfile, float]]:
        """Поиск лучшего совпадения вида по цвету."""
        best_match = None
        best_score = 0.0

        for profile in self.species_profiles:
            score = self._match_color_to_species(color, profile.species_id)
            if score > best_score:
                best_score = score
                best_match = (profile, score)

        return best_match if best_score > 0.5 else None

    def _assess_freshness(
        self,
        color: Optional[ColorData],
    ) -> Tuple[str, float]:
        """Оценка свежести по цветовым данным."""
        if not color:
            return ("unknown", 0.0)

        score = color.freshness_score

        if score >= 0.6:
            status = "fresh"
        elif score >= 0.4:
            status = "acceptable"
        else:
            status = "spoiled"

        return (status, score)

    def update_detection(self, detection: Detection) -> None:
        """Обновление последней детекции."""
        self._last_detection = detection

    def update_color(self, color: ColorData) -> None:
        """Обновление последних данных цвета."""
        self._last_color = color

    async def get_latest_fusion(self) -> Optional[FusedResult]:
        """Получение слияния последних данных."""
        if not self._last_detection:
            return None

        return await self.fuse(
            self._last_detection,
            None,  # Classification from detection
            self._last_color,
        )
