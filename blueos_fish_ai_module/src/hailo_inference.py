"""
Hailo-8L Inference Engine.

Обеспечивает высокопроизводительный inference на NPU Hailo-8L
для детекции и классификации рыб.
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

# Hailo Runtime (опционально, с fallback на mock)
try:
    from hailo_platform import (
        ConfiguredInferModel,
        HEF,
        VDevice,
        HailoStreamInterface,
        FormatType,
    )
    HAILO_AVAILABLE = True
except ImportError:
    HAILO_AVAILABLE = False
    logger.warning("Hailo Runtime not available, using mock mode")


@dataclass
class Detection:
    """Результат детекции объекта."""

    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    class_id: int
    class_name: str
    confidence: float
    timestamp: float = field(default_factory=time.time)

    @property
    def center(self) -> Tuple[int, int]:
        """Центр bounding box."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def area(self) -> int:
        """Площадь bounding box."""
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)


@dataclass
class ClassificationResult:
    """Результат классификации."""

    class_id: int
    class_name: str
    confidence: float
    top_k: List[Tuple[int, str, float]] = field(default_factory=list)


class HailoInferenceEngine:
    """
    Движок inference для Hailo-8L NPU.

    Поддерживает асинхронный inference для детекции (YOLO)
    и классификации (MobileNet/ResNet) моделей.

    Attributes:
        device: VDevice объект Hailo.
        detector_model: Загруженная модель детекции.
        classifier_model: Загруженная модель классификации.
    """

    def __init__(
        self,
        detector_path: Optional[str] = None,
        classifier_path: Optional[str] = None,
        device_id: int = 0,
    ):
        """
        Инициализация Hailo engine.

        Args:
            detector_path: Путь к HEF модели детектора.
            classifier_path: Путь к HEF модели классификатора.
            device_id: ID устройства Hailo (0 по умолчанию).
        """
        self.device_id = device_id
        self.detector_path = detector_path
        self.classifier_path = classifier_path

        self._device: Optional[Any] = None
        self._detector: Optional[Any] = None
        self._classifier: Optional[Any] = None
        self._initialized = False

        # Классы детекции
        self.detection_classes = ["fish", "not_fish"]

        # Классы классификации (загружаются из конфига)
        self.classification_classes: List[str] = []

        # Статистика
        self._inference_count = 0
        self._total_inference_time = 0.0

    async def initialize(self) -> bool:
        """
        Асинхронная инициализация движка.

        Returns:
            True если инициализация успешна.
        """
        if not HAILO_AVAILABLE:
            logger.info("Running in mock mode (no Hailo hardware)")
            self._initialized = True
            return True

        try:
            # Создание виртуального устройства
            self._device = VDevice()
            logger.info(f"Hailo device initialized: {self._device}")

            # Загрузка модели детекции
            if self.detector_path and Path(self.detector_path).exists():
                hef = HEF(self.detector_path)
                self._detector = self._device.configure(hef)
                logger.info(f"Detector model loaded: {self.detector_path}")

            # Загрузка модели классификации
            if self.classifier_path and Path(self.classifier_path).exists():
                hef = HEF(self.classifier_path)
                self._classifier = self._device.configure(hef)
                logger.info(f"Classifier model loaded: {self.classifier_path}")

            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Hailo: {e}")
            return False

    async def detect(
        self,
        frame: np.ndarray,
        confidence_threshold: float = 0.5,
        nms_threshold: float = 0.45,
    ) -> List[Detection]:
        """
        Детекция рыб на изображении.

        Args:
            frame: Входное изображение (BGR, HWC).
            confidence_threshold: Порог уверенности.
            nms_threshold: Порог NMS.

        Returns:
            Список детекций.
        """
        if not self._initialized:
            return []

        start_time = time.perf_counter()

        # Mock режим для тестирования
        if not HAILO_AVAILABLE or self._detector is None:
            return self._mock_detect(frame, confidence_threshold)

        try:
            # Предобработка
            input_tensor = self._preprocess_detection(frame)

            # Inference
            with self._detector.activate() as infer_model:
                bindings = infer_model.create_bindings()
                bindings.input().set_buffer(input_tensor)

                infer_model.wait_for_async_ready(timeout_ms=100)
                infer_model.run([bindings])

                output = bindings.output().get_buffer()

            # Постобработка
            detections = self._postprocess_detection(
                output, frame.shape, confidence_threshold, nms_threshold
            )

            # Статистика
            inference_time = time.perf_counter() - start_time
            self._inference_count += 1
            self._total_inference_time += inference_time

            return detections

        except Exception as e:
            logger.error(f"Detection inference failed: {e}")
            return []

    async def classify(
        self,
        image: np.ndarray,
        top_k: int = 5,
    ) -> Optional[ClassificationResult]:
        """
        Классификация вида рыбы.

        Args:
            image: Изображение рыбы (обрезанное по bbox).
            top_k: Количество top-K результатов.

        Returns:
            Результат классификации или None.
        """
        if not self._initialized:
            return None

        # Mock режим
        if not HAILO_AVAILABLE or self._classifier is None:
            return self._mock_classify(image, top_k)

        try:
            # Предобработка
            input_tensor = self._preprocess_classification(image)

            # Inference
            with self._classifier.activate() as infer_model:
                bindings = infer_model.create_bindings()
                bindings.input().set_buffer(input_tensor)

                infer_model.run([bindings])
                output = bindings.output().get_buffer()

            # Постобработка
            return self._postprocess_classification(output, top_k)

        except Exception as e:
            logger.error(f"Classification inference failed: {e}")
            return None

    def _preprocess_detection(self, frame: np.ndarray) -> np.ndarray:
        """Предобработка для детекции (YOLO)."""
        import cv2

        # Resize до 640x640
        resized = cv2.resize(frame, (640, 640))

        # BGR -> RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        # HWC -> NHWC, uint8
        return np.expand_dims(rgb, axis=0).astype(np.uint8)

    def _preprocess_classification(self, image: np.ndarray) -> np.ndarray:
        """Предобработка для классификации."""
        import cv2

        # Resize до 224x224
        resized = cv2.resize(image, (224, 224))

        # BGR -> RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        # Нормализация
        normalized = rgb.astype(np.float32) / 255.0

        # NHWC
        return np.expand_dims(normalized, axis=0)

    def _postprocess_detection(
        self,
        output: np.ndarray,
        original_shape: Tuple[int, ...],
        conf_threshold: float,
        nms_threshold: float,
    ) -> List[Detection]:
        """Постобработка YOLO выхода."""
        detections = []
        h, w = original_shape[:2]
        scale_x, scale_y = w / 640, h / 640

        # Парсинг YOLO output (зависит от версии модели)
        # Упрощённая версия для YOLOv8
        for detection in output[0]:
            x, y, w_box, h_box, *class_scores = detection

            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])

            if confidence < conf_threshold:
                continue

            # Конвертация в x1, y1, x2, y2
            x1 = int((x - w_box / 2) * scale_x)
            y1 = int((y - h_box / 2) * scale_y)
            x2 = int((x + w_box / 2) * scale_x)
            y2 = int((y + h_box / 2) * scale_y)

            detections.append(Detection(
                bbox=(x1, y1, x2, y2),
                class_id=class_id,
                class_name=self.detection_classes[class_id],
                confidence=confidence,
            ))

        # NMS
        return self._apply_nms(detections, nms_threshold)

    def _postprocess_classification(
        self,
        output: np.ndarray,
        top_k: int,
    ) -> ClassificationResult:
        """Постобработка классификации."""
        probabilities = self._softmax(output[0])
        top_indices = np.argsort(probabilities)[-top_k:][::-1]

        top_k_results = [
            (int(idx), self.classification_classes[idx], float(probabilities[idx]))
            for idx in top_indices
            if idx < len(self.classification_classes)
        ]

        best_idx = top_indices[0]
        return ClassificationResult(
            class_id=int(best_idx),
            class_name=self.classification_classes[best_idx],
            confidence=float(probabilities[best_idx]),
            top_k=top_k_results,
        )

    def _apply_nms(
        self,
        detections: List[Detection],
        threshold: float,
    ) -> List[Detection]:
        """Non-Maximum Suppression."""
        if not detections:
            return []

        # Сортировка по confidence
        detections = sorted(detections, key=lambda d: d.confidence, reverse=True)
        keep = []

        while detections:
            best = detections.pop(0)
            keep.append(best)

            detections = [
                d for d in detections
                if self._iou(best.bbox, d.bbox) < threshold
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

    def _mock_detect(
        self,
        frame: np.ndarray,
        conf_threshold: float,
    ) -> List[Detection]:
        """Mock детекция для тестирования."""
        # Симуляция детекции
        h, w = frame.shape[:2]
        return [
            Detection(
                bbox=(w // 4, h // 4, 3 * w // 4, 3 * h // 4),
                class_id=0,
                class_name="fish",
                confidence=0.85,
            )
        ]

    def _mock_classify(
        self,
        image: np.ndarray,
        top_k: int,
    ) -> ClassificationResult:
        """Mock классификация для тестирования."""
        return ClassificationResult(
            class_id=10,
            class_name="Atlantic Salmon",
            confidence=0.78,
            top_k=[(10, "Atlantic Salmon", 0.78), (11, "Sea Bass", 0.12)],
        )

    @property
    def stats(self) -> Dict[str, Any]:
        """Статистика inference."""
        avg_time = (
            self._total_inference_time / self._inference_count
            if self._inference_count > 0
            else 0
        )
        return {
            "inference_count": self._inference_count,
            "total_time_s": self._total_inference_time,
            "avg_time_ms": avg_time * 1000,
            "fps": 1 / avg_time if avg_time > 0 else 0,
        }

    async def shutdown(self) -> None:
        """Освобождение ресурсов."""
        if self._device:
            self._device = None
        self._detector = None
        self._classifier = None
        self._initialized = False
        logger.info("Hailo engine shutdown complete")
