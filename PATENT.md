# ПАТЕНТНАЯ ДЕКЛАРАЦИЯ И ОПИСАНИЕ АКТИВА

## PATENT DECLARATION AND ASSET DESCRIPTION

---

## 1. ОБЩИЕ СВЕДЕНИЯ / GENERAL INFORMATION

| Параметр / Parameter | Значение / Value |
|---------------------|------------------|
| **Наименование актива** | Underwater AI Sensing Platform (UAISP) |
| **Asset Name** | Underwater AI Sensing Platform |
| **Владелец/Изобретатель** | Leonidy431 |
| **Owner/Inventor** | Leonidy431 |
| **Дата создания** | 2024-2026 |
| **Creation Date** | 2024-2026 |
| **Статус** | Proprietary Technology / Trade Secret |
| **Status** | Проприетарная технология / Коммерческая тайна |
| **Классификация актива** | Программное обеспечение (Software) / Embedded AI |
| **Asset Classification** | Software / Embedded Artificial Intelligence |
| **Версия документа** | 1.0.0 |
| **Document Version** | 1.0.0 |

---

## 2. АННОТАЦИЯ / ABSTRACT

### 2.1 Краткое описание (RU)

Настоящий документ описывает комплексную программную платформу для
подводных исследований на базе искусственного интеллекта, включающую:

1. **Fish Color Analyzer Module** - модуль спектрального анализа цвета
   чешуи рыб с использованием 6-канального датчика AS7262 (450-650 нм)

2. **BlueOS Fish AI Module** - модуль нейросетевой детекции и классификации
   рыб на базе ускорителя Hailo-8L для платформы Raspberry Pi 5

3. **BlueOS SBP AI Module** - модуль археологической детекции для
   профилировщика донного грунта SUBPRO2545 с AI-обработкой на Hailo-8L

### 2.2 Abstract (EN)

This document describes a comprehensive software platform for underwater
research based on artificial intelligence, including:

1. **Fish Color Analyzer Module** - spectral color analysis module for fish
   scales using 6-channel AS7262 sensor (450-650 nm range)

2. **BlueOS Fish AI Module** - neural network fish detection and classification
   module based on Hailo-8L accelerator for Raspberry Pi 5 platform

3. **BlueOS SBP AI Module** - archaeological detection module for SUBPRO2545
   sub-bottom profiler with AI processing on Hailo-8L

---

## 3. ОБЛАСТЬ ТЕХНИКИ / TECHNICAL FIELD

### 3.1 Международная патентная классификация (МПК/IPC)

| Код / Code | Описание / Description |
|-----------|------------------------|
| G01N 21/27 | Исследование материалов с помощью оптических средств - спектрофотометрия |
| G01N 21/25 | Цвет; Спектральные свойства |
| G06N 3/08 | Обучаемые нейронные сети |
| G06V 20/05 | Underwater image analysis |
| G01S 7/52 | Системы обработки гидроакустических сигналов |
| G01V 1/38 | Сейсмическая разведка - обработка данных |
| G06F 18/24 | Классификация с использованием машинного обучения |

### 3.2 Ключевые технологии / Key Technologies

- Спектральный анализ видимого диапазона (Visible Spectrum Analysis)
- Машинное зрение (Computer Vision)
- Нейросетевой inference на edge-устройствах (Edge AI Inference)
- Акустическое профилирование дна (Sub-Bottom Acoustic Profiling)
- Семантическая сегментация слоёв грунта (Sediment Layer Segmentation)
- Археологическая детекция объектов (Archaeological Object Detection)

---

## 4. УРОВЕНЬ ТЕХНИКИ / BACKGROUND ART

### 4.1 Существующие решения и их ограничения

Современные системы подводных исследований имеют следующие ограничения:

1. **Спектральный анализ**: Существующие решения требуют лабораторного
   оборудования, не адаптированы для работы в реальном времени под водой

2. **Детекция рыб**: Большинство систем требуют облачной обработки,
   что неприменимо для автономных подводных аппаратов (ROV/AUV)

3. **Археологическая разведка**: Интерпретация данных профилировщиков
   требует высокой квалификации и выполняется вручную

