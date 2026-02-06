"""
Hailo-8L Inference Engine для Sub-Bottom Profiler.

Модели для анализа данных профилировщика донного грунта:
- Сегментация слоёв грунта (U-Net)
- Детекция погребённых объектов (YOLOv8)
- Классификация типа грунта (MobileNet)
- Детекция археологических объектов (специализированная)
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

# Hailo Runtime (с fallback на mock)
try:
    from hailo_platform import HEF, VDevice
    HAILO_AVAILABLE = True
except ImportError:
    HAILO_AVAILABLE = False
    logger.warning("Hailo Runtime not available, using mock mode")


class SedimentType(Enum):
    """Типы донных осадков."""

    WATER = 0
    MUD = 1       # Ил
    SAND = 2      # Песок
    CLAY = 3      # Глина
    GRAVEL = 4    # Гравий
    ROCK = 5      # Скала


class ObjectType(Enum):
    """Типы погребённых объектов."""

    UNKNOWN = 0
    PIPE = 1           # Трубопровод
    CABLE = 2          # Кабель
    WRECK = 3          # Обломки судна
    DEBRIS = 4         # Мусор/обломки
    UXO = 5            # Боеприпасы
    ARCHAEOLOGICAL = 6  # Археологический объект
    ANCHOR = 7         # Якорь
    STRUCTURE = 8      # Искусственная структура


@dataclass
class LayerSegment:
    """Сегмент слоя грунта."""

    sediment_type: SedimentType
    depth_start_m: float
    depth_end_m: float
    confidence: float
    acoustic_impedance: float = 0.0

    @property
    def thickness_m(self) -> float:
        """Толщина слоя в метрах."""
        return self.depth_end_m - self.depth_start_m


@dataclass
class DetectedObject:
    """Обнаруженный погребённый объект."""

    object_type: ObjectType
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2 на эхограмме
    depth_m: float                    # Глубина залегания
    distance_m: float                 # Расстояние по профилю
    confidence: float
    size_estimate_m: Tuple[float, float] = (0.0, 0.0)  # width, height
    ping_range: Tuple[int, int] = (0, 0)
    archaeological_probability: float = 0.0  # Вероятность арх. значимости

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь."""
        return {
            "type": self.object_type.name,
            "depth_m": round(self.depth_m, 2),
            "distance_m": round(self.distance_m, 2),
            "confidence": round(self.confidence, 3),
            "size_m": [round(s, 2) for s in self.size_estimate_m],
            "archaeological_probability": round(self.archaeological_probability, 3),
            "bbox": self.bbox,
        }


