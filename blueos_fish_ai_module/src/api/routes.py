"""
REST API Routes for Fish AI Module.

Предоставляет HTTP endpoints для доступа к функционалу
детекции и анализа рыб.
"""

import time
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

# Type hints для движков
HailoEngine = Any
FusionEngine = Any


class HealthResponse(BaseModel):
    """Ответ health check."""

    status: str
    hailo_available: bool
    color_sensor_available: bool
    uptime_seconds: float


class DetectionRequest(BaseModel):
    """Запрос на детекцию."""

    confidence_threshold: float = 0.5
    nms_threshold: float = 0.45


class AnalysisResponse(BaseModel):
    """Ответ полного анализа."""

    fish_detected: bool
    species: Optional[Dict[str, Any]]
    color: Optional[Dict[str, Any]]
    freshness: Dict[str, Any]
    confidence: float
    timestamp: float


# Глобальные ссылки на движки
_hailo_engine: Optional[HailoEngine] = None
_fusion_engine: Optional[FusionEngine] = None
_start_time: float = time.time()


def create_app(
    hailo_engine: Optional[HailoEngine] = None,
    fusion_engine: Optional[FusionEngine] = None,
) -> FastAPI:
    """
    Создание FastAPI приложения.

    Args:
        hailo_engine: Hailo inference engine.
        fusion_engine: Data fusion engine.

    Returns:
        Настроенное FastAPI приложение.
    """
    global _hailo_engine, _fusion_engine
    _hailo_engine = hailo_engine
    _fusion_engine = fusion_engine

    app = FastAPI(
        title="Fish AI Module API",
        description="Real-time fish detection and color analysis",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Статические файлы (Web UI)
    try:
        app.mount("/static", StaticFiles(directory="/app/web"), name="static")
    except Exception:
        logger.warning("Static files directory not found")

    # Регистрация роутов
    register_routes(app)

    return app


def register_routes(app: FastAPI) -> None:
    """Регистрация всех API endpoints."""

    @app.get("/")
    async def root():
        """Корневой endpoint."""
        return {"name": "Fish AI Module", "version": "1.0.0"}

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            hailo_available=_hailo_engine is not None,
            color_sensor_available=True,  # TODO: реальная проверка
            uptime_seconds=time.time() - _start_time,
        )

    @app.get("/api/v1/status")
    async def get_status():
        """Получение статуса системы."""
        status = {
            "module": "Fish AI",
            "version": "1.0.0",
            "uptime_seconds": time.time() - _start_time,
            "components": {
                "hailo": {
                    "available": _hailo_engine is not None,
                    "stats": _hailo_engine.stats if _hailo_engine else None,
                },
                "color_sensor": {
                    "available": True,
                    "type": "AS7262",
                },
                "fusion": {
                    "available": _fusion_engine is not None,
                },
            },
        }
        return JSONResponse(content=status)

    @app.post("/api/v1/detect")
    async def detect_fish(
        file: UploadFile = File(...),
        confidence_threshold: float = 0.5,
        nms_threshold: float = 0.45,
    ):
        """
        Детекция рыб на изображении.

        Args:
            file: Загруженное изображение.
            confidence_threshold: Порог уверенности.
            nms_threshold: Порог NMS.

        Returns:
            Список детекций.
        """
        if not _hailo_engine:
            raise HTTPException(
                status_code=503,
                detail="Hailo engine not available"
            )

        try:
            import cv2

            # Чтение изображения
            contents = await file.read()
            nparr = np.frombuffer(contents, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid image format"
                )

            # Детекция
            detections = await _hailo_engine.detect(
                frame,
                confidence_threshold=confidence_threshold,
                nms_threshold=nms_threshold,
            )

            return {
                "detections": [
                    {
                        "bbox": d.bbox,
                        "class": d.class_name,
                        "confidence": round(d.confidence, 3),
                    }
                    for d in detections
                ],
                "count": len(detections),
                "image_size": [frame.shape[1], frame.shape[0]],
            }

        except Exception as e:
            logger.error(f"Detection failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/v1/classify")
    async def classify_species(file: UploadFile = File(...)):
        """
        Классификация вида рыбы.

        Args:
            file: Изображение рыбы (обрезанное).

        Returns:
            Результат классификации.
        """
        if not _hailo_engine:
            raise HTTPException(
                status_code=503,
                detail="Hailo engine not available"
            )

        try:
            import cv2

            contents = await file.read()
            nparr = np.frombuffer(contents, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image is None:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid image format"
                )

            result = await _hailo_engine.classify(image)

            if not result:
                return {"species": None, "confidence": 0}

            return {
                "species": {
                    "id": result.class_id,
                    "name": result.class_name,
                    "confidence": round(result.confidence, 3),
                },
                "top_k": [
                    {"id": c[0], "name": c[1], "confidence": round(c[2], 3)}
                    for c in result.top_k
                ],
            }

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/color")
    async def get_color_data():
        """
        Получение текущих данных цвета от AS7262.

        Returns:
            Спектральные и цветовые данные.
        """
        # TODO: интеграция с реальным AS7262
        # Временные mock данные
        return {
            "spectrum": {
                "violet": 0.234,
                "blue": 0.456,
                "green": 0.789,
                "yellow": 0.654,
                "orange": 0.432,
                "red": 0.321,
            },
            "rgb": [180, 220, 150],
            "hsv": {"h": 95.5, "s": 0.682, "v": 0.863},
            "lab": {"L": 82.45, "a": -15.32, "b": 28.76},
            "color_class": "Green",
            "freshness": {"status": "fresh", "score": 0.756},
            "timestamp": time.time(),
        }

    @app.post("/api/v1/analysis")
    async def full_analysis(
        file: UploadFile = File(...),
        include_color: bool = True,
    ):
        """
        Полный анализ: детекция + классификация + цвет.

        Args:
            file: Изображение для анализа.
            include_color: Включить анализ цвета.

        Returns:
            Комплексный результат анализа.
        """
        if not _hailo_engine or not _fusion_engine:
            raise HTTPException(
                status_code=503,
                detail="Analysis engines not available"
            )

        try:
            import cv2

            contents = await file.read()
            nparr = np.frombuffer(contents, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid image format"
                )

            # Детекция
            detections = await _hailo_engine.detect(frame)

            if not detections:
                return {
                    "fish_detected": False,
                    "species": None,
                    "color": None,
                    "freshness": {"status": "unknown", "score": 0},
                    "confidence": 0,
                    "timestamp": time.time(),
                }

            # Классификация лучшей детекции
            best_detection = max(detections, key=lambda d: d.confidence)
            x1, y1, x2, y2 = best_detection.bbox
            fish_crop = frame[y1:y2, x1:x2]

            classification = await _hailo_engine.classify(fish_crop)

            # Слияние данных (цвет - mock)
            from .data_fusion import ColorData
            color_data = ColorData(
                spectrum={"violet": 0.2, "blue": 0.4, "green": 0.7,
                          "yellow": 0.5, "orange": 0.3, "red": 0.2},
                rgb=(180, 220, 150),
                hsv=(95.5, 0.68, 0.86),
                lab=(82.4, -15.3, 28.7),
                dominant_hue=95.5,
                saturation=0.68,
                freshness_score=0.75,
                color_class="Green",
            ) if include_color else None

            result = await _fusion_engine.fuse(
                best_detection,
                classification,
                color_data,
            )

            return result.to_dict()

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/species")
    async def list_species():
        """Список поддерживаемых видов рыб."""
        if not _fusion_engine:
            return {"species": []}

        return {
            "species": [
                {
                    "id": p.species_id,
                    "name": p.species_name,
                    "color_profile": {
                        "hue_range": p.hue_range,
                        "saturation_range": p.saturation_range,
                        "iridescent": p.is_iridescent,
                    },
                }
                for p in _fusion_engine.species_profiles
            ],
            "count": len(_fusion_engine.species_profiles),
        }

    @app.get("/api/v1/stats")
    async def get_stats():
        """Статистика работы модуля."""
        return {
            "hailo": _hailo_engine.stats if _hailo_engine else None,
            "uptime_seconds": time.time() - _start_time,
        }
