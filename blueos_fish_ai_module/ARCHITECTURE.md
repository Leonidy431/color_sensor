# Архитектура Fish AI Module

## Обзор

Модуль реализует конвейер обработки данных для идентификации рыб в реальном времени, объединяя визуальную детекцию (Hailo-8L) и спектральный анализ цвета (AS7262).

## Компоненты системы

### 1. Hailo Inference Engine

```
┌────────────────────────────────────────────────────────────┐
│                    Hailo-8L Pipeline                        │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   Camera Frame                                             │
│        │                                                   │
│        ▼                                                   │
│   ┌─────────────┐                                         │
│   │ Preprocess  │  Resize 640x640, Normalize              │
│   │ (CPU/GPU)   │  RGB → BGR, uint8 → float32             │
│   └──────┬──────┘                                         │
│          │                                                 │
│          ▼                                                 │
│   ┌─────────────┐                                         │
│   │   Hailo     │  YOLOv8n-fish.hef                       │
│   │  Runtime    │  Async inference, 13 TOPS               │
│   │  (NPU)      │  Batch size: 1-8                        │
│   └──────┬──────┘                                         │
│          │                                                 │
│          ▼                                                 │
│   ┌─────────────┐                                         │
│   │ Postprocess │  NMS, Confidence filtering              │
│   │ (CPU)       │  Box decoding, Class mapping            │
│   └──────┬──────┘                                         │
│          │                                                 │
│          ▼                                                 │
│   Detections [bbox, class, confidence]                    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

#### Оптимизация производительности

| Параметр | Значение | Описание |
|----------|----------|----------|
| Input format | NHWC uint8 | Нативный формат Hailo |
| Batch size | 2-4 | Баланс latency/throughput |
| Quantization | INT8 | Полная квантизация |
| Pipeline depth | 3 | Async prefetch |

### 2. Color Analysis Module

```
┌────────────────────────────────────────────────────────────┐
│                  AS7262 Color Pipeline                      │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   ┌─────────────┐      ┌─────────────┐                    │
│   │   AS7262    │ I2C  │   SMBus     │                    │
│   │   Sensor    │◄────►│   Driver    │                    │
│   └─────────────┘      └──────┬──────┘                    │
│                               │                            │
│                               ▼                            │
│                        Raw Spectrum                        │
│                   [V, B, G, Y, O, R]                       │
│                               │                            │
│          ┌────────────────────┼────────────────────┐      │
│          ▼                    ▼                    ▼      │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐│
│   │  XYZ→Lab    │     │ Spectrum→RGB│     │  Freshness  ││
│   │  Transform  │     │   Mapping   │     │   Score     ││
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘│
│          │                   │                   │        │
│          └───────────────────┼───────────────────┘        │
│                              ▼                            │
│                     Color Analysis Result                 │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 3. Data Fusion Layer

Слияние данных от двух сенсоров:

```python
class FusionResult:
    detection: DetectionResult     # Hailo output
    color: ColorAnalysisResult     # AS7262 output
    species: SpeciesClassification # Combined inference
    confidence: float              # Fused confidence
    timestamp: float
```

#### Алгоритм слияния

1. **Temporal alignment** - синхронизация по timestamp (±50ms)
2. **Spatial ROI** - цвет анализируется только в области детекции
3. **Confidence fusion** - взвешенная комбинация:
   ```
   final_conf = 0.7 × detection_conf + 0.3 × color_match_score
   ```
4. **Species refinement** - уточнение вида по цвету чешуи

### 4. API Layer