@dataclass
class SBPAnalysisResult:
    """Результат полного анализа эхограммы."""

    layers: List[LayerSegment]
    objects: List[DetectedObject]
    sediment_classification: Dict[str, float]
    penetration_depth_m: float
    water_depth_m: float
    processing_time_ms: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь."""
        return {
            "layers": [
                {
                    "type": l.sediment_type.name,
                    "depth_start_m": round(l.depth_start_m, 2),
                    "depth_end_m": round(l.depth_end_m, 2),
                    "thickness_m": round(l.thickness_m, 2),
                    "confidence": round(l.confidence, 3),
                }
                for l in self.layers
            ],
            "objects": [o.to_dict() for o in self.objects],
            "sediment_classification": {
                k: round(v, 3) for k, v in self.sediment_classification.items()
            },
            "penetration_depth_m": round(self.penetration_depth_m, 2),
            "water_depth_m": round(self.water_depth_m, 2),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "timestamp": self.timestamp,
        }


class HailoSBPEngine:
    """
    AI движок для анализа данных Sub-Bottom Profiler на Hailo-8L.

    Модели:
    - layer_segmentation.hef: U-Net для сегментации слоёв
    - object_detector.hef: YOLOv8 для детекции объектов
    - sediment_classifier.hef: MobileNet для классификации грунта
    - archaeological_detector.hef: Специализированная модель для археологии
    """

    # Размеры входов моделей
    SEGMENTATION_INPUT_SIZE = (512, 256)  # height, width
    DETECTOR_INPUT_SIZE = (640, 640)
    CLASSIFIER_INPUT_SIZE = (224, 224)

    # Классы сегментации
    SEDIMENT_CLASSES = ["water", "mud", "sand", "clay", "gravel", "rock"]

    # Классы объектов
    OBJECT_CLASSES = [
        "unknown", "pipe", "cable", "wreck", "debris",
        "uxo", "archaeological", "anchor", "structure"
    ]

    def __init__(
        self,
        models_dir: str = "/app/models",
        device_id: int = 0,
    ):
        """
        Инициализация движка.

        Args:
            models_dir: Директория с HEF моделями.
            device_id: ID устройства Hailo.
        """
        self.models_dir = Path(models_dir)
        self.device_id = device_id

        self._device: Optional[Any] = None
        self._segmentation_model: Optional[Any] = None
        self._detector_model: Optional[Any] = None
        self._classifier_model: Optional[Any] = None
        self._archaeological_model: Optional[Any] = None

        self._initialized = False

        # Статистика
        self._inference_count = 0
        self._total_time = 0.0

    async def initialize(self) -> bool:
        """
        Инициализация Hailo и загрузка моделей.

        Returns:
            True если успешно.
        """
        if not HAILO_AVAILABLE:
            logger.info("Running in mock mode (no Hailo hardware)")
            self._initialized = True
            return True

        try:
            self._device = VDevice()
            logger.info(f"Hailo device initialized")

            # Загрузка моделей
            await self._load_models()

            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"Hailo initialization failed: {e}")
            return False

    async def _load_models(self) -> None:
        """Загрузка всех моделей."""
        model_files = {
            "segmentation": "layer_segmentation.hef",
            "detector": "object_detector.hef",
            "classifier": "sediment_classifier.hef",
            "archaeological": "archaeological_detector.hef",
        }

        for name, filename in model_files.items():
            path = self.models_dir / filename
            if path.exists():
                hef = HEF(str(path))
                model = self._device.configure(hef)
                setattr(self, f"_{name}_model", model)
                logger.info(f"Loaded model: {filename}")
            else:
                logger.warning(f"Model not found: {path}")

    async def analyze_echogram(
        self,
        echogram: np.ndarray,
        range_m: float = 50.0,
        ping_interval_m: float = 0.5,
    ) -> SBPAnalysisResult:
        """
        Полный анализ эхограммы.

        Args:
            echogram: 2D массив эхограммы (samples x pings).
            range_m: Максимальная дальность (м).
            ping_interval_m: Расстояние между пингами (м).

        Returns:
            Результат анализа.
        """
        start_time = time.perf_counter()

        # Сегментация слоёв
        layers = await self.segment_layers(echogram, range_m)

        # Детекция объектов
        objects = await self.detect_objects(echogram, range_m, ping_interval_m)

        # Классификация грунта
        sediment_class = await self.classify_sediment(echogram)

        # Определение глубин
        water_depth = layers[0].depth_end_m if layers else 0.0
        penetration = layers[-1].depth_end_m if layers else 0.0

        processing_time = (time.perf_counter() - start_time) * 1000

        self._inference_count += 1
        self._total_time += processing_time

        return SBPAnalysisResult(
            layers=layers,
            objects=objects,
            sediment_classification=sediment_class,
            penetration_depth_m=penetration - water_depth,
            water_depth_m=water_depth,
            processing_time_ms=processing_time,
        )

    async def segment_layers(
        self,
        echogram: np.ndarray,
        range_m: float,
    ) -> List[LayerSegment]:
        """
        Сегментация слоёв грунта.

        Args:
            echogram: Эхограмма (samples x pings).
            range_m: Максимальная дальность.

        Returns:
            Список слоёв.
        """
        if not self._initialized:
            return []

        # Mock режим
        if not HAILO_AVAILABLE or self._segmentation_model is None:
            return self._mock_segment_layers(echogram, range_m)

        try:
            # Предобработка
            input_tensor = self._preprocess_for_segmentation(echogram)

            # Inference
            with self._segmentation_model.activate() as model:
                bindings = model.create_bindings()
                bindings.input().set_buffer(input_tensor)
                model.run([bindings])
                output = bindings.output().get_buffer()

            # Постобработка
            return self._postprocess_segmentation(output, range_m)

        except Exception as e:
            logger.error(f"Segmentation failed: {e}")
            return self._mock_segment_layers(echogram, range_m)

    async def detect_objects(
        self,
        echogram: np.ndarray,
        range_m: float,
        ping_interval_m: float,
    ) -> List[DetectedObject]:
        """
        Детекция погребённых объектов.

        Args:
            echogram: Эхограмма.
            range_m: Дальность.
            ping_interval_m: Расстояние между пингами.

        Returns:
            Список обнаруженных объектов.
        """
        if not self._initialized:
            return []

        # Mock режим
        if not HAILO_AVAILABLE or self._detector_model is None:
            return self._mock_detect_objects(echogram, range_m, ping_interval_m)

        try:
            # Конвертация в RGB-подобный формат
            input_tensor = self._preprocess_for_detection(echogram)

            # Inference
            with self._detector_model.activate() as model:
                bindings = model.create_bindings()
                bindings.input().set_buffer(input_tensor)
                model.run([bindings])
                output = bindings.output().get_buffer()

            # Постобработка
            objects = self._postprocess_detection(
                output, echogram.shape, range_m, ping_interval_m
            )

            # Дополнительная оценка археологической значимости
            for obj in objects:
                obj.archaeological_probability = self._estimate_archaeological_value(obj)

            return objects

        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return self._mock_detect_objects(echogram, range_m, ping_interval_m)

    async def classify_sediment(
        self,
        echogram: np.ndarray,
    ) -> Dict[str, float]:
        """
        Классификация типа грунта.

        Args:
            echogram: Эхограмма.

        Returns:
            Словарь {тип_грунта: вероятность}.
        """
        if not self._initialized:
            return {}

        # Mock режим
        if not HAILO_AVAILABLE or self._classifier_model is None:
            return self._mock_classify_sediment(echogram)

        try:
            input_tensor = self._preprocess_for_classification(echogram)

            with self._classifier_model.activate() as model:
                bindings = model.create_bindings()
                bindings.input().set_buffer(input_tensor)
                model.run([bindings])
                output = bindings.output().get_buffer()

            probabilities = self._softmax(output[0])
            return dict(zip(self.SEDIMENT_CLASSES, probabilities.tolist()))

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return self._mock_classify_sediment(echogram)

    def _estimate_archaeological_value(self, obj: DetectedObject) -> float:
        """
        Оценка археологической значимости объекта.

        Критерии:
        - Глубина залегания (старые объекты глубже)
        - Размер и форма
        - Тип объекта
        - Контекст (окружающие слои)
        """
        score = 0.0

        # Глубина (глубже = потенциально старше)
        if 1.0 <= obj.depth_m <= 3.0:
            score += 0.3  # Неглубокий придонный слой
        elif 3.0 < obj.depth_m <= 8.0:
            score += 0.5  # Средняя глубина
        elif obj.depth_m > 8.0:
            score += 0.7  # Глубокое залегание

        # Тип объекта
        if obj.object_type == ObjectType.WRECK:
            score += 0.4
        elif obj.object_type == ObjectType.ARCHAEOLOGICAL:
            score += 0.8
        elif obj.object_type == ObjectType.ANCHOR:
            score += 0.5
        elif obj.object_type == ObjectType.STRUCTURE:
            score += 0.6

        # Размер (средние объекты более интересны)
        width, height = obj.size_estimate_m
        if 0.5 <= width <= 5.0 and 0.3 <= height <= 3.0:
            score += 0.2

        return min(score, 1.0)

    # ========== Предобработка ==========

    def _preprocess_for_segmentation(self, echogram: np.ndarray) -> np.ndarray:
        """Предобработка для сегментации."""
        import cv2

        # Resize до входного размера модели
        h, w = self.SEGMENTATION_INPUT_SIZE
        resized = cv2.resize(echogram, (w, h))

        # Нормализация
        normalized = resized.astype(np.float32)
        normalized = (normalized - normalized.mean()) / (normalized.std() + 1e-6)

        # NHWC формат с 1 каналом
        return np.expand_dims(np.expand_dims(normalized, axis=0), axis=-1)

    def _preprocess_for_detection(self, echogram: np.ndarray) -> np.ndarray:
        """Предобработка для детекции."""
        import cv2

        h, w = self.DETECTOR_INPUT_SIZE

        # Нормализация в 0-255
        normalized = echogram.astype(np.float32)
        vmin, vmax = np.percentile(normalized, [2, 98])
        normalized = np.clip((normalized - vmin) / (vmax - vmin + 1e-6) * 255, 0, 255)
        normalized = normalized.astype(np.uint8)

        # Resize
        resized = cv2.resize(normalized, (w, h))

        # Конвертация в 3-канальный (псевдо-RGB)
        rgb = np.stack([resized, resized, resized], axis=-1)

        # NHWC uint8
        return np.expand_dims(rgb, axis=0)

    def _preprocess_for_classification(self, echogram: np.ndarray) -> np.ndarray:
        """Предобработка для классификации."""
        import cv2

        h, w = self.CLASSIFIER_INPUT_SIZE

        # Центральный crop
        eh, ew = echogram.shape
        ch, cw = min(eh, ew), min(eh, ew)
        y1, x1 = (eh - ch) // 2, (ew - cw) // 2
        crop = echogram[y1:y1 + ch, x1:x1 + cw]

        # Resize
        resized = cv2.resize(crop, (w, h))

        # Нормализация
        normalized = resized.astype(np.float32) / 255.0

        return np.expand_dims(np.expand_dims(normalized, axis=0), axis=-1)

    # ========== Постобработка ==========

    def _postprocess_segmentation(
        self,
        output: np.ndarray,
        range_m: float,
    ) -> List[LayerSegment]:
        """Постобработка сегментации в слои."""
        # output shape: (1, H, W, num_classes)
        segmentation_map = np.argmax(output[0], axis=-1)  # (H, W)

        # Усреднение по горизонтали для получения профиля слоёв
        vertical_profile = np.median(segmentation_map, axis=1).astype(int)

        layers = []
        current_class = vertical_profile[0]
        start_idx = 0

        for i, cls in enumerate(vertical_profile):
            if cls != current_class or i == len(vertical_profile) - 1:
                depth_start = start_idx / len(vertical_profile) * range_m
                depth_end = i / len(vertical_profile) * range_m

                layers.append(LayerSegment(
                    sediment_type=SedimentType(current_class),
                    depth_start_m=depth_start,
                    depth_end_m=depth_end,
                    confidence=0.8,  # TODO: реальный confidence
                ))

                current_class = cls
                start_idx = i

        return layers

    def _postprocess_detection(
        self,
        output: np.ndarray,
        original_shape: Tuple[int, int],
        range_m: float,
        ping_interval_m: float,
    ) -> List[DetectedObject]:
        """Постобработка детекции объектов."""
        objects = []
        h, w = original_shape
        scale_y = h / self.DETECTOR_INPUT_SIZE[0]
        scale_x = w / self.DETECTOR_INPUT_SIZE[1]

        # Парсинг YOLO output
        for detection in output[0]:
            x, y, box_w, box_h, *class_scores = detection

            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])

            if confidence < 0.3:
                continue

            # Конвертация координат
            x1 = int((x - box_w / 2) * scale_x)
            y1 = int((y - box_h / 2) * scale_y)
            x2 = int((x + box_w / 2) * scale_x)
            y2 = int((y + box_h / 2) * scale_y)

            # Расчёт физических размеров
            depth_m = (y1 + y2) / 2 / h * range_m
            distance_m = (x1 + x2) / 2 * ping_interval_m
            width_m = (x2 - x1) * ping_interval_m
            height_m = (y2 - y1) / h * range_m

            objects.append(DetectedObject(
                object_type=ObjectType(min(class_id, len(ObjectType) - 1)),
                bbox=(x1, y1, x2, y2),
                depth_m=depth_m,
                distance_m=distance_m,
                confidence=confidence,
                size_estimate_m=(width_m, height_m),
                ping_range=(x1, x2),
            ))

        # NMS
        return self._apply_nms(objects, 0.5)

    def _apply_nms(
        self,
        objects: List[DetectedObject],
        threshold: float,
    ) -> List[DetectedObject]:
        """Non-Maximum Suppression для объектов."""
        if not objects:
            return []

        objects = sorted(objects, key=lambda o: o.confidence, reverse=True)
        keep = []

        while objects:
            best = objects.pop(0)
            keep.append(best)

            objects = [
                o for o in objects
                if self._iou(best.bbox, o.bbox) < threshold
            ]

        return keep

    @staticmethod
    def _iou(box1: Tuple, box2: Tuple) -> float:
        """Intersection over Union."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Softmax функция."""
        exp_x = np.exp(x - np.max(x))
        return exp_x / exp_x.sum()

    # ========== Mock методы ==========

    def _mock_segment_layers(
        self,
        echogram: np.ndarray,
        range_m: float,
    ) -> List[LayerSegment]:
        """Mock сегментация слоёв."""
        return [
            LayerSegment(SedimentType.WATER, 0.0, 12.5, 0.95),
            LayerSegment(SedimentType.MUD, 12.5, 15.8, 0.85),
            LayerSegment(SedimentType.SAND, 15.8, 21.2, 0.78),
            LayerSegment(SedimentType.CLAY, 21.2, 26.5, 0.72),
            LayerSegment(SedimentType.ROCK, 26.5, range_m, 0.88),
        ]

    def _mock_detect_objects(
        self,
        echogram: np.ndarray,
        range_m: float,
        ping_interval_m: float,
    ) -> List[DetectedObject]:
        """Mock детекция объектов."""
        h, w = echogram.shape
        objects = []

        # Поиск аномалий (упрощённо)
        threshold = np.percentile(echogram, 95)
        anomalies = echogram > threshold

        # Группировка аномалий (простой алгоритм)
        if np.any(anomalies):
            # Находим центр масс аномалий
            y_coords, x_coords = np.where(anomalies)
            if len(y_coords) > 10:
                y_center = int(np.mean(y_coords))
                x_center = int(np.mean(x_coords))

                # Оценка размеров
                y_min, y_max = y_coords.min(), y_coords.max()
                x_min, x_max = x_coords.min(), x_coords.max()

                depth_m = y_center / h * range_m
                distance_m = x_center * ping_interval_m

                obj = DetectedObject(
                    object_type=ObjectType.ARCHAEOLOGICAL,
                    bbox=(x_min, y_min, x_max, y_max),
                    depth_m=depth_m,
                    distance_m=distance_m,
                    confidence=0.75,
                    size_estimate_m=(
                        (x_max - x_min) * ping_interval_m,
                        (y_max - y_min) / h * range_m
                    ),
                    ping_range=(x_min, x_max),
                )
                obj.archaeological_probability = self._estimate_archaeological_value(obj)
                objects.append(obj)

        return objects

    def _mock_classify_sediment(self, echogram: np.ndarray) -> Dict[str, float]:
        """Mock классификация грунта."""
        # Простая эвристика на основе статистики сигнала
        mean_val = np.mean(echogram)
        std_val = np.std(echogram)

        if std_val < 200:
            return {"mud": 0.6, "clay": 0.25, "sand": 0.1, "gravel": 0.03, "rock": 0.02}
        elif std_val < 500:
            return {"sand": 0.5, "mud": 0.25, "clay": 0.15, "gravel": 0.07, "rock": 0.03}
        else:
            return {"gravel": 0.4, "rock": 0.3, "sand": 0.2, "clay": 0.07, "mud": 0.03}

    @property
    def stats(self) -> Dict[str, Any]:
        """Статистика inference."""
        avg_time = self._total_time / self._inference_count if self._inference_count > 0 else 0
        return {
            "inference_count": self._inference_count,
            "total_time_ms": round(self._total_time, 2),
            "avg_time_ms": round(avg_time, 2),
            "fps": round(1000 / avg_time, 1) if avg_time > 0 else 0,
        }

    async def shutdown(self) -> None:
        """Освобождение ресурсов."""
        self._device = None
        self._segmentation_model = None
        self._detector_model = None
        self._classifier_model = None
        self._initialized = False
        logger.info("Hailo SBP engine shutdown")
