# BlueOS Fish AI Module

Модуль для BlueOS на Raspberry Pi 5 с ускорителем Hailo-8L для определения типа рыбы и анализа цвета чешуи в реальном времени.

## Архитектура системы

```
┌─────────────────────────────────────────────────────────────────┐
│                      BlueOS (Docker Host)                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Fish AI Extension Container                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │   │
│  │  │   Hailo     │  │   AS7262    │  │    FastAPI      │  │   │
│  │  │  Inference  │  │   Color     │  │    REST API     │  │   │
│  │  │   Engine    │  │   Sensor    │  │    + WebSocket  │  │   │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │   │
│  │         │                │                   │           │   │
│  │         └────────┬───────┴───────────────────┘           │   │
│  │                  │                                        │   │
│  │         ┌────────▼────────┐                              │   │
│  │         │  Data Fusion    │                              │   │
│  │         │  & Analysis     │                              │   │
│  │         └────────┬────────┘                              │   │
│  │                  │                                        │   │
│  │         ┌────────▼────────┐                              │   │
│  │         │   MAVLink       │                              │   │
│  │         │   Integration   │                              │   │
│  │         └─────────────────┘                              │   │
│  └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                     Hardware Layer                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ RPi 5    │  │ Hailo-8L │  │ AS7262   │  │ Camera       │   │
│  │ (8GB)    │  │ (13TOPS) │  │ I2C      │  │ CSI/USB      │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Структура проекта

```
blueos_fish_ai_module/
├── README.md                    # Документация модуля
├── ARCHITECTURE.md              # Детальное описание архитектуры
├── docker/
│   ├── Dockerfile               # Образ контейнера
│   ├── docker-compose.yml       # Локальная разработка
│   └── permissions.json         # BlueOS permissions
├── config/
│   ├── extension.json           # BlueOS extension metadata
│   ├── hailo_config.yaml        # Настройки Hailo-8L
│   ├── fish_species.yaml        # База данных видов рыб
│   └── color_calibration.yaml   # Калибровка цвета
├── models/
│   ├── fish_classifier.hef      # Скомпилированная модель Hailo
│   ├── fish_detector_yolov8n.hef
│   └── model_info.json          # Метаданные моделей
├── src/
│   ├── __init__.py
│   ├── main.py                  # Точка входа
│   ├── hailo_inference.py       # Hailo-8L inference engine
│   ├── color_analyzer.py        # AS7262 интеграция
│   ├── fish_classifier.py       # Классификация рыб
│   ├── data_fusion.py           # Слияние данных
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # REST API endpoints
│   │   └── websocket.py         # Real-time streaming
│   ├── mavlink/
│   │   ├── __init__.py
│   │   └── integration.py       # MAVLink сообщения
│   └── utils/
│       ├── __init__.py
│       ├── camera.py            # Захват видео
│       └── logger.py            # Логирование
├── web/
│   ├── index.html               # Web UI
│   ├── style.css
│   └── app.js
├── tests/
│   ├── test_hailo.py
│   ├── test_color.py
│   └── test_api.py
├── scripts/
│   ├── install_hailo.sh         # Установка Hailo SDK
│   ├── convert_model.sh         # Конвертация моделей
│   └── calibrate_color.py       # Калибровка датчика
├── requirements.txt
└── setup.py
```

## Аппаратные требования

### Raspberry Pi 5
| Компонент | Требование |
|-----------|------------|
| Модель | Raspberry Pi 5 (8GB RAM рекомендуется) |
| Питание | 27W USB-C PD (5V/5A) |
| Охлаждение | Active Cooler обязательно |
| Хранилище | NVMe SSD 64GB+ (через M.2 HAT) |

### Hailo-8L AI Accelerator
| Параметр | Значение |
|----------|----------|
| Производительность | 13 TOPS (INT8) |
| Интерфейс | M.2 Key M (PCIe Gen3 x1) |
| Энергопотребление | ~2.5W типичное |
| Поддерживаемые сети | YOLOv5/v8, ResNet, MobileNet, etc. |

### AS7262 Spectral Sensor
| Параметр | Значение |
|----------|----------|
| Каналы | 6 (450, 500, 550, 570, 600, 650 нм) |
| Интерфейс | I2C (0x49) |
| Подключение | GPIO2/3 (SDA/SCL) |

### Камера
- Raspberry Pi Camera Module 3 (рекомендуется)
- USB камера с поддержкой V4L2
- Разрешение: минимум 640x480 @ 30fps

## Производительность

### Ожидаемые показатели

| Задача | FPS | Latency |
|--------|-----|---------|
| YOLOv8n детекция | 30-40 | ~25ms |
| Классификация рыб | 50-60 | ~18ms |
| Анализ цвета AS7262 | 1 | ~140ms |
| Полный pipeline | 25-30 | ~40ms |

### Оптимизации

1. **Параллелизм** - Hailo inference и AS7262 читаются асинхронно
2. **Batch processing** - группировка кадров для inference
3. **ROI processing** - анализ цвета только в области детекции
4. **Кэширование** - результаты классификации кэшируются

## Быстрый старт

### 1. Установка Hailo SDK

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Hailo
sudo apt install hailo-all
sudo reboot

# Проверка
hailortcli fw-control identify
```