```
┌────────────────────────────────────────────────────────────┐
│                     FastAPI Server                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   HTTP Endpoints                    WebSocket              │
│   ┌─────────────┐                  ┌─────────────┐        │
│   │ /api/v1/*   │                  │ /ws/stream  │        │
│   │ REST JSON   │                  │ Real-time   │        │
│   └──────┬──────┘                  └──────┬──────┘        │
│          │                                │                │
│          └────────────┬───────────────────┘                │
│                       ▼                                    │
│              ┌─────────────┐                              │
│              │   Service   │                              │
│              │    Layer    │                              │
│              └──────┬──────┘                              │
│                     │                                      │
│     ┌───────────────┼───────────────┐                     │
│     ▼               ▼               ▼                     │
│ ┌────────┐    ┌──────────┐    ┌──────────┐              │
│ │ Hailo  │    │  Color   │    │  Fusion  │              │
│ │ Engine │    │ Analyzer │    │  Engine  │              │
│ └────────┘    └──────────┘    └──────────┘              │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Потоки данных

### Основной pipeline (30 FPS)

```
Camera (30fps)
    │
    ├──► Frame Buffer (ring, 3 frames)
    │         │
    │         ├──► Hailo Inference Thread
    │         │         │
    │         │         ▼
    │         │    Detection Queue
    │         │         │
    │         │         ├──► ROI Extraction
    │         │         │
    ▼         ▼         ▼
AS7262 ──► Color Queue ──► Fusion Thread
(1fps)                          │
                                ▼
                         Result Queue
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
               WebSocket    REST API    MAVLink
```

### Потоки и очереди

| Поток | Приоритет | Описание |
|-------|-----------|----------|
| CameraThread | High | Захват кадров |
| HailoThread | High | GPU inference |
| ColorThread | Normal | I2C чтение |
| FusionThread | Normal | Слияние данных |
| APIThread | Low | HTTP/WS сервер |

## Модель памяти

```
Total RAM: 8GB (RPi5)
├── System: ~1GB
├── BlueOS: ~500MB
├── Fish AI Module: ~2GB
│   ├── Hailo Runtime: ~500MB
│   ├── Model buffers: ~200MB
│   ├── Frame buffers: ~100MB
│   ├── Python heap: ~500MB
│   └── Reserve: ~700MB
└── Available: ~4.5GB
```

## Конфигурация Hailo Runtime

### Оптимальные настройки

```yaml
hailo:
  device_id: 0
  power_mode: "performance"  # performance | balanced | low_power

  scheduler:
    type: "round_robin"      # round_robin | priority

  inference:
    batch_size: 2
    timeout_ms: 100
    async_queue_depth: 3

  memory:
    input_buffer_pool: 4
    output_buffer_pool: 4
```

### Модели для детекции рыб

| Модель | Размер | FPS | mAP |
|--------|--------|-----|-----|
| YOLOv8n-fish | 6.3MB | 40 | 0.72 |
| YOLOv8s-fish | 22MB | 25 | 0.78 |
| MobileNetV3-fish | 4.1MB | 60 | 0.65 |

## Обработка ошибок

### Graceful degradation

```python
class FallbackStrategy:
    """Стратегия деградации при отказе компонентов."""

    HAILO_FAILURE = "color_only"      # Только анализ цвета
    COLOR_FAILURE = "detection_only"   # Только детекция
    CAMERA_FAILURE = "sensor_only"     # Только AS7262
    ALL_FAILURE = "maintenance_mode"   # Ожидание восстановления
```

### Мониторинг

- Watchdog для каждого потока (timeout 5s)
- Автоматический перезапуск при зависании
- Логирование в journald + локальный файл
- Метрики через Prometheus endpoint

## Интеграция с BlueOS

### Docker privileges

```json
{
  "HostConfig": {
    "Privileged": false,
    "Devices": [
      {"PathOnHost": "/dev/i2c-1", "PathInContainer": "/dev/i2c-1"},
      {"PathOnHost": "/dev/video0", "PathInContainer": "/dev/video0"},
      {"PathOnHost": "/dev/hailo0", "PathInContainer": "/dev/hailo0"}
    ],
    "Binds": [
      "/lib/firmware:/lib/firmware:ro",
      "/sys/class/hailo_chardev:/sys/class/hailo_chardev:ro"
    ]
  }
}
```

### Network ports

| Port | Protocol | Описание |
|------|----------|----------|
| 8080 | HTTP/WS | REST API + WebSocket |
| 9090 | HTTP | Prometheus metrics |
| 14550 | UDP | MAVLink |

## Тестирование

### Unit tests

```bash
pytest tests/ -v --cov=src
```

### Integration tests

```bash
# С реальным оборудованием
pytest tests/integration/ --hardware

# Mock режим
pytest tests/integration/ --mock
```

### Performance benchmarks

```bash
python -m scripts.benchmark --duration 60 --report
```
