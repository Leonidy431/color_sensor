"""
Детектор археологических объектов в придонных слоях.

Специализированный модуль для обнаружения и классификации
археологически значимых объектов по данным профилировщика.

Поддерживаемые классы объектов:
- Затонувшие суда и их фрагменты
- Якоря и цепи
- Амфоры и керамика
- Каменные структуры (причалы, молы)
- Деревянные конструкции (сваи, обшивка)
- Металлические артефакты
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger


class ArchaeologicalClass(Enum):
    """Классы археологических объектов."""

    UNKNOWN = 0
    SHIPWRECK_WOODEN = 1      # Деревянное судно
    SHIPWRECK_METAL = 2       # Металлическое судно
    SHIPWRECK_FRAGMENT = 3    # Фрагмент судна
    ANCHOR_STONE = 4          # Каменный якорь
    ANCHOR_IRON = 5           # Железный якорь
    ANCHOR_ADMIRALTY = 6      # Адмиралтейский якорь
    AMPHORA = 7               # Амфора
    CERAMIC_CLUSTER = 8       # Скопление керамики
    STONE_STRUCTURE = 9       # Каменная структура
    WOODEN_STRUCTURE = 10     # Деревянная структура (сваи)
    BALLAST_PILE = 11         # Балластная куча
    CARGO_SCATTER = 12        # Россыпь груза
    CANNON = 13               # Пушка
    METAL_ARTIFACT = 14       # Металлический артефакт


class HistoricalPeriod(Enum):
    """Предполагаемый исторический период."""

    UNKNOWN = 0
    ANCIENT = 1        # Античность (до 500 н.э.)
    MEDIEVAL = 2       # Средневековье (500-1500)
    EARLY_MODERN = 3   # Раннее новое время (1500-1800)
    MODERN = 4         # Новое время (1800-1950)
    CONTEMPORARY = 5   # Современный период (после 1950)


@dataclass
class ArchaeologicalObject:
    """
    Археологический объект, обнаруженный на эхограмме.

    Содержит детальную информацию для археологической оценки.
    """

    # Идентификация
    object_id: str
    object_class: ArchaeologicalClass
    confidence: float

    # Местоположение
    depth_below_seabed_m: float  # Глубина под дном
    water_depth_m: float         # Глубина воды
    distance_along_track_m: float
    position_wgs84: Optional[Tuple[float, float]] = None  # lat, lon

    # Размеры
    length_m: float = 0.0
    width_m: float = 0.0
    height_m: float = 0.0

    # Акустические характеристики
    acoustic_signature: str = ""  # Описание сигнатуры
    reflection_strength_db: float = 0.0
    shadow_length_m: float = 0.0

    # Оценки
    historical_period: HistoricalPeriod = HistoricalPeriod.UNKNOWN
    preservation_estimate: str = "unknown"  # good, moderate, poor
    scientific_value: float = 0.0  # 0-1
    excavation_priority: int = 0   # 1-5 (5 = высший)

    # Связанные объекты
    associated_objects: List[str] = field(default_factory=list)

    # Метаданные
    detection_timestamp: float = field(default_factory=time.time)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь."""
        return {
            "id": self.object_id,
            "class": self.object_class.name,
            "confidence": round(self.confidence, 3),
            "location": {
                "depth_below_seabed_m": round(self.depth_below_seabed_m, 2),
                "water_depth_m": round(self.water_depth_m, 2),
                "distance_m": round(self.distance_along_track_m, 2),
                "coordinates": self.position_wgs84,
            },
            "dimensions": {
                "length_m": round(self.length_m, 2),
                "width_m": round(self.width_m, 2),
                "height_m": round(self.height_m, 2),
            },
            "acoustics": {
                "signature": self.acoustic_signature,
                "reflection_db": round(self.reflection_strength_db, 1),
                "shadow_m": round(self.shadow_length_m, 2),
            },
            "assessment": {
                "period": self.historical_period.name,
                "preservation": self.preservation_estimate,
                "scientific_value": round(self.scientific_value, 2),
                "priority": self.excavation_priority,
            },
            "associated_objects": self.associated_objects,
            "notes": self.notes,
        }