### 2. Настройка PCIe Gen3

```bash
# /boot/firmware/config.txt
dtparam=pciex1_gen=3
```

### 3. Сборка Docker образа

```bash
cd blueos_fish_ai_module
docker build -t fish-ai-module:latest -f docker/Dockerfile .
```

### 4. Запуск

```bash
docker run --privileged \
  -v /dev:/dev \
  -v /lib/firmware:/lib/firmware:ro \
  -p 8080:8080 \
  fish-ai-module:latest
```

## API Endpoints

### REST API

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/v1/status` | GET | Статус системы |
| `/api/v1/detect` | POST | Детекция рыб на изображении |
| `/api/v1/classify` | POST | Классификация вида |
| `/api/v1/color` | GET | Текущие данные цвета |
| `/api/v1/analysis` | GET | Полный анализ (детекция + цвет) |
| `/api/v1/species` | GET | Список поддерживаемых видов |

### WebSocket

```javascript
ws://device:8080/ws/stream

// Сообщения
{
  "type": "detection",
  "data": {
    "fish": [...],
    "color": {...},
    "timestamp": 1706745600.123
  }
}
```

## Модели машинного обучения

### Детекция рыб (YOLOv8n-fish)
- Архитектура: YOLOv8 nano
- Входной размер: 640x640
- Классы: fish, not_fish
- Формат: HEF (Hailo Executable Format)

### Классификация видов (FishNet-lite)
- Архитектура: MobileNetV3-small
- Входной размер: 224x224
- Классы: 50+ видов рыб
- Формат: HEF

### Конвертация моделей

```bash
# ONNX → HEF
hailo parser onnx fish_classifier.onnx
hailo optimize fish_classifier.har
hailo compiler fish_classifier.har --hw-arch hailo8l
```

## Интеграция с BlueOS

### Extension Manifest

```json
{
  "name": "Fish AI Analyzer",
  "docker": "yourname/fish-ai-module",
  "version": "1.0.0",
  "permissions": {
    "devices": ["/dev/i2c-1", "/dev/video0", "/dev/hailo0"],
    "network": true
  }
}
```

### MAVLink интеграция

Модуль отправляет данные через MAVLink NAMED_VALUE_FLOAT:
- `FISH_COUNT` - количество обнаруженных рыб
- `FISH_CONF` - уверенность детекции
- `FISH_COLOR_H` - Hue доминирующего цвета
- `FISH_FRESH` - индекс свежести

## Калибровка

### Цветовая калибровка

1. Подготовьте белый эталон (SpectralON или PTFE)
2. Запустите скрипт калибровки:

```bash
python scripts/calibrate_color.py --white-reference
```

### Калибровка детекции

Для специфических условий освещения:

```bash
python scripts/calibrate_detection.py --exposure auto --gain 1.5
```

## Лицензия

MIT License
