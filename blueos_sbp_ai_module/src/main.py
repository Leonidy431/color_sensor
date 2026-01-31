"""
SBP AI Module - Main Entry Point.

Модуль анализа данных профилировщика донного грунта
для обнаружения археологических объектов.

Компоненты:
- SUBPRO2545 Parser: приём данных от профилировщика
- Hailo SBP Engine: AI-анализ на NPU
- Archaeological Detector: классификация артефактов
- FastAPI Server: REST API + WebSocket
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

import uvicorn
import yaml
from loguru import logger

from .api.routes import create_app
from .sbp_parser import SUBPRO2545Parser, SBPConfig
from .hailo_sbp_inference import HailoSBPEngine
from .archaeological_detector import ArchaeologicalDetector

# Настройка логирования
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add(
    "/app/logs/sbp_ai.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
)


class SBPAIModule:
    """
    Главный класс модуля SBP AI.

    Координирует работу всех компонентов для анализа
    данных профилировщика и детекции археологических объектов.
    """

    def __init__(self, config_dir: str = "/app/config"):
        """
        Инициализация модуля.

        Args:
            config_dir: Директория с конфигурационными файлами.
        """
        self.config_dir = Path(config_dir)
        self.config: dict = {}

        # Компоненты
        self.sbp_parser: Optional[SUBPRO2545Parser] = None
        self.hailo_engine: Optional[HailoSBPEngine] = None
        self.arch_detector: Optional[ArchaeologicalDetector] = None

        # Состояние
        self._running = False
        self._tasks: list = []

    async def load_config(self) -> None:
        """Загрузка конфигурации."""
        # SBP config
        sbp_config_path = self.config_dir / "subpro_config.yaml"
        if sbp_config_path.exists():
            with open(sbp_config_path) as f:
                self.config["sbp"] = yaml.safe_load(f)
            logger.info("SBP config loaded")

        # Archaeological objects config
        arch_config_path = self.config_dir / "archaeological_objects.yaml"
        if arch_config_path.exists():
            with open(arch_config_path) as f:
                self.config["archaeological"] = yaml.safe_load(f)
            logger.info("Archaeological config loaded")

    async def initialize_components(self) -> None:
        """Инициализация всех компонентов."""
        logger.info("Initializing SBP AI components...")

        # SBP Parser
        sbp_cfg = self.config.get("sbp", {})
        conn_cfg = sbp_cfg.get("connection", {})
        acq_cfg = sbp_cfg.get("acquisition", {})

        parser_config = SBPConfig(
            ip_address=conn_cfg.get("ip", "192.168.2.100"),
            port=conn_cfg.get("port", 4040),
            protocol=conn_cfg.get("protocol", "udp"),
            frequency_khz=acq_cfg.get("frequency_khz", 35.0),
            ping_rate_hz=acq_cfg.get("ping_rate_hz", 20.0),
            range_m=acq_cfg.get("range_m", 50.0),
        )

        self.sbp_parser = SUBPRO2545Parser(config=parser_config)
        logger.info(f"SBP Parser configured for {parser_config.ip_address}:{parser_config.port}")

        # Hailo Engine
        self.hailo_engine = HailoSBPEngine(
            models_dir=str(self.config_dir.parent / "models"),
        )

        if await self.hailo_engine.initialize():
            logger.info("Hailo SBP engine initialized")
        else:
            logger.warning("Hailo initialization failed, running in mock mode")

        # Archaeological Detector
        self.arch_detector = ArchaeologicalDetector()
        logger.info("Archaeological detector initialized")

        # Callback для обработки пингов
        self.sbp_parser.add_callback(self._on_ping_received)

        logger.info("All components initialized")

    def _on_ping_received(self, ping) -> None:
        """Callback при получении пинга от профилировщика."""
        # Асинхронная обработка в отдельной задаче
        asyncio.create_task(self._process_ping(ping))

    async def _process_ping(self, ping) -> None:
        """Асинхронная обработка пинга."""
        try:
            # Получение эхограммы для анализа (каждые N пингов)
            if ping.ping_number % 10 == 0:  # Анализ каждые 10 пингов
                echogram = self.sbp_parser.get_echogram(64)
                if echogram is not None and self.hailo_engine:
                    result = await self.hailo_engine.analyze_echogram(
                        echogram,
                        range_m=ping.range_m,
                        ping_interval_m=0.5,
                    )

                    # Обработка археологических объектов
                    if result.objects and self.arch_detector:
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

                        arch_objects = self.arch_detector.analyze_detections(
                            detections,
                            water_depth_m=result.water_depth_m,
                            track_position=ping.position,
                        )

                        if arch_objects:
                            for obj in arch_objects:
                                if obj.excavation_priority >= 4:
                                    logger.info(
                                        f"High-priority archaeological object: "
                                        f"{obj.object_class.name} at {obj.depth_below_seabed_m:.1f}m, "
                                        f"priority={obj.excavation_priority}"
                                    )

        except Exception as e:
            logger.error(f"Ping processing error: {e}")

    async def start(self) -> None:
        """Запуск модуля."""
        logger.info("Starting SBP AI Module...")

        await self.load_config()
        await self.initialize_components()

        self._running = True

        # Создание FastAPI приложения
        app = create_app(
            hailo_engine=self.hailo_engine,
            sbp_parser=self.sbp_parser,
            arch_detector=self.arch_detector,
        )

        # Запуск SBP streaming в фоне
        streaming_task = asyncio.create_task(self._run_sbp_streaming())
        self._tasks.append(streaming_task)

        # Mock данные для демонстрации (если нет реального оборудования)
        mock_task = asyncio.create_task(self._generate_mock_data())
        self._tasks.append(mock_task)

        # Запуск API сервера
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8080,
            log_level="info",
            access_log=True,
        )
        server = uvicorn.Server(config)

        # Обработка сигналов
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self.shutdown(s))
            )

        logger.info("SBP AI Module started on port 8080")
        logger.info("Endpoints:")
        logger.info("  - API Docs: http://localhost:8080/api/docs")
        logger.info("  - WebSocket: ws://localhost:8080/ws/stream")

        await server.serve()

    async def _run_sbp_streaming(self) -> None:
        """Запуск потоковой обработки SBP данных."""
        try:
            if await self.sbp_parser.connect():
                await self.sbp_parser.start_streaming()
        except Exception as e:
            logger.error(f"SBP streaming error: {e}")

    async def _generate_mock_data(self) -> None:
        """Генерация mock данных для тестирования."""
        logger.info("Starting mock data generation...")

        while self._running:
            try:
                # Генерируем mock пинг
                if self.sbp_parser:
                    mock_ping = self.sbp_parser._generate_mock_ping()
                    self.sbp_parser._add_to_buffer(mock_ping)

                    # Вызываем обработчики
                    for callback in self.sbp_parser._callbacks:
                        callback(mock_ping)

                await asyncio.sleep(0.05)  # 20 Hz

            except Exception as e:
                logger.error(f"Mock data error: {e}")
                await asyncio.sleep(1)

    async def shutdown(self, sig: signal.Signals) -> None:
        """Graceful shutdown."""
        logger.info(f"Received signal {sig.name}, shutting down...")

        self._running = False

        # Остановка компонентов
        if self.sbp_parser:
            await self.sbp_parser.disconnect()

        if self.hailo_engine:
            await self.hailo_engine.shutdown()

        # Отмена задач
        for task in self._tasks:
            task.cancel()

        # Генерация финального отчёта
        if self.arch_detector:
            report = self.arch_detector.generate_report()
            logger.info(
                f"Session summary: {report['summary']['total_objects']} objects, "
                f"{report['summary']['total_sites']} sites detected"
            )

        logger.info("Shutdown complete")
        sys.exit(0)


async def main() -> None:
    """Точка входа."""
    module = SBPAIModule()
    await module.start()


if __name__ == "__main__":
    asyncio.run(main())
