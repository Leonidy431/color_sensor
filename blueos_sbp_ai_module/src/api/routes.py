"""
REST API Routes for SBP AI Module.

API для доступа к функционалу анализа данных профилировщика
донного грунта и детекции археологических объектов.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

# Type hints
HailoEngine = Any
SBPParser = Any
ArchDetector = Any


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    sbp_connected: bool
    hailo_available: bool
    uptime_seconds: float


class AnalysisResponse(BaseModel):
    """Analysis result response."""

    layers: List[Dict]
    objects: List[Dict]
    sediment: Dict[str, float]
    water_depth_m: float
    penetration_m: float
    processing_time_ms: float


# Global references
_hailo_engine: Optional[HailoEngine] = None
_sbp_parser: Optional[SBPParser] = None
_arch_detector: Optional[ArchDetector] = None
_start_time: float = time.time()
_websocket_clients: List[WebSocket] = []


def create_app(
    hailo_engine: Optional[HailoEngine] = None,
    sbp_parser: Optional[SBPParser] = None,
    arch_detector: Optional[ArchDetector] = None,
) -> FastAPI:
    """
    Создание FastAPI приложения.

    Args:
        hailo_engine: Hailo SBP inference engine.
        sbp_parser: SUBPRO2545 parser.
        arch_detector: Archaeological detector.

    Returns:
        Configured FastAPI app.
    """
    global _hailo_engine, _sbp_parser, _arch_detector
    _hailo_engine = hailo_engine
    _sbp_parser = sbp_parser
    _arch_detector = arch_detector

    app = FastAPI(
        title="SBP AI Module API",
        description="Sub-Bottom Profiler AI Analysis for Archaeological Detection",
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

    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    """Register all API endpoints."""

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "SBP AI Module",
            "version": "1.0.0",
            "description": "Archaeological object detection in sub-bottom profiler data",
        }

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            sbp_connected=_sbp_parser.is_connected if _sbp_parser else False,
            hailo_available=_hailo_engine is not None,
            uptime_seconds=time.time() - _start_time,
        )

    @app.get("/api/v1/status")
    async def get_status():
        """Get full system status."""
        return {
            "module": "SBP AI",
            "version": "1.0.0",
            "uptime_seconds": time.time() - _start_time,
            "components": {
                "sbp_parser": {
                    "connected": _sbp_parser.is_connected if _sbp_parser else False,
                    "ping_count": _sbp_parser.ping_count if _sbp_parser else 0,
                },
                "hailo": {
                    "available": _hailo_engine is not None,
                    "stats": _hailo_engine.stats if _hailo_engine else None,
                },
                "archaeological_detector": {
                    "available": _arch_detector is not None,
                    "objects_detected": len(_arch_detector.get_all_objects())
                    if _arch_detector else 0,
                },
            },
            "websocket_clients": len(_websocket_clients),
        }

    @app.get("/api/v1/echogram")
    async def get_echogram(num_pings: int = 256):
        """
        Get current echogram data.

        Args:
            num_pings: Number of pings to include.

        Returns:
            Echogram as 2D array (base64 or list).
        """
        if not _sbp_parser:
            raise HTTPException(status_code=503, detail="SBP parser not available")

        echogram = _sbp_parser.get_echogram_normalized(num_pings)
        if echogram is None:
            raise HTTPException(status_code=404, detail="No echogram data available")

        return {
            "shape": echogram.shape,
            "data": echogram.tolist(),
            "range_m": 50.0,
            "timestamp": time.time(),
        }

    @app.get("/api/v1/layers")
    async def get_layers():
        """Get current layer segmentation."""
        if not _hailo_engine or not _sbp_parser:
            raise HTTPException(status_code=503, detail="Analysis not available")

        echogram = _sbp_parser.get_echogram(256)
        if echogram is None:
            raise HTTPException(status_code=404, detail="No data available")

        layers = await _hailo_engine.segment_layers(echogram, range_m=50.0)

        return {
            "layers": [
                {
                    "type": l.sediment_type.name,
                    "depth_start_m": round(l.depth_start_m, 2),
                    "depth_end_m": round(l.depth_end_m, 2),
                    "thickness_m": round(l.thickness_m, 2),
                    "confidence": round(l.confidence, 3),
                }
                for l in layers
            ],
            "timestamp": time.time(),
        }

    @app.get("/api/v1/objects")
    async def get_detected_objects():
        """Get all detected objects."""
        if not _hailo_engine or not _sbp_parser:
            raise HTTPException(status_code=503, detail="Detection not available")

        echogram = _sbp_parser.get_echogram(256)
        if echogram is None:
            raise HTTPException(status_code=404, detail="No data available")

        objects = await _hailo_engine.detect_objects(
            echogram, range_m=50.0, ping_interval_m=0.5
        )

        return {
            "objects": [o.to_dict() for o in objects],
            "count": len(objects),
            "timestamp": time.time(),
        }

    @app.get("/api/v1/archaeological")
    async def get_archaeological_objects():
        """Get archaeological objects and sites."""
        if not _arch_detector:
            raise HTTPException(
                status_code=503, detail="Archaeological detector not available"
            )

        return _arch_detector.generate_report()

    @app.get("/api/v1/archaeological/sites")
    async def get_archaeological_sites():
        """Get discovered archaeological sites."""
        if not _arch_detector:
            raise HTTPException(status_code=503, detail="Detector not available")

        sites = _arch_detector.get_sites()
        return {
            "sites": [s.to_dict() for s in sites],
            "count": len(sites),
        }

    @app.post("/api/v1/analyze")
    async def analyze_current():
        """Run full analysis on current echogram."""
        if not _hailo_engine or not _sbp_parser:
            raise HTTPException(status_code=503, detail="Analysis not available")

        echogram = _sbp_parser.get_echogram(256)
        if echogram is None:
            raise HTTPException(status_code=404, detail="No data available")

        result = await _hailo_engine.analyze_echogram(
            echogram, range_m=50.0, ping_interval_m=0.5
        )

        # Process through archaeological detector
        if _arch_detector:
            detections = [
                {
                    "depth_m": o.depth_m,
                    "distance_m": o.distance_m,
                    "confidence": o.confidence,
                    "size_m": o.size_estimate_m,
                    "archaeological_probability": o.archaeological_probability,
                }
                for o in result.objects
            ]
            arch_objects = _arch_detector.analyze_detections(
                detections,
                water_depth_m=result.water_depth_m,
            )
            result_dict = result.to_dict()
            result_dict["archaeological_objects"] = [o.to_dict() for o in arch_objects]
        else:
            result_dict = result.to_dict()

        return result_dict

    @app.get("/api/v1/sediment")
    async def get_sediment_classification():
        """Get sediment classification."""
        if not _hailo_engine or not _sbp_parser:
            raise HTTPException(status_code=503, detail="Classification not available")

        echogram = _sbp_parser.get_echogram(256)
        if echogram is None:
            raise HTTPException(status_code=404, detail="No data available")

        classification = await _hailo_engine.classify_sediment(echogram)

        return {
            "classification": classification,
            "dominant": max(classification, key=classification.get)
            if classification else None,
            "timestamp": time.time(),
        }

    @app.get("/api/v1/config")
    async def get_config():
        """Get current SBP configuration."""
        if not _sbp_parser:
            raise HTTPException(status_code=503, detail="Parser not available")

        cfg = _sbp_parser.config
        return {
            "connection": {
                "ip": cfg.ip_address,
                "port": cfg.port,
                "protocol": cfg.protocol,
            },
            "acquisition": {
                "frequency_khz": cfg.frequency_khz,
                "pulse_length_us": cfg.pulse_length_us,
                "ping_rate_hz": cfg.ping_rate_hz,
                "range_m": cfg.range_m,
            },
            "gain": {
                "mode": cfg.gain_mode,
                "gain_db": cfg.gain_db,
                "tvg_db_per_m": cfg.tvg_db_per_m,
            },
        }

    @app.get("/api/v1/stats")
    async def get_stats():
        """Get processing statistics."""
        return {
            "hailo": _hailo_engine.stats if _hailo_engine else None,
            "sbp": {
                "ping_count": _sbp_parser.ping_count if _sbp_parser else 0,
            },
            "archaeological": {
                "total_objects": len(_arch_detector.get_all_objects())
                if _arch_detector else 0,
                "total_sites": len(_arch_detector.get_sites())
                if _arch_detector else 0,
            },
            "uptime_seconds": time.time() - _start_time,
        }

    @app.websocket("/ws/stream")
    async def websocket_stream(websocket: WebSocket):
        """WebSocket endpoint for real-time data streaming."""
        await websocket.accept()
        _websocket_clients.append(websocket)
        logger.info(f"WebSocket client connected. Total: {len(_websocket_clients)}")

        try:
            while True:
                # Receive any client messages (keep-alive, config updates)
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_json(), timeout=0.1
                    )
                    # Handle client commands if needed
                    if data.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    pass

                # Send latest analysis if available
                if _hailo_engine and _sbp_parser:
                    echogram = _sbp_parser.get_echogram(64)
                    if echogram is not None:
                        result = await _hailo_engine.analyze_echogram(
                            echogram, range_m=50.0, ping_interval_m=0.5
                        )

                        await websocket.send_json({
                            "type": "analysis",
                            "data": result.to_dict(),
                        })

                await asyncio.sleep(0.5)  # 2 Hz update rate

        except WebSocketDisconnect:
            _websocket_clients.remove(websocket)
            logger.info(
                f"WebSocket client disconnected. Total: {len(_websocket_clients)}"
            )
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            if websocket in _websocket_clients:
                _websocket_clients.remove(websocket)


async def broadcast_to_websockets(message: Dict[str, Any]) -> None:
    """Broadcast message to all connected WebSocket clients."""
    for client in _websocket_clients[:]:
        try:
            await client.send_json(message)
        except Exception:
            _websocket_clients.remove(client)
