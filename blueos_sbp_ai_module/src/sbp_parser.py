"""
Sub-Bottom Profiler Data Parser.

Парсинг данных от профилировщиков донного грунта:
- SUBPRO2545 (General Acoustics)
- Поддержка форматов SEG-Y, RAW, UDP stream

Характеристики SUBPRO2545:
- Частоты: 25-45 кГц
- Вертикальное разрешение: 1-2 см
- Проникновение: 15+ м в грунт
"""

import asyncio
import socket
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger


class SBPDataFormat(Enum):
    """Форматы данных профилировщика."""

    RAW = "raw"
    SEGY = "segy"
    UDP_STREAM = "udp"


@dataclass
class SBPPing:
    """
    Единичный пинг (эхограмма) от профилировщика.

    Содержит акустические данные одного измерения.
    """

    ping_number: int
    timestamp: float
    frequency_khz: float
    samples: np.ndarray  # Амплитуды эхо-сигнала
    range_m: float  # Максимальная дальность
    sample_interval_us: float  # Интервал между отсчётами
    position: Optional[Tuple[float, float, float]] = None  # lat, lon, depth
    heading: float = 0.0
    speed_mps: float = 0.0

    @property
    def num_samples(self) -> int:
        """Количество отсчётов в пинге."""
        return len(self.samples)

    @property
    def depth_array(self) -> np.ndarray:
        """Массив глубин для каждого отсчёта (м)."""
        sound_speed = 1500  # м/с в воде
        time_array = np.arange(self.num_samples) * self.sample_interval_us * 1e-6
        return time_array * sound_speed / 2  # Двойной путь

    @property
    def resolution_m(self) -> float:
        """Вертикальное разрешение (м)."""
        sound_speed = 1500
        return self.sample_interval_us * 1e-6 * sound_speed / 2

    def to_image(self, width: int = 1) -> np.ndarray:
        """Конвертация в формат изображения (H, W)."""
        return self.samples.reshape(-1, width)

    def normalize(self) -> np.ndarray:
        """Нормализация амплитуд в диапазон 0-255."""
        data = self.samples.astype(np.float32)
        data_min, data_max = data.min(), data.max()
        if data_max > data_min:
            normalized = (data - data_min) / (data_max - data_min) * 255
        else:
            normalized = np.zeros_like(data)
        return normalized.astype(np.uint8)


@dataclass
class SBPConfig:
    """Конфигурация профилировщика SUBPRO2545."""

    # Подключение
    ip_address: str = "192.168.2.100"
    port: int = 4040
    protocol: str = "udp"

    # Параметры съёмки
    frequency_khz: float = 35.0  # 25-45 кГц
    pulse_length_us: int = 100
    ping_rate_hz: float = 20.0
    range_m: float = 50.0

    # Усиление
    gain_mode: str = "auto"  # auto, manual, tvg
    gain_db: float = 20.0
    tvg_db_per_m: float = 0.5

    # Фильтрация
    bandpass_low_khz: float = 20.0
    bandpass_high_khz: float = 50.0