### 4.2 Научные источники / Scientific References

1. Colorimetric data and ANN for fish freshness assessment
   (ScienceDirect, 2022) - DOI:10.1016/j.heliyon.2022.e10987

2. Emerging approaches for fish freshness evaluation based on color
   (PMC, 2022) - PMID: 35880755

3. Spectral reflectance properties of fish scales
   (Journal of Experimental Biology, 2016)

4. Machine vision for food quality inspection
   (Computers and Electronics in Agriculture, 2023)

5. Deep learning for seismic interpretation
   (Geophysics, 2019)

---

## 5. ОПИСАНИЕ ИЗОБРЕТЕНИЯ / DESCRIPTION OF INVENTION

### 5.1 АКТИВ 1: Fish Color Analyzer Module

#### 5.1.1 Техническая спецификация

```
Компонент: color_fish_analyzer.py
Версия: 1.0.0
Строк кода: 600+
Лицензия: Proprietary
```

#### 5.1.2 Аппаратная база

| Параметр | Значение |
|----------|----------|
| Датчик | ams-OSRAM AS7262 |
| Тип | 6-канальный спектральный сенсор |
| Диапазон | 430-670 нм |
| Каналы | V(450), B(500), G(550), Y(570), O(600), R(650) нм |
| FWHM | ±40 нм на канал |
| Интерфейс | I2C (0x49) |
| Питание | 2.7-3.6 В |

#### 5.1.3 Классы и методы

```python
class AS7262Sensor:
    """
    Драйвер низкого уровня для AS7262.

    Methods:
        read_calibrated() -> Dict[str, float]
        set_led(current_ma: int) -> None
        get_temperature() -> int
    """

class ColorAnalyzer:
    """
    Научные алгоритмы анализа цвета.

    Methods:
        spectrum_to_xyz(spectrum) -> Tuple[float, float, float]
        xyz_to_lab(xyz, illuminant='D65') -> Tuple[float, float, float]
        spectrum_to_rgb(spectrum) -> Tuple[int, int, int]
        calculate_hsv(rgb) -> Tuple[float, float, float]
        classify_fish_color(hsv) -> str
        assess_freshness(spectrum, lab) -> Dict
    """

class FishColorAnalyzer:
    """
    Высокоуровневый API для анализа рыб.

    Methods:
        measure_and_analyze() -> Dict
        start() -> None  # Background thread
        stop() -> None
        get_latest() -> Optional[Dict]
        get_history(count: int) -> List[Dict]
    """
```

#### 5.1.4 Научные методы

**Метод 1: Преобразование спектра в CIE XYZ**
```
X = Σ(spectrum_i × x̄_i)
Y = Σ(spectrum_i × ȳ_i)
Z = Σ(spectrum_i × z̄_i)
```
Где x̄, ȳ, z̄ - весовые коэффициенты CIE 1931.

**Метод 2: Оценка свежести рыбы (TVB-N корреляция)**
```
chroma = sqrt(a*² + b*²)
spectral_ratio = (red + orange) / (blue + green)
freshness_score = 0.4×(chroma/50) + 0.3×(L*/100) + 0.3×(spectral_ratio/2)
```

| Оценка | Статус | Описание |
|--------|--------|----------|
| ≥ 0.6 | Свежая | Яркий, насыщенный цвет |
| 0.4-0.6 | Допустимая | Умеренные изменения |
| < 0.4 | Несвежая | Тусклый оттенок |

---

### 5.2 АКТИВ 2: BlueOS Fish AI Module

#### 5.2.1 Техническая спецификация

```
Директория: blueos_fish_ai_module/
Компоненты:
  - src/hailo_inference.py      (433 lines)
  - src/data_fusion.py          (356 lines)
  - src/api/routes.py           (393 lines)
  - src/mavlink/integration.py  (358 lines)
  - web/index.html              (Real-time UI)
  - docker/Dockerfile           (BlueOS extension)
  - tests/test_color_analyzer.py
```

#### 5.2.2 Аппаратная платформа

