# BlueOS Sub-Bottom Profiler AI Module

Модуль обработки данных профилировщика донного грунта (Sub-Bottom Profiler) с AI-ускорением на Hailo-8L для BlueOS / Raspberry Pi 5.

## Поддерживаемое оборудование

### SUBPRO2545 (General Acoustics)

| Параметр | Значение |
|----------|----------|
| Вертикальное разрешение | 1-2 см (лучшее в классе) |
| Проникновение в грунт | 15+ м |
| Частоты | 25-45 кГц |
| Внутреннее разрешение | 1 мм |
| Цена | $50-90K |

**Рекомендация:** ТОП выбор для бюджетных высокочастотных исследований

## Архитектура системы

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BlueOS (RPi 5)                              │
├─────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    SBP AI Extension                           │ │
│  │                                                               │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────────────┐ │ │
│  │  │ SUBPRO2545  │  │   Hailo-8L  │  │      FastAPI          │ │ │
│  │  │   Parser    │  │  Inference  │  │   REST + WebSocket    │ │ │
│  │  │ (25-45kHz)  │  │   Engine    │  │                       │ │ │
│  │  └──────┬──────┘  └──────┬──────┘  └───────────┬───────────┘ │ │
│  │         │                │                     │             │ │
│  │         └────────┬───────┴─────────────────────┘             │ │
│  │                  │                                            │ │
│  │         ┌────────▼────────┐                                  │ │
│  │         │   AI Analysis   │                                  │ │
│  │         │ • Layer detect  │                                  │ │
│  │         │ • Object detect │                                  │ │
│  │         │ • Sediment class│                                  │ │
│  │         └────────┬────────┘                                  │ │
│  │                  │                                            │ │
│  │         ┌────────▼────────┐                                  │ │
│  │         │    MAVLink      │                                  │ │
│  │         │   + QGround     │                                  │ │
│  │         └─────────────────┘                                  │ │
│  └───────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│                       Hardware Layer                                │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │  RPi 5   │  │ Hailo-8L │  │ Ethernet/  │  │   SUBPRO2545    │  │
│  │  (8GB)   │  │ (13TOPS) │  │  Serial    │  │   (25-45kHz)    │  │
│  └──────────┘  └──────────┘  └────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Возможности AI-анализа

### 1. Автоматическая сегментация слоёв грунта

Нейросеть на Hailo-8L анализирует эхограммы и выделяет:
- Границы седиментных слоёв
- Глубину залегания коренных пород
- Аномалии в структуре дна

```python
# Пример выхода сегментации
{
    "layers": [
        {"depth_m": 0.0, "type": "water", "thickness_m": 12.5},
        {"depth_m": 12.5, "type": "soft_sediment", "thickness_m": 3.2},
        {"depth_m": 15.7, "type": "sand", "thickness_m": 5.1},
        {"depth_m": 20.8, "type": "clay", "thickness_m": 4.3},
        {"depth_m": 25.1, "type": "bedrock", "thickness_m": null}
    ],
    "penetration_m": 15.3,
    "confidence": 0.89
}
```

### 2. Детекция подводных объектов

Обнаружение погребённых объектов:
- Трубопроводы и кабели
- Затонувшие суда/обломки
- Археологические артефакты
- Боеприпасы (UXO)

### 3. Классификация типов грунта

| Класс | Описание | Акустический признак |
|-------|----------|---------------------|
| Ил (Mud) | Мягкий, высокое поглощение | Слабый отклик |
| Песок (Sand) | Средняя плотность | Умеренный отклик |
| Гравий (Gravel) | Грубый материал | Сильное рассеяние |
| Глина (Clay) | Плотный, слоистый | Чёткие границы |
| Скала (Rock) | Коренная порода | Сильное отражение |

## Технические требования

### Аппаратное обеспечение

| Компонент | Требование |
|-----------|------------|
| Raspberry Pi | RPi 5, 8GB RAM |
| AI Accelerator | Hailo-8L (M.2 HAT+) |
| Питание | 27W USB-C PD |
| Охлаждение | Active Cooler |
| Хранилище | NVMe SSD 128GB+ (для записи данных) |

### Подключение SUBPRO2545

| Интерфейс | Параметры |
|-----------|-----------|
| Ethernet | 1 Gbps, UDP/TCP |
| Формат данных | SEG-Y / проприетарный |
| Частота кадров | 10-50 Hz (зависит от глубины) |

## Структура проекта

```
blueos_sbp_ai_module/
├── README.md
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── config/
│   ├── extension.json
│   ├── hailo_config.yaml
│   ├── subpro_config.yaml      # Настройки SUBPRO2545
│   └── sediment_classes.yaml   # Классы грунтов
├── models/
│   ├── layer_segmentation.hef  # U-Net для сегментации
│   ├── object_detector.hef     # YOLOv8 для объектов
│   └── sediment_classifier.hef # ResNet для классификации
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── sbp_parser.py           # Парсер данных SUBPRO2545
│   ├── hailo_inference.py      # AI inference
│   ├── layer_analysis.py       # Анализ слоёв
│   ├── object_detection.py     # Детекция объектов
│   ├── api/
│   │   ├── routes.py
│   │   └── websocket.py
│   └── mavlink/
│       └── integration.py
├── web/
│   ├── index.html              # Визуализация эхограмм
│   └── viewer.js
└── tests/
```

