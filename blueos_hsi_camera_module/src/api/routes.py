"""
REST API для модуля подводной гиперспектральной визуализации (HSI).

Предоставляет доступ к калибровке куба данных и SAM-классификации
материалов по спектральной библиотеке.
"""

import time
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from hsi_calibration import HSICalibrator
from spectral_analysis import SpectralAnalyzer, SpectralLibrary

# Значения по умолчанию: диапазон и разрешение Ecotone AS UHI
# (выбранная камера, см. README.md раздел 1)
DEFAULT_WAVELENGTHS_NM = [
    380 + i * 2.2 for i in range(int((750 - 380) / 2.2) + 1)
]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    white_calibrated: bool
    water_column_calibrated: bool
    uptime_seconds: float


class ClassifyPixelRequest(BaseModel):
    """Запрос на классификацию одного спектра пикселя."""

    spectrum: List[float]
    wavelengths_nm: Optional[List[float]] = None
    depth_m: float = 0.0


class ClassifyPixelResponse(BaseModel):
    """Результат классификации пикселя."""

    material: str
    angle_rad: float
    degradation_index: float


_calibrator = HSICalibrator()
_analyzer = SpectralAnalyzer()
_library: Optional[SpectralLibrary] = None
_start_time = time.time()


def create_app() -> FastAPI:
    """Создание FastAPI приложения для HSI-модуля."""
    global _library
    _library = SpectralLibrary.seed_illustrative_library(DEFAULT_WAVELENGTHS_NM)

    app = FastAPI(
        title="HSI Camera Module API",
        description=(
            "Underwater Hyperspectral Imaging analysis "
            "(material classification, water column correction)"
        ),
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    """Регистрация всех эндпоинтов."""

    @app.get("/")
    async def root():
        return {
            "name": "HSI Camera Module",
            "version": "1.0.0",
            "camera": "Ecotone AS UHI (см. README.md)",
            "description": "Underwater hyperspectral material classification",
        }

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health_check():
        return HealthResponse(
            status="healthy",
            white_calibrated=_calibrator.is_white_calibrated,
            water_column_calibrated=_calibrator.is_water_column_calibrated,
            uptime_seconds=time.time() - _start_time,
        )

    @app.get("/api/v1/library")
    async def get_library():
        """Список доступных эталонов спектральной библиотеки."""
        return {
            "materials": list(_library.endmembers.keys()),
            "channels": len(_library.wavelengths_nm),
            "wavelength_range_nm": [
                min(_library.wavelengths_nm),
                max(_library.wavelengths_nm),
            ],
        }

    @app.post("/api/v1/classify", response_model=ClassifyPixelResponse)
    async def classify_pixel(request: ClassifyPixelRequest):
        """Классификация одного спектра (например, из ручного зонда)."""
        wavelengths = request.wavelengths_nm or DEFAULT_WAVELENGTHS_NM
        if len(request.spectrum) != len(wavelengths):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Длина spectrum (%d) не совпадает с числом каналов "
                    "(%d)" % (len(request.spectrum), len(wavelengths))
                ),
            )

        spectrum = np.array(request.spectrum, dtype=np.float64)

        if request.depth_m > 0:
            cube = spectrum.reshape(1, 1, -1)
            corrected = _calibrator.correct_water_column(
                cube, wavelengths, request.depth_m
            )
            spectrum = corrected[0, 0, :]

        library = _library
        if len(wavelengths) != len(_library.wavelengths_nm):
            library = _library.resample_to(wavelengths)

        material, angle = _analyzer.classify_pixel(spectrum, library)
        degradation = _analyzer.degradation_index(spectrum, wavelengths)

        return ClassifyPixelResponse(
            material=material,
            angle_rad=round(angle, 4),
            degradation_index=round(degradation, 3),
        )

    @app.get("/api/v1/config")
    async def get_config():
        """Текущая конфигурация камеры (см. README.md, раздел 1)."""
        return {
            "camera_model": "Ecotone AS UHI",
            "spectral_range_nm": [380, 750],
            "spectral_resolution_nm": 2.2,
            "channels": len(DEFAULT_WAVELENGTHS_NM),
            "scan_type": "pushbroom",
            "housing": "titanium",
            "depth_rating_options_m": [1000, 2000, 6000],
        }