| Компонент | Спецификация |
|-----------|--------------|
| SoC | Raspberry Pi 5 |
| CPU | BCM2712 Quad-core Cortex-A76 @ 2.4GHz |
| RAM | 4-8 GB LPDDR4X |
| NPU | Hailo-8L (13 TOPS) |
| Interface | M.2 HAT / PCIe |
| Camera | любая USB/CSI камера |
| Sensor | AS7262 (I2C) |

#### 5.2.3 AI модели

| Модель | Архитектура | Назначение | Input Size |
|--------|-------------|------------|------------|
| Detector | YOLOv8n | Детекция рыб | 640×640 |
| Classifier | MobileNetV3 | Классификация видов | 224×224 |

#### 5.2.4 Ключевые классы

```python
@dataclass
class Detection:
    """Результат детекции."""
    bbox: Tuple[int, int, int, int]
    class_id: int
    class_name: str
    confidence: float

@dataclass
class ClassificationResult:
    """Результат классификации вида."""
    class_id: int
    class_name: str
    confidence: float
    top_k: List[Tuple[int, str, float]]

class HailoInferenceEngine:
    """
    Движок inference на Hailo-8L NPU.

    Async Methods:
        initialize() -> bool
        detect(frame, conf_thresh, nms_thresh) -> List[Detection]
        classify(image, top_k) -> ClassificationResult
        shutdown() -> None
    """

class DataFusionEngine:
    """
    Слияние данных визуальной детекции и спектрального анализа.

    Methods:
        fuse(detection, classification, color) -> FusedResult
        add_species_profile(profile) -> None
    """
```

#### 5.2.5 REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/status` | GET | System status |
| `/api/v1/detect` | POST | Detect fish in image |
| `/api/v1/classify` | POST | Classify fish species |
| `/api/v1/color` | GET | Get color sensor data |
| `/api/v1/analysis` | POST | Full analysis pipeline |
| `/api/v1/species` | GET | List supported species |
| `/api/v1/stats` | GET | Inference statistics |

#### 5.2.6 MAVLink интеграция

Передача телеметрии в QGroundControl:

| Параметр | MAVLink Name | Тип |
|----------|--------------|-----|
| Кол-во рыб | FISH_CNT | NAMED_VALUE_FLOAT |
| Уверенность | FISH_CONF | NAMED_VALUE_FLOAT |
| Оттенок цвета | COLOR_HUE | NAMED_VALUE_FLOAT |
| Насыщенность | COLOR_SAT | NAMED_VALUE_FLOAT |
| Свежесть | FRESH_SCR | NAMED_VALUE_FLOAT |
| RGB вектор | FISH_RGB | DEBUG_VECT |

---

### 5.3 АКТИВ 3: BlueOS SBP AI Module

#### 5.3.1 Техническая спецификация

```
Директория: blueos_sbp_ai_module/
Компоненты:
  - src/sbp_parser.py              (442 lines)
  - src/hailo_sbp_inference.py     (718 lines)
  - src/archaeological_detector.py  (526 lines)
  - src/api/routes.py              (387 lines)
  - src/mavlink/integration.py     (279 lines)
  - web/index.html                 (Echogram visualization)
  - docker/Dockerfile
  - tests/test_archaeological.py
```

#### 5.3.2 Профилировщик SUBPRO2545

| Параметр | Значение |
|----------|----------|
| Производитель | General Acoustics |
| Частотный диапазон | 25-45 кГц (chirp) |
| Вертикальное разрешение | 1-2 см |
| Проникновение в грунт | 15+ м |
| Протокол | UDP streaming / SEG-Y |
| Порт | 4040 |

#### 5.3.3 AI модели для SBP

| Модель | Архитектура | Назначение | Input |
|--------|-------------|------------|-------|
| layer_segmentation.hef | U-Net | Сегментация слоёв | 512×256 |
| object_detector.hef | YOLOv8 | Детекция объектов | 640×640 |
| sediment_classifier.hef | MobileNet | Тип грунта | 224×224 |
| archaeological_detector.hef | Custom | Арх. объекты | 640×640 |

#### 5.3.4 Классы донных осадков

