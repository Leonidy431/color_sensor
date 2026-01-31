"""
Fish AI Module - Main Entry Point.

Запускает все компоненты системы и координирует их работу.
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
from .hailo_inference import HailoInferenceEngine
from .data_fusion import DataFusionEngine, SpeciesColorProfile

# Настройка логирования
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add(
    "/app/logs/fish_ai.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
)


class FishAIModule:
    """
    Главный класс модуля Fish AI.

    Координирует работу всех компонентов:
    - Hailo inference engine
    - AS7262 color analyzer
    - Data fusion
    - REST/WebSocket API
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
        self.hailo_engine: Optional[HailoInferenceEngine] = None
        self.color_analyzer = None  # AS7262 from parent module
        self.fusion_engine: Optional[DataFusionEngine] = None

        # Состояние
        self._running = False
        self._tasks: list = []

    async def load_config(self) -> None:
        """Загрузка конфигурации."""
        # Hailo config
        hailo_config_path = self.config_dir / "hailo_config.yaml"
        if hailo_config_path.exists():
            with open(hailo_config_path) as f:
                self.config["hailo"] = yaml.safe_load(f)
            logger.info("Hailo config loaded")

        # Fish species config
        species_config_path = self.config_dir / "fish_species.yaml"
        if species_config_path.exists():
            with open(species_config_path) as f:
                self.config["species"] = yaml.safe_load(f)
            logger.info("Fish species config loaded")

    async def initialize_components(self) -> None:
        """Инициализация всех компонентов."""
        logger.info("Initializing Fish AI components...")

        # Hailo Engine
        hailo_cfg = self.config.get("hailo", {})
        models_cfg = hailo_cfg.get("models", {})

        self.hailo_engine = HailoInferenceEngine(
            detector_path=models_cfg.get("fish_detector", {}).get("path"),
            classifier_path=models_cfg.get("fish_classifier", {}).get("path"),
            device_id=hailo_cfg.get("device", {}).get("id", 0),
        )

        if not await self.hailo_engine.initialize():
            logger.warning("Hailo initialization failed, running in degraded mode")

        # Fusion Engine
        species_cfg = self.config.get("species", {})
        species_profiles = []

        for species in species_cfg.get("species", []):
            color_profile = species.get("color_profile", {})
            profiles = SpeciesColorProfile(
                species_id=species["id"],
                species_name=species["name_en"],
                hue_range=tuple(color_profile.get("dominant_hue", [0, 360])),
                saturation_range=tuple(color_profile.get("saturation_range", [0, 1])),
                is_iridescent=color_profile.get("iridescent", False),
                pattern=color_profile.get("pattern", "solid"),
            )
            species_profiles.append(profiles)

        classification_cfg = species_cfg.get("classification", {})
        self.fusion_engine = DataFusionEngine(
            species_profiles=species_profiles,
            visual_weight=classification_cfg.get("visual_weight", 0.7),
            color_weight=classification_cfg.get("color_weight", 0.3),
        )

        # Загрузка классов для Hailo classifier
        if self.hailo_engine:
            self.hailo_engine.classification_classes = [
                s["name_en"] for s in species_cfg.get("species", [])
            ]

        logger.info("All components initialized")

    async def start(self) -> None:
        """Запуск модуля."""
        logger.info("Starting Fish AI Module...")

        await self.load_config()
        await self.initialize_components()

        self._running = True

        # Создание FastAPI приложения
        app = create_app(
            hailo_engine=self.hailo_engine,
            fusion_engine=self.fusion_engine,
        )

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

        logger.info("Fish AI Module started on port 8080")
        await server.serve()

    async def shutdown(self, sig: signal.Signals) -> None:
        """Graceful shutdown."""
        logger.info(f"Received signal {sig.name}, shutting down...")

        self._running = False

        # Остановка компонентов
        if self.hailo_engine:
            await self.hailo_engine.shutdown()

        # Отмена задач
        for task in self._tasks:
            task.cancel()

        logger.info("Shutdown complete")
        sys.exit(0)


async def main() -> None:
    """Точка входа."""
    module = FishAIModule()
    await module.start()


if __name__ == "__main__":
    asyncio.run(main())