@dataclass
class ArchaeologicalSite:
    """
    Археологический памятник (комплекс объектов).
    """

    site_id: str
    name: str
    objects: List[ArchaeologicalObject]
    center_position: Optional[Tuple[float, float]] = None
    extent_m: Tuple[float, float] = (0.0, 0.0)  # length x width
    site_type: str = "unknown"  # shipwreck, settlement, anchorage, etc.
    estimated_period: HistoricalPeriod = HistoricalPeriod.UNKNOWN
    total_scientific_value: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь."""
        return {
            "site_id": self.site_id,
            "name": self.name,
            "type": self.site_type,
            "period": self.estimated_period.name,
            "center": self.center_position,
            "extent_m": self.extent_m,
            "object_count": len(self.objects),
            "scientific_value": round(self.total_scientific_value, 2),
            "objects": [obj.to_dict() for obj in self.objects],
        }


class ArchaeologicalDetector:
    """
    Детектор и классификатор археологических объектов.

    Использует комбинацию AI-детекции и правил для
    идентификации археологически значимых объектов.
    """

    # Акустические сигнатуры типичных объектов
    ACOUSTIC_SIGNATURES = {
        ArchaeologicalClass.SHIPWRECK_WOODEN: {
            "reflection_range_db": (-10, 5),
            "typical_size_m": (5, 50),
            "shadow": True,
            "layered": True,
        },
        ArchaeologicalClass.SHIPWRECK_METAL: {
            "reflection_range_db": (5, 20),
            "typical_size_m": (10, 200),
            "shadow": True,
            "layered": False,
        },
        ArchaeologicalClass.ANCHOR_IRON: {
            "reflection_range_db": (0, 15),
            "typical_size_m": (1, 5),
            "shadow": True,
            "layered": False,
        },
        ArchaeologicalClass.AMPHORA: {
            "reflection_range_db": (-5, 5),
            "typical_size_m": (0.3, 1.5),
            "shadow": False,
            "layered": False,
        },
        ArchaeologicalClass.STONE_STRUCTURE: {
            "reflection_range_db": (5, 15),
            "typical_size_m": (2, 100),
            "shadow": True,
            "layered": True,
        },
        ArchaeologicalClass.BALLAST_PILE: {
            "reflection_range_db": (0, 10),
            "typical_size_m": (3, 20),
            "shadow": False,
            "layered": False,
        },
    }

    # Характерные глубины залегания по периодам
    PERIOD_DEPTH_RANGES = {
        HistoricalPeriod.ANCIENT: (2.0, 15.0),      # Античные объекты глубже
        HistoricalPeriod.MEDIEVAL: (1.0, 8.0),
        HistoricalPeriod.EARLY_MODERN: (0.5, 5.0),
        HistoricalPeriod.MODERN: (0.0, 3.0),
        HistoricalPeriod.CONTEMPORARY: (0.0, 1.0),
    }

    def __init__(self):
        """Инициализация детектора."""
        self._detected_objects: List[ArchaeologicalObject] = []
        self._sites: List[ArchaeologicalSite] = []
        self._object_counter = 0

    def analyze_detections(
        self,
        detections: List[Dict[str, Any]],
        water_depth_m: float,
        track_position: Optional[Tuple[float, float]] = None,
    ) -> List[ArchaeologicalObject]:
        """
        Анализ детекций и классификация археологических объектов.

        Args:
            detections: Список детекций от Hailo (object_type, bbox, confidence, etc.)
            water_depth_m: Глубина воды.
            track_position: Текущая позиция (lat, lon).

        Returns:
            Список археологических объектов.
        """
        archaeological_objects = []

        for det in detections:
            # Проверка на археологическую значимость
            if det.get("archaeological_probability", 0) < 0.3:
                continue

            # Создание объекта
            obj = self._create_archaeological_object(det, water_depth_m, track_position)

            # Классификация по акустическим признакам
            obj = self._classify_by_acoustics(obj, det)

            # Оценка исторического периода
            obj.historical_period = self._estimate_period(obj)

            # Оценка научной ценности
            obj.scientific_value = self._calculate_scientific_value(obj)

            # Приоритет раскопок
            obj.excavation_priority = self._assign_priority(obj)

            archaeological_objects.append(obj)
            self._detected_objects.append(obj)

        # Группировка в памятники
        self._update_sites()

        return archaeological_objects

    def _create_archaeological_object(
        self,
        detection: Dict[str, Any],
        water_depth_m: float,
        track_position: Optional[Tuple[float, float]],
    ) -> ArchaeologicalObject:
        """Создание археологического объекта из детекции."""
        self._object_counter += 1
        obj_id = f"AO-{self._object_counter:06d}"

        depth_m = detection.get("depth_m", 0)
        size = detection.get("size_m", (1.0, 1.0))

        return ArchaeologicalObject(
            object_id=obj_id,
            object_class=ArchaeologicalClass.UNKNOWN,
            confidence=detection.get("confidence", 0.5),
            depth_below_seabed_m=max(0, depth_m - water_depth_m),
            water_depth_m=water_depth_m,
            distance_along_track_m=detection.get("distance_m", 0),
            position_wgs84=track_position,
            length_m=size[0],
            width_m=size[0] * 0.5,  # Приблизительно
            height_m=size[1],
        )

    def _classify_by_acoustics(
        self,
        obj: ArchaeologicalObject,
        detection: Dict[str, Any],
    ) -> ArchaeologicalObject:
        """Классификация объекта по акустическим характеристикам."""
        # Получение акустических параметров
        reflection_db = detection.get("reflection_db", 0)
        has_shadow = detection.get("has_shadow", False)
        size = (obj.length_m, obj.height_m)

        best_match = ArchaeologicalClass.UNKNOWN
        best_score = 0.0

        for obj_class, signature in self.ACOUSTIC_SIGNATURES.items():
            score = 0.0

            # Проверка отражения
            ref_min, ref_max = signature["reflection_range_db"]
            if ref_min <= reflection_db <= ref_max:
                score += 0.3

            # Проверка размера
            size_min, size_max = signature["typical_size_m"]
            if size_min <= obj.length_m <= size_max:
                score += 0.3

            # Проверка тени
            if signature["shadow"] == has_shadow:
                score += 0.2

            # Проверка глубины (неглубокие придонные слои)
            if obj.depth_below_seabed_m <= 5.0:
                score += 0.2

            if score > best_score:
                best_score = score
                best_match = obj_class

        obj.object_class = best_match
        obj.acoustic_signature = self._describe_signature(obj, detection)
        obj.reflection_strength_db = reflection_db

        return obj

    def _describe_signature(
        self,
        obj: ArchaeologicalObject,
        detection: Dict[str, Any],
    ) -> str:
        """Текстовое описание акустической сигнатуры."""
        parts = []

        ref_db = detection.get("reflection_db", 0)
        if ref_db > 10:
            parts.append("сильное отражение")
        elif ref_db > 0:
            parts.append("умеренное отражение")
        else:
            parts.append("слабое отражение")

        if detection.get("has_shadow"):
            parts.append("акустическая тень")

        if obj.depth_below_seabed_m > 2:
            parts.append("глубокое залегание")
        else:
            parts.append("поверхностное залегание")

        return ", ".join(parts)

    def _estimate_period(self, obj: ArchaeologicalObject) -> HistoricalPeriod:
        """Оценка исторического периода по глубине залегания."""
        depth = obj.depth_below_seabed_m

        for period, (min_d, max_d) in self.PERIOD_DEPTH_RANGES.items():
            if min_d <= depth <= max_d:
                return period

        return HistoricalPeriod.UNKNOWN

    def _calculate_scientific_value(self, obj: ArchaeologicalObject) -> float:
        """Расчёт научной ценности объекта."""
        value = 0.0

        # Редкость типа объекта
        rarity_scores = {
            ArchaeologicalClass.SHIPWRECK_WOODEN: 0.9,
            ArchaeologicalClass.AMPHORA: 0.8,
            ArchaeologicalClass.ANCHOR_STONE: 0.85,
            ArchaeologicalClass.CANNON: 0.75,
            ArchaeologicalClass.STONE_STRUCTURE: 0.7,
            ArchaeologicalClass.BALLAST_PILE: 0.5,
        }
        value += rarity_scores.get(obj.object_class, 0.3)

        # Древность
        period_scores = {
            HistoricalPeriod.ANCIENT: 0.5,
            HistoricalPeriod.MEDIEVAL: 0.4,
            HistoricalPeriod.EARLY_MODERN: 0.3,
            HistoricalPeriod.MODERN: 0.1,
        }
        value += period_scores.get(obj.historical_period, 0.0)

        # Размер (крупные объекты обычно важнее)
        if obj.length_m > 10:
            value += 0.2
        elif obj.length_m > 3:
            value += 0.1

        # Confidence детекции
        value *= obj.confidence

        return min(value, 1.0)

    def _assign_priority(self, obj: ArchaeologicalObject) -> int:
        """Назначение приоритета раскопок (1-5)."""
        if obj.scientific_value >= 0.8:
            return 5
        elif obj.scientific_value >= 0.6:
            return 4
        elif obj.scientific_value >= 0.4:
            return 3
        elif obj.scientific_value >= 0.2:
            return 2
        else:
            return 1

    def _update_sites(self) -> None:
        """Обновление группировки объектов в памятники."""
        # Простая кластеризация по расстоянию
        clustered = []
        used = set()

        for i, obj in enumerate(self._detected_objects):
            if i in used:
                continue

            cluster = [obj]
            used.add(i)

            for j, other in enumerate(self._detected_objects):
                if j in used:
                    continue

                # Проверка расстояния (50м порог)
                dist = abs(obj.distance_along_track_m - other.distance_along_track_m)
                if dist < 50:
                    cluster.append(other)
                    used.add(j)

            if len(cluster) >= 2:
                clustered.append(cluster)

        # Создание памятников
        self._sites = []
        for i, cluster in enumerate(clustered):
            site = ArchaeologicalSite(
                site_id=f"AS-{i + 1:04d}",
                name=f"Памятник {i + 1}",
                objects=cluster,
                site_type=self._determine_site_type(cluster),
                estimated_period=self._most_common_period(cluster),
                total_scientific_value=sum(o.scientific_value for o in cluster) / len(cluster),
            )
            self._sites.append(site)

    def _determine_site_type(self, objects: List[ArchaeologicalObject]) -> str:
        """Определение типа памятника."""
        classes = [obj.object_class for obj in objects]

        if ArchaeologicalClass.SHIPWRECK_WOODEN in classes or \
           ArchaeologicalClass.SHIPWRECK_METAL in classes:
            return "shipwreck"
        elif ArchaeologicalClass.STONE_STRUCTURE in classes:
            return "settlement"
        elif ArchaeologicalClass.ANCHOR_IRON in classes or \
             ArchaeologicalClass.ANCHOR_STONE in classes:
            return "anchorage"
        else:
            return "scatter"

    def _most_common_period(
        self,
        objects: List[ArchaeologicalObject],
    ) -> HistoricalPeriod:
        """Наиболее частый период среди объектов."""
        from collections import Counter
        periods = [obj.historical_period for obj in objects]
        if not periods:
            return HistoricalPeriod.UNKNOWN
        return Counter(periods).most_common(1)[0][0]

    def get_all_objects(self) -> List[ArchaeologicalObject]:
        """Получение всех обнаруженных объектов."""
        return self._detected_objects

    def get_sites(self) -> List[ArchaeologicalSite]:
        """Получение всех памятников."""
        return self._sites

    def generate_report(self) -> Dict[str, Any]:
        """Генерация отчёта об обнаруженных объектах."""
        return {
            "summary": {
                "total_objects": len(self._detected_objects),
                "total_sites": len(self._sites),
                "high_priority_count": sum(
                    1 for o in self._detected_objects if o.excavation_priority >= 4
                ),
            },
            "objects_by_class": self._count_by_class(),
            "objects_by_period": self._count_by_period(),
            "sites": [s.to_dict() for s in self._sites],
            "objects": [o.to_dict() for o in self._detected_objects],
        }

    def _count_by_class(self) -> Dict[str, int]:
        """Подсчёт объектов по классам."""
        from collections import Counter
        classes = [obj.object_class.name for obj in self._detected_objects]
        return dict(Counter(classes))

    def _count_by_period(self) -> Dict[str, int]:
        """Подсчёт объектов по периодам."""
        from collections import Counter
        periods = [obj.historical_period.name for obj in self._detected_objects]
        return dict(Counter(periods))