```python
class SedimentType(Enum):
    WATER = 0    # Водная толща
    MUD = 1      # Ил
    SAND = 2     # Песок
    CLAY = 3     # Глина
    GRAVEL = 4   # Гравий
    ROCK = 5     # Скала
```

#### 5.3.5 Археологические классы объектов

```python
class ArchaeologicalClass(Enum):
    UNKNOWN = 0
    SHIPWRECK_WOODEN = 1      # Деревянное судно
    SHIPWRECK_METAL = 2       # Металлическое судно
    SHIPWRECK_FRAGMENT = 3    # Фрагмент судна
    ANCHOR_STONE = 4          # Каменный якорь
    ANCHOR_IRON = 5           # Железный якорь
    ANCHOR_ADMIRALTY = 6      # Адмиралтейский якорь
    AMPHORA = 7               # Амфора
    CERAMIC_CLUSTER = 8       # Скопление керамики
    STONE_STRUCTURE = 9       # Каменная структура
    WOODEN_STRUCTURE = 10     # Деревянная структура
    BALLAST_PILE = 11         # Балластная куча
    CARGO_SCATTER = 12        # Россыпь груза
    CANNON = 13               # Пушка
    METAL_ARTIFACT = 14       # Металлический артефакт
```

#### 5.3.6 Датировка по глубине залегания

| Период | Глубина залегания | Возраст |
|--------|-------------------|---------|
| ANCIENT | 2.0-15.0 м | до 500 н.э. |
| MEDIEVAL | 1.0-8.0 м | 500-1500 |
| EARLY_MODERN | 0.5-5.0 м | 1500-1800 |
| MODERN | 0.0-3.0 м | 1800-1950 |
| CONTEMPORARY | 0.0-1.0 м | после 1950 |

#### 5.3.7 Алгоритм оценки научной ценности

```python
def calculate_scientific_value(obj: ArchaeologicalObject) -> float:
    """
    Расчёт научной ценности археологического объекта.

    Критерии:
    1. Редкость типа объекта (0.3-0.9)
    2. Древность периода (0.1-0.5)
    3. Размер объекта (0.1-0.2)
    4. Уверенность детекции (множитель)

    Returns:
        value: float (0.0-1.0)
    """
```

#### 5.3.8 REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/echogram` | GET | Get echogram image |
| `/api/v1/layers` | GET | Layer segmentation |
| `/api/v1/objects` | GET | Detected objects |
| `/api/v1/archaeological` | GET | Archaeological report |
| `/api/v1/archaeological/sites` | GET | Discovered sites |
| `/api/v1/analyze` | POST | Full analysis |
| `/api/v1/sediment` | GET | Sediment classification |
| `/ws/stream` | WS | Real-time data stream |

---

## 6. ФОРМУЛА ИЗОБРЕТЕНИЯ / CLAIMS

### Пункт 1 (независимый)

Система анализа цвета подводных объектов, содержащая:
- 6-канальный спектральный датчик видимого диапазона (450-650 нм);
- микроконтроллер с I2C интерфейсом;
- программный модуль преобразования спектра в CIE XYZ/L*a*b*/RGB;
- алгоритм оценки свежести на основе корреляции с TVB-N;
**отличающаяся тем, что** обработка производится в реальном времени
на встроенном процессоре подводного аппарата.

### Пункт 2 (зависимый)

Система по п.1, **отличающаяся тем, что** дополнительно содержит:
- нейросетевой ускоритель Hailo-8L (13 TOPS);
- модели YOLOv8 для детекции объектов;
- модели классификации видов рыб;
- модуль слияния данных детекции и спектрального анализа.

### Пункт 3 (зависимый)

Система по п.2, **отличающаяся тем, что** реализована как
расширение BlueOS с Docker-контейнеризацией и REST API.

### Пункт 4 (независимый)

Система археологической детекции в донных отложениях, содержащая:
- профилировщик донного грунта (25-45 кГц);
- нейросетевой ускоритель для edge-inference;
- модель сегментации слоёв грунта (U-Net);
- модель детекции погребённых объектов (YOLOv8);
- классификатор археологических объектов (14 классов);
**отличающаяся тем, что** система автоматически оценивает
исторический период объекта по глубине залегания.

