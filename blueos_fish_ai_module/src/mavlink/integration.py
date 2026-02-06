"""
MAVLink Integration for Fish AI Module.

Отправка данных о детекции рыб и анализе цвета через MAVLink
для интеграции с QGroundControl и автопилотом.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

try:
    from pymavlink import mavutil
    from pymavlink.dialects.v20 import common as mavlink
    MAVLINK_AVAILABLE = True
except ImportError:
    MAVLINK_AVAILABLE = False
    logger.warning("pymavlink not available")


@dataclass
class FishDetectionMessage:
    """Сообщение о детекции рыбы для MAVLink."""

    fish_count: int
    avg_confidence: float
    dominant_species: str
    dominant_color_hue: float
    freshness_score: float
    water_temp_c: float
    timestamp: float


class MAVLinkIntegration:
    """
    Интеграция с MAVLink для передачи данных Fish AI.

    Отправляет данные через:
    - NAMED_VALUE_FLOAT: числовые параметры
    - STATUSTEXT: текстовые уведомления
    - DEBUG_VECT: векторные данные (RGB цвет)
    """

    # Имена параметров MAVLink (max 10 символов)
    PARAM_FISH_COUNT = "FISH_CNT"
    PARAM_FISH_CONF = "FISH_CONF"
    PARAM_COLOR_HUE = "COLOR_HUE"
    PARAM_COLOR_SAT = "COLOR_SAT"
    PARAM_FRESHNESS = "FRESH_SCR"
    PARAM_TEMP = "SENS_TEMP"

    def __init__(
        self,
        connection_string: str = "udpout:127.0.0.1:14550",
        source_system: int = 1,
        source_component: int = 191,  # MAV_COMP_ID_ONBOARD_COMPUTER
    ):
        """
        Инициализация MAVLink соединения.

        Args:
            connection_string: Строка подключения MAVLink.
            source_system: System ID.
            source_component: Component ID.
        """
        self.connection_string = connection_string
        self.source_system = source_system
        self.source_component = source_component

        self._connection: Optional[Any] = None
        self._connected = False
        self._message_count = 0

    async def connect(self) -> bool:
        """
        Установка MAVLink соединения.

        Returns:
            True если соединение успешно.
        """
        if not MAVLINK_AVAILABLE:
            logger.warning("MAVLink not available, running in mock mode")
            return False

        try:
            self._connection = mavutil.mavlink_connection(
                self.connection_string,
                source_system=self.source_system,
                source_component=self.source_component,
            )
            self._connected = True
            logger.info(f"MAVLink connected: {self.connection_string}")
            return True

        except Exception as e:
            logger.error(f"MAVLink connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Закрытие соединения."""
        if self._connection:
            self._connection.close()
            self._connection = None
        self._connected = False
        logger.info("MAVLink disconnected")

    def send_named_float(self, name: str, value: float) -> bool:
        """
        Отправка NAMED_VALUE_FLOAT сообщения.

        Args:
            name: Имя параметра (max 10 символов).
            value: Значение float.

        Returns:
            True если отправлено успешно.
        """
        if not self._connected or not self._connection:
            return False

        try:
            # Обрезаем имя до 10 символов и дополняем нулями
            name_bytes = name[:10].encode('utf-8').ljust(10, b'\x00')

            self._connection.mav.named_value_float_send(
                int(time.time() * 1000) % (2**32),  # time_boot_ms
                name_bytes,
                value,
            )
            self._message_count += 1
            return True

        except Exception as e:
            logger.error(f"Failed to send NAMED_VALUE_FLOAT: {e}")
            return False

    def send_status_text(
        self,
        text: str,
        severity: int = 6,  # MAV_SEVERITY_INFO
    ) -> bool:
        """
        Отправка STATUSTEXT сообщения.

        Args:
            text: Текст сообщения (max 50 символов).
            severity: Уровень важности (0=EMERGENCY, 6=INFO).

        Returns:
            True если отправлено успешно.
        """
        if not self._connected or not self._connection:
            return False

        try:
            self._connection.mav.statustext_send(
                severity,
                text[:50].encode('utf-8'),
            )
            self._message_count += 1
            return True

        except Exception as e:
            logger.error(f"Failed to send STATUSTEXT: {e}")
            return False

    def send_debug_vect(
        self,
        name: str,
        x: float,
        y: float,
        z: float,
    ) -> bool:
        """
        Отправка DEBUG_VECT сообщения (для RGB и т.п.).

        Args:
            name: Имя вектора (max 10 символов).
            x, y, z: Компоненты вектора.

        Returns:
            True если отправлено успешно.
        """
        if not self._connected or not self._connection:
            return False

        try:
            name_bytes = name[:10].encode('utf-8').ljust(10, b'\x00')

            self._connection.mav.debug_vect_send(
                name_bytes,
                int(time.time() * 1e6),  # time_usec
                x, y, z,
            )
            self._message_count += 1
            return True

        except Exception as e:
            logger.error(f"Failed to send DEBUG_VECT: {e}")
            return False

    async def send_fish_detection(
        self,
        detection: FishDetectionMessage,
    ) -> None:
        """
        Отправка полных данных о детекции рыб.

        Args:
            detection: Данные детекции.
        """
        # Количество рыб
        self.send_named_float(self.PARAM_FISH_COUNT, float(detection.fish_count))

        # Средняя уверенность
        self.send_named_float(self.PARAM_FISH_CONF, detection.avg_confidence)

        # Цвет (Hue)
        self.send_named_float(self.PARAM_COLOR_HUE, detection.dominant_color_hue)

        # Свежесть
        self.send_named_float(self.PARAM_FRESHNESS, detection.freshness_score)

        # Температура датчика
        self.send_named_float(self.PARAM_TEMP, detection.water_temp_c)

        # Уведомление при обнаружении рыб
        if detection.fish_count > 0:
            text = f"Fish: {detection.fish_count}, {detection.dominant_species}"
            self.send_status_text(text, severity=6)

    async def send_color_analysis(
        self,
        rgb: Tuple[int, int, int],
        hsv: Tuple[float, float, float],
        freshness: str,
    ) -> None:
        """
        Отправка данных анализа цвета.

        Args:
            rgb: RGB значения (0-255).
            hsv: HSV значения.
            freshness: Статус свежести.
        """
        # RGB как DEBUG_VECT
        self.send_debug_vect(
            "FISH_RGB",
            float(rgb[0]),
            float(rgb[1]),
            float(rgb[2]),
        )

        # HSV параметры
        self.send_named_float(self.PARAM_COLOR_HUE, hsv[0])
        self.send_named_float(self.PARAM_COLOR_SAT, hsv[1])

        # Уведомление о свежести если не "fresh"
        if freshness.lower() != "fresh":
            self.send_status_text(f"Fish freshness: {freshness}", severity=4)

    @property
    def is_connected(self) -> bool:
        """Статус соединения."""
        return self._connected

    @property
    def message_count(self) -> int:
        """Количество отправленных сообщений."""
        return self._message_count