## Конфигурация SUBPRO2545

```yaml
# config/subpro_config.yaml
device:
  name: "SUBPRO2545"
  manufacturer: "General Acoustics"

connection:
  type: "ethernet"
  ip: "192.168.2.100"
  port: 4040
  protocol: "udp"

acquisition:
  frequency_khz:
    min: 25
    max: 45
    default: 35
  pulse_length_us: 100
  ping_rate_hz: 20

  # Разрешение
  vertical_resolution_cm: 1.5
  horizontal_resolution_m: 0.5

processing:
  gain_mode: "auto"  # auto | manual | tvg
  tvg_db_per_m: 0.5
  filter_bandpass: [20, 50]  # kHz

recording:
  format: "segy"  # segy | raw | both
  output_dir: "/data/sbp"
  auto_split_mb: 500
```

## AI Модели

### 1. Layer Segmentation (U-Net)

Сегментация слоёв грунта на эхограммах.

| Параметр | Значение |
|----------|----------|
| Архитектура | U-Net (MobileNetV3 encoder) |
| Входной размер | 512 x 256 (range x time) |
| Классы | 6 (water, mud, sand, clay, gravel, rock) |
| FPS на Hailo-8L | ~25 |

### 2. Object Detector (YOLOv8n)

Детекция погребённых объектов.

| Параметр | Значение |
|----------|----------|
| Архитектура | YOLOv8 nano |
| Входной размер | 640 x 640 |
| Классы | pipe, cable, wreck, debris, uxo |
| FPS на Hailo-8L | ~40 |

### 3. Sediment Classifier (MobileNetV3)

Классификация типа грунта по текстуре эхо-сигнала.

| Параметр | Значение |
|----------|----------|
| Архитектура | MobileNetV3-small |
| Входной размер | 224 x 224 |
| Классы | 5 типов грунта |
| FPS на Hailo-8L | ~60 |

## API Endpoints

### REST API

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/v1/status` | GET | Статус системы и SUBPRO |
| `/api/v1/ping` | GET | Текущий пинг (эхограмма) |
| `/api/v1/layers` | GET | Анализ слоёв (последний) |
| `/api/v1/objects` | GET | Обнаруженные объекты |
| `/api/v1/sediment` | GET | Классификация грунта |
| `/api/v1/config` | GET/PUT | Настройки SUBPRO |
| `/api/v1/recording/start` | POST | Начать запись |
| `/api/v1/recording/stop` | POST | Остановить запись |

### WebSocket

```javascript
// ws://device:8080/ws/echogram
{
  "type": "echogram",
  "data": {
    "ping_number": 12345,
    "timestamp": 1706745600.123,
    "range_m": 50,
    "samples": [...],  // Амплитуды
    "layers": [...],   // AI-сегментация
    "objects": [...]   // Детекции
  }
}
```

## Быстрый старт

### 1. Установка

```bash
# Клонирование
git clone https://github.com/yourname/blueos-sbp-ai.git
cd blueos-sbp-ai

# Сборка Docker образа
docker build -t sbp-ai-module:latest -f docker/Dockerfile .
```

### 2. Настройка SUBPRO2545

```bash
# Редактирование конфига
nano config/subpro_config.yaml

# Проверка связи с профилировщиком
ping 192.168.2.100
```

### 3. Запуск

```bash
docker run --privileged \
  --network host \
  -v /dev:/dev \
  -v /data/sbp:/data/sbp \
  -p 8080:8080 \
  sbp-ai-module:latest
```

### 4. Доступ к интерфейсу

- Web UI: `http://device:8080/`
- API Docs: `http://device:8080/api/docs`
- WebSocket: `ws://device:8080/ws/echogram`

## Визуализация

### Web-интерфейс

Модуль включает real-time визуализацию:
- Эхограмма с цветовой шкалой
- Наложение AI-сегментации слоёв
- Маркеры обнаруженных объектов
- График глубины проникновения

### Интеграция с QGroundControl

Данные передаются через MAVLink:
- `NAMED_VALUE_FLOAT`: глубина воды, проникновение
- `DEBUG_VECT`: позиция ROV + данные SBP
- `STATUSTEXT`: предупреждения об объектах

## Производительность

| Операция | Latency | Throughput |
|----------|---------|------------|
| Парсинг SUBPRO данных | <5 ms | 50 pings/s |
| AI сегментация слоёв | ~40 ms | 25 fps |
| Детекция объектов | ~25 ms | 40 fps |
| Классификация грунта | ~17 ms | 60 fps |
| Полный pipeline | ~60 ms | 15 fps |

## Применение

- **Геотехнические изыскания** - анализ грунта перед строительством
- **Прокладка кабелей/труб** - выбор оптимального маршрута
- **Археология** - поиск затонувших объектов
- **Экология** - исследование донных отложений
- **Безопасность** - обнаружение UXO (боеприпасов)

## Лицензия

MIT License

---

## Совместимость с другими профилировщиками

Модуль может быть адаптирован для:
- Meridata HD-SBP UHF
- EdgeTech 3100
- Innomar SES-2000
- Kongsberg TOPAS

Требуется разработка соответствующего парсера данных.