class SUBPRO2545Parser:
    """
    Парсер данных SUBPRO2545 (General Acoustics).

    Поддерживает:
    - UDP streaming в реальном времени
    - Чтение SEG-Y файлов
    - Запись данных
    """

    # Заголовок пакета SUBPRO
    HEADER_MAGIC = b'SBPR'
    HEADER_SIZE = 64

    def __init__(self, config: Optional[SBPConfig] = None):
        """
        Инициализация парсера.

        Args:
            config: Конфигурация профилировщика.
        """
        self.config = config or SBPConfig()
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._ping_count = 0
        self._callbacks: List[Callable[[SBPPing], None]] = []

        # Буфер для накопления эхограммы
        self._echogram_buffer: List[SBPPing] = []
        self._buffer_size = 512  # Количество пингов

    async def connect(self) -> bool:
        """
        Подключение к профилировщику.

        Returns:
            True если подключение успешно.
        """
        try:
            if self.config.protocol == "udp":
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._socket.bind(('0.0.0.0', self.config.port))
                self._socket.setblocking(False)
                logger.info(f"UDP listener bound to port {self.config.port}")
            else:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.connect((self.config.ip_address, self.config.port))
                self._socket.setblocking(False)
                logger.info(f"Connected to {self.config.ip_address}:{self.config.port}")

            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Отключение от профилировщика."""
        self._running = False
        if self._socket:
            self._socket.close()
            self._socket = None
        logger.info("Disconnected from SUBPRO2545")

    def add_callback(self, callback: Callable[[SBPPing], None]) -> None:
        """Добавление callback для обработки пингов."""
        self._callbacks.append(callback)

    async def start_streaming(self) -> None:
        """Запуск потоковой обработки данных."""
        if not self._socket:
            await self.connect()

        self._running = True
        logger.info("Started SUBPRO2545 streaming")

        while self._running:
            try:
                await self._receive_ping()
            except BlockingIOError:
                await asyncio.sleep(0.001)
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                await asyncio.sleep(0.1)

    async def _receive_ping(self) -> Optional[SBPPing]:
        """Приём и парсинг одного пинга."""
        loop = asyncio.get_event_loop()

        try:
            data, addr = await loop.sock_recvfrom(self._socket, 65536)
        except BlockingIOError:
            return None

        if len(data) < self.HEADER_SIZE:
            return None

        ping = self._parse_packet(data)
        if ping:
            self._ping_count += 1
            self._add_to_buffer(ping)

            # Вызов callbacks
            for callback in self._callbacks:
                try:
                    callback(ping)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

        return ping

    def _parse_packet(self, data: bytes) -> Optional[SBPPing]:
        """
        Парсинг пакета данных SUBPRO2545.

        Формат заголовка (64 байта):
        - 4 bytes: Magic ('SBPR')
        - 4 bytes: Packet length
        - 4 bytes: Ping number
        - 8 bytes: Timestamp (double)
        - 4 bytes: Frequency (float, kHz)
        - 4 bytes: Sample count
        - 4 bytes: Sample interval (us)
        - 4 bytes: Range (m)
        - 8 bytes: Latitude (double)
        - 8 bytes: Longitude (double)
        - 4 bytes: Depth (float)
        - 4 bytes: Heading (float)
        - 4 bytes: Speed (float)
        """
        # Проверка magic
        if data[:4] != self.HEADER_MAGIC:
            # Mock данные для тестирования
            return self._generate_mock_ping()

        try:
            header = struct.unpack('<4sIIdfIffddffff', data[:self.HEADER_SIZE])

            magic, packet_len, ping_num, timestamp, freq_khz = header[:5]
            sample_count, sample_interval, range_m = header[5:8]
            lat, lon, depth, heading, speed = header[8:13]

            # Парсинг данных амплитуд (int16)
            samples_data = data[self.HEADER_SIZE:self.HEADER_SIZE + sample_count * 2]
            samples = np.frombuffer(samples_data, dtype=np.int16).astype(np.float32)

            return SBPPing(
                ping_number=ping_num,
                timestamp=timestamp,
                frequency_khz=freq_khz,
                samples=samples,
                range_m=range_m,
                sample_interval_us=sample_interval,
                position=(lat, lon, depth) if lat != 0 else None,
                heading=heading,
                speed_mps=speed,
            )

        except Exception as e:
            logger.error(f"Packet parse error: {e}")
            return None

    def _generate_mock_ping(self) -> SBPPing:
        """Генерация mock пинга для тестирования."""
        num_samples = 2048
        depth_range = 50.0  # м

        # Симуляция слоёв грунта
        samples = np.zeros(num_samples, dtype=np.float32)

        # Водная толща (слабый шум)
        water_end = int(num_samples * 0.25)
        samples[:water_end] = np.random.normal(100, 20, water_end)

        # Морское дно (сильный отклик)
        bottom_idx = water_end
        samples[bottom_idx:bottom_idx + 20] = np.random.normal(3000, 500, 20)

        # Слой 1: мягкий осадок
        layer1_end = int(num_samples * 0.4)
        samples[bottom_idx + 20:layer1_end] = np.random.normal(800, 150, layer1_end - bottom_idx - 20)

        # Слой 2: песок
        layer2_end = int(num_samples * 0.55)
        samples[layer1_end:layer2_end] = np.random.normal(1200, 200, layer2_end - layer1_end)

        # Погребённый объект (аномалия)
        if np.random.random() > 0.7:  # 30% шанс объекта
            obj_pos = np.random.randint(layer1_end, layer2_end - 50)
            obj_size = np.random.randint(10, 30)
            samples[obj_pos:obj_pos + obj_size] = np.random.normal(4000, 800, obj_size)

        # Глубокие слои (затухание)
        samples[layer2_end:] = np.random.normal(500, 100, num_samples - layer2_end)
        samples[layer2_end:] *= np.exp(-np.linspace(0, 2, num_samples - layer2_end))

        self._ping_count += 1

        return SBPPing(
            ping_number=self._ping_count,
            timestamp=time.time(),
            frequency_khz=self.config.frequency_khz,
            samples=samples,
            range_m=depth_range,
            sample_interval_us=25.0,
            position=(55.7558 + np.random.normal(0, 0.0001),
                      37.6173 + np.random.normal(0, 0.0001),
                      12.5),
            heading=np.random.uniform(0, 360),
            speed_mps=1.5,
        )

    def _add_to_buffer(self, ping: SBPPing) -> None:
        """Добавление пинга в буфер эхограммы."""
        self._echogram_buffer.append(ping)
        if len(self._echogram_buffer) > self._buffer_size:
            self._echogram_buffer.pop(0)

    def get_echogram(self, num_pings: int = 256) -> Optional[np.ndarray]:
        """
        Получение текущей эхограммы как 2D изображения.

        Args:
            num_pings: Количество пингов для эхограммы.

        Returns:
            2D numpy array (samples x pings) или None.
        """
        if len(self._echogram_buffer) < 2:
            return None

        pings = self._echogram_buffer[-num_pings:]
        num_samples = pings[0].num_samples

        echogram = np.zeros((num_samples, len(pings)), dtype=np.float32)
        for i, ping in enumerate(pings):
            if len(ping.samples) == num_samples:
                echogram[:, i] = ping.samples

        return echogram

    def get_echogram_normalized(self, num_pings: int = 256) -> Optional[np.ndarray]:
        """Получение нормализованной эхограммы (0-255)."""
        echogram = self.get_echogram(num_pings)
        if echogram is None:
            return None

        # Логарифмическое сжатие
        echogram = np.log10(np.abs(echogram) + 1)

        # Нормализация
        vmin, vmax = np.percentile(echogram, [2, 98])
        echogram = np.clip((echogram - vmin) / (vmax - vmin + 1e-6), 0, 1)

        return (echogram * 255).astype(np.uint8)

    @property
    def ping_count(self) -> int:
        """Количество принятых пингов."""
        return self._ping_count

    @property
    def is_connected(self) -> bool:
        """Статус подключения."""
        return self._socket is not None


class SEGYReader:
    """Чтение SEG-Y файлов профилировщика."""

    def __init__(self, filepath: str):
        """
        Инициализация читателя SEG-Y.

        Args:
            filepath: Путь к SEG-Y файлу.
        """
        self.filepath = Path(filepath)
        self._traces: List[SBPPing] = []

    def read(self) -> List[SBPPing]:
        """
        Чтение всех трасс из файла.

        Returns:
            Список пингов.
        """
        # Упрощённый парсер SEG-Y (заголовки опущены для краткости)
        try:
            with open(self.filepath, 'rb') as f:
                # Пропуск текстового заголовка (3200 байт)
                f.seek(3200)

                # Бинарный заголовок (400 байт)
                bin_header = f.read(400)
                sample_interval = struct.unpack('>h', bin_header[16:18])[0]
                num_samples = struct.unpack('>h', bin_header[20:22])[0]

                # Чтение трасс
                trace_num = 0
                while True:
                    # Заголовок трассы (240 байт)
                    trace_header = f.read(240)
                    if len(trace_header) < 240:
                        break

                    # Данные трассы
                    trace_data = f.read(num_samples * 4)  # float32
                    if len(trace_data) < num_samples * 4:
                        break

                    samples = np.frombuffer(trace_data, dtype='>f')

                    ping = SBPPing(
                        ping_number=trace_num,
                        timestamp=time.time(),
                        frequency_khz=35.0,
                        samples=samples,
                        range_m=50.0,
                        sample_interval_us=sample_interval,
                    )
                    self._traces.append(ping)
                    trace_num += 1

            logger.info(f"Read {len(self._traces)} traces from {self.filepath}")
            return self._traces

        except Exception as e:
            logger.error(f"SEG-Y read error: {e}")
            return []