class MAVLinkReceiver:
    """
    Приёмник MAVLink сообщений.

    Принимает команды и данные навигации от автопилота.
    """

    def __init__(
        self,
        connection_string: str = "udpin:0.0.0.0:14550",
    ):
        """
        Инициализация приёмника.

        Args:
            connection_string: Строка подключения.
        """
        self.connection_string = connection_string
        self._connection: Optional[Any] = None
        self._running = False

        # Последние данные навигации
        self.position: Optional[Tuple[float, float, float]] = None  # lat, lon, alt
        self.attitude: Optional[Tuple[float, float, float]] = None  # roll, pitch, yaw
        self.depth_m: float = 0.0

    async def start(self) -> bool:
        """Запуск приёма сообщений."""
        if not MAVLINK_AVAILABLE:
            return False

        try:
            self._connection = mavutil.mavlink_connection(self.connection_string)
            self._running = True
            asyncio.create_task(self._receive_loop())
            logger.info(f"MAVLink receiver started: {self.connection_string}")
            return True

        except Exception as e:
            logger.error(f"MAVLink receiver start failed: {e}")
            return False

    async def stop(self) -> None:
        """Остановка приёма."""
        self._running = False
        if self._connection:
            self._connection.close()

    async def _receive_loop(self) -> None:
        """Цикл приёма сообщений."""
        while self._running:
            try:
                msg = self._connection.recv_match(blocking=False)
                if msg:
                    self._handle_message(msg)
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"MAVLink receive error: {e}")
                await asyncio.sleep(0.1)

    def _handle_message(self, msg: Any) -> None:
        """Обработка входящего сообщения."""
        msg_type = msg.get_type()

        if msg_type == "GLOBAL_POSITION_INT":
            self.position = (
                msg.lat / 1e7,
                msg.lon / 1e7,
                msg.relative_alt / 1000.0,
            )

        elif msg_type == "ATTITUDE":
            self.attitude = (
                msg.roll,
                msg.pitch,
                msg.yaw,
            )

        elif msg_type == "VFR_HUD":
            # Для ROV глубина может быть в alt
            self.depth_m = -msg.alt if msg.alt < 0 else 0