### Пункт 5 (зависимый)

Система по п.4, **отличающаяся тем, что** дополнительно содержит:
- алгоритм расчёта научной ценности объекта;
- модуль группировки объектов в археологические памятники;
- WebSocket streaming для визуализации эхограммы в реальном времени.

---

## 7. ТЕХНИЧЕСКОЕ ИСПОЛНЕНИЕ / IMPLEMENTATION

### 7.1 Требования к окружению

```
Python: 3.9+
OS: Linux (Raspberry Pi OS, Ubuntu)
Hardware: Raspberry Pi 5 + Hailo-8L M.2 HAT
```

### 7.2 Зависимости

```
# Core
numpy>=1.21.0
smbus>=1.1.0

# AI/ML
hailo-platform>=4.14.0
opencv-python>=4.5.0

# API
fastapi>=0.100.0
uvicorn>=0.22.0
pydantic>=2.0.0

# MAVLink
pymavlink>=2.4.0

# Logging
loguru>=0.7.0
```

### 7.3 Docker deployment

```dockerfile
FROM python:3.11-slim-bookworm

# Hailo Runtime
RUN apt-get update && apt-get install -y \
    libhailort libhailort-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## 8. ПРОМЫШЛЕННАЯ ПРИМЕНИМОСТЬ / INDUSTRIAL APPLICABILITY

### 8.1 Области применения

| Отрасль | Применение |
|---------|------------|
| Рыбная промышленность | Оценка свежести улова |
| Морская биология | Идентификация видов |
| Подводная археология | Разведка памятников |
| Нефтегазовая отрасль | Инспекция трубопроводов |
| Оборонная сфера | Обнаружение затонувших объектов |
| ROV/AUV | Автономная навигация |

### 8.2 Экономический эффект

- Сокращение времени анализа свежести рыбы в 10-100 раз
- Автоматизация археологической разведки
- Работа в реальном времени на edge-устройствах
- Отсутствие необходимости облачного подключения

---

## 9. СТАТУС ИНТЕЛЛЕКТУАЛЬНОЙ СОБСТВЕННОСТИ

### 9.1 Права

| Право | Статус |
|-------|--------|
| Авторское право | Защищено (©2024-2026 Leonidy431) |
| Коммерческая тайна | Да |
| Патентная заявка | В подготовке |
| Открытая лицензия | Нет |

### 9.2 Ограничения использования

1. Запрещено копирование и распространение без письменного согласия
2. Запрещено декомпилирование и реверс-инжиниринг
3. Использование только в рамках лицензионного соглашения
4. Запрещена передача третьим лицам

---

## 10. ИСТОРИЯ ВЕРСИЙ / VERSION HISTORY

| Версия | Дата | Изменения |
|--------|------|-----------|
| 0.1.0 | 2024-01 | Начальная разработка AS7262 драйвера |
| 0.2.0 | 2024-03 | Добавлен ColorAnalyzer |
| 0.3.0 | 2024-06 | BlueOS Fish AI Module |
| 0.4.0 | 2024-09 | BlueOS SBP AI Module |
| 0.5.0 | 2024-11 | Web UI для обоих модулей |
| 0.6.0 | 2025-01 | MAVLink интеграция |
| 1.0.0 | 2026-02 | Стабильный релиз |

---

## 11. КОНТАКТНАЯ ИНФОРМАЦИЯ

**Владелец актива:** Leonidy431
**Repository:** github.com/Leonidy431/color_sensor
**Статус:** Private / Proprietary

---

## 12. ПОДПИСИ / SIGNATURES

```
Владелец/Изобретатель: Leonidy431
Дата: 2026-02-07

_________________________________
(подпись / signature)
```

---

**КОНФИДЕНЦИАЛЬНО / CONFIDENTIAL**

Данный документ содержит сведения, составляющие коммерческую тайну.
Распространение без письменного разрешения владельца запрещено.

This document contains trade secret information.
Distribution without written permission from the owner is prohibited.

© 2024-2026 Leonidy431. All rights reserved.
