"""
MAVLink Integration for SBP AI Module.

Отправка данных о профилировании дна и археологических
объектах через MAVLink для интеграции с QGroundControl.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

try:
    from pymavlink import mavutil
    MAVLINK_AVAILABLE = True
except ImportError:
    MAVLINK_AVAILABLE = False
    logger.warning("pymavlink not available")


@dataclass
class SBPTelemetry:
    """Телеметрия профилировщика для MAVLink."""

    water_depth_m: float
    penetration_m: float
    sediment_type: str
    objects_count: int
    high_priority_count: int
    ping_rate_hz: float
    position: Optional[Tuple[float, float]] = None


class SBPMAVLinkIntegration:
    """
    MAVLink интеграция для Sub-Bottom Profiler AI.

    Передаёт данные о:
    - Глубине воды и проникновении в грунт
    - Типе донных отложений
    - Обнаруженных объектах
    - Археологических находках высокого приоритета
    """

    # Параметры MAVLink (max 10 символов)
    PARAM_WATER_DEPTH = "SBP_WDEPTH"
    PARAM_PENETRATION = "SBP_PENET"
    PARAM_OBJECTS = "SBP_OBJCNT"
    PARAM_PRIORITY = "SBP_HPRIO"
    PARAM_PING_RATE = "SBP_PING"
    PARAM_SEDIMENT = "SBP_SEDIM"

    # Коды типов грунта для MAVLink
    SEDIMENT_CODES = {
        "water": 0,
        "mud": 1,
        "sand": 2,
        "clay": 3,
        "gravel": 4,
        "rock": 5,
    }

    def __init__(
        self,
        connection_string: str = "udpout:127.0.0.1:14550",
        source_system: int = 1,
        source_component: int = 192,
    ):
        """
        Инициализация MAVLink.

        Args:
            connection_string: Строка подключения.
            source_system: System ID.
            source_component: Component ID.
        """
        self.connection_string = connection_string
        self.source_system = source_system
        self.source_component = source_component

        self._connection: Optional[Any] = None
        self._connected = False
        self._message_count = 0

        # Кэш для throttling
        self._last_alert_time: Dict[str, float] = {}
        self._alert_interval = 10.0  # секунд между alert одного типа

    async def connect(self) -> bool:
        """Установка соединения."""
        if not MAVLINK_AVAILABLE:
            logger.warning("MAVLink not available")
            return False

        try:
            self._connection = mavutil.mavlink_connection(
                self.connection_string,
                source_system=self.source_system,
                source_component=self.source_component,
            )
            self._connected = True
            logger.info(f"SBP MAVLink connected: {self.connection_string}")
            return True

        except Exception as e:
            logger.error(f"MAVLink connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Закрытие соединения."""
        if self._connection:
            self._connection.close()
        self._connected = False
        logger.info("SBP MAVLink disconnected")

    def send_named_float(self, name: str, value: float) -> bool:
        """Отправка NAMED_VALUE_FLOAT."""
        if not self._connected or not self._connection:
            return False

        try:
            name_bytes = name[:10].encode('utf-8').ljust(10, b'\x00')
            self._connection.mav.named_value_float_send(
                int(time.time() * 1000) % (2**32),
                name_bytes,
                value,
            )
            self._message_count += 1
            return True

        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    def send_status_text(
        self,
        text: str,
        severity: int = 6,
        throttle_key: Optional[str] = None,
    ) -> bool:
        """
        Отправка STATUSTEXT с throttling.

        Args:
            text: Текст сообщения.
            severity: Уровень (0=EMERGENCY, 4=WARNING, 6=INFO).
            throttle_key: Ключ для throttling (не отправлять чаще интервала).
        """
        if not self._connected or not self._connection:
            return False

        # Throttling
        if throttle_key:
            now = time.time()
            last = self._last_alert_time.get(throttle_key, 0)
            if now - last < self._alert_interval:
                return False
            self._last_alert_time[throttle_key] = now

        try:
            self._connection.mav.statustext_send(
                severity,
                text[:50].encode('utf-8'),
            )
            self._message_count += 1
            return True

        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    async def send_telemetry(self, telemetry: SBPTelemetry) -> None:
        """
        Отправка телеметрии SBP.

        Args:
            telemetry: Данные телеметрии.
        """
        # Глубина воды
        self.send_named_float(self.PARAM_WATER_DEPTH, telemetry.water_depth_m)

        # Проникновение в грунт
        self.send_named_float(self.PARAM_PENETRATION, telemetry.penetration_m)

        # Количество объектов
        self.send_named_float(self.PARAM_OBJECTS, float(telemetry.objects_count))

        # Высокоприоритетные объекты
        self.send_named_float(self.PARAM_PRIORITY, float(telemetry.high_priority_count))

        # Тип грунта (как код)
        sediment_code = self.SEDIMENT_CODES.get(telemetry.sediment_type.lower(), 0)
        self.send_named_float(self.PARAM_SEDIMENT, float(sediment_code))

        # Частота пингов
        self.send_named_float(self.PARAM_PING_RATE, telemetry.ping_rate_hz)

    async def send_object_alert(
        self,
        object_type: str,
        depth_m: float,
        priority: int,
        confidence: float,
    ) -> None:
        """
        Отправка алерта об обнаруженном объекте.

        Args:
            object_type: Тип объекта.
            depth_m: Глубина залегания.
            priority: Приоритет (1-5).
            confidence: Уверенность (0-1).
        """
        # Определение severity по приоритету
        if priority >= 5:
            severity = 3  # MAV_SEVERITY_ERROR (важный)
        elif priority >= 4:
            severity = 4  # MAV_SEVERITY_WARNING
        else:
            severity = 6  # MAV_SEVERITY_INFO

        text = f"SBP: {object_type} at {depth_m:.1f}m (P{priority})"

        self.send_status_text(
            text,
            severity=severity,
            throttle_key=f"obj_{object_type}",
        )

    async def send_site_discovery(
        self,
        site_type: str,
        object_count: int,
        estimated_period: str,
    ) -> None:
        """
        Отправка уведомления об обнаружении памятника.

        Args:
            site_type: Тип памятника (shipwreck, anchorage, etc).
            object_count: Количество объектов.
            estimated_period: Предполагаемый период.
        """
        text = f"SITE: {site_type}, {object_count} obj, {estimated_period}"

        # Всегда важное сообщение для памятника
        self.send_status_text(
            text,
            severity=2,  # MAV_SEVERITY_CRITICAL
            throttle_key=f"site_{site_type}",
        )

    async def send_layer_change(
        self,
        new_layer: str,
        depth_m: float,
    ) -> None:
        """
        Уведомление о смене слоя грунта.

        Args:
            new_layer: Новый тип слоя.
            depth_m: Глубина границы.
        """
        text = f"Layer: {new_layer} at {depth_m:.1f}m"
        self.send_status_text(text, severity=6)

    @property
    def is_connected(self) -> bool:
        """Статус соединения."""
        return self._connected

    @property
    def message_count(self) -> int:
        """Количество отправленных сообщений."""
        return self._message_count
