# Fish Color Analyzer - AS7262

Система анализа цвета чешуи рыб и подводных объектов на базе 6-канального спектрального датчика AS7262.

## Описание

Модуль предназначен для определения цветовых характеристик рыб и подводных объектов с использованием спектрального анализа в видимом диапазоне. Интегрируется с BlueOS для подводных роботов и ROV.

## Датчик AS7262

### Технические характеристики

| Параметр | Значение |
|----------|----------|
| Производитель | ams-OSRAM |
| Тип | 6-канальный спектральный датчик видимого света |
| Диапазон | 430-670 нм |
| Интерфейс | I2C (адрес 0x49), UART |
| Напряжение питания | 2.7-3.6 В |
| Ток потребления | ~10 мА (активный режим) |

### Спектральные каналы

| Канал | Длина волны | FWHM | Цвет |
|-------|-------------|------|------|
| V | 450 нм | ±40 нм | Фиолетовый |
| B | 500 нм | ±40 нм | Синий |
| G | 550 нм | ±40 нм | Зелёный |
| Y | 570 нм | ±40 нм | Жёлтый |
| O | 600 нм | ±40 нм | Оранжевый |
| R | 650 нм | ±40 нм | Красный |

### Настройки усиления

- **1x** - яркое освещение
- **3.7x** - стандартные условия (по умолчанию)
- **16x** - слабое освещение
- **64x** - очень слабое освещение

### Время интеграции

- Диапазон: 2.8 - 714 мс
- Формула: `время_мс = значение_регистра × 2.8`
- Рекомендуемое: 50-100 единиц (140-280 мс)

## Научные методы анализа

### 1. Преобразование спектра в цветовые пространства

#### CIE XYZ
Спектральные данные преобразуются в CIE XYZ с использованием весовых коэффициентов на основе функций цветового соответствия CIE 1931:

```
X = Σ(спектр_i × x̄_i)
Y = Σ(спектр_i × ȳ_i)
Z = Σ(спектр_i × z̄_i)
```

#### CIE L\*a\*b\*
Преобразование XYZ → L\*a\*b\* для перцептуально-равномерного цветового пространства:

- **L\*** - светлота (0-100)
- **a\*** - красно-зелёная ось
- **b\*** - жёлто-синяя ось

Референсная белая точка: D65 (дневной свет)

### 2. Оценка свежести рыбы

Метод основан на корреляции цветовых параметров с **TVB-N** (Total Volatile Basic Nitrogen) - биохимическим индикатором порчи рыбы.

#### Научные основания

Исследования показали [[1]](https://www.sciencedirect.com/science/article/pii/S2772753X22001174):

- Параметр **a\*** (красный) снижается при хранении рыбы
- Параметр **b\*** изменяется от жёлтого к серому
- **Chroma** (насыщенность) коррелирует со свежестью (R² = 0.97)

#### Алгоритм оценки

```python
chroma = sqrt(a*² + b*²)
spectral_ratio = (красный + оранжевый) / (синий + зелёный)
freshness_score = 0.4 × (chroma/50) + 0.3 × (L*/100) + 0.3 × (spectral_ratio/2)
```

#### Классификация

| Оценка | Статус | Описание |
|--------|--------|----------|
| ≥ 0.6 | Свежая | Яркий, насыщенный цвет |
| 0.4-0.6 | Допустимая | Умеренное изменение цвета |
| < 0.4 | Несвежая | Тусклый, сероватый оттенок |

### 3. Классификация цвета

Используется HSV-преобразование с классификацией по оттенку (Hue):

| Диапазон H | Цвет |
|------------|------|
| 0-15°, 345-360° | Красная |
| 15-45° | Оранжевая |
| 45-75° | Жёлтая |
| 75-165° | Зелёная |
| 165-195° | Голубая |
| 195-255° | Синяя |
| 255-285° | Фиолетовая |
| S < 0.15 | Серебристая/Белая |

## Применение для подводных исследований

### Особенности измерений под водой

1. **Поглощение света водой** - красный свет затухает быстрее синего
2. **Рассеяние** - взвешенные частицы влияют на измерения
3. **Глубина** - ниже 10м красный канал малоинформативен

### Рекомендации

- Использовать встроенную LED-подсветку (25-50 мА)
- Расстояние до объекта: 5-20 мм
- Калибровка с белым эталоном перед погружением
- Учитывать температурный дрейф (датчик имеет встроенный термометр)

### Иридесценция чешуи

Многие виды рыб имеют иридесцентную (переливающуюся) чешую [[2]](https://pmc.ncbi.nlm.nih.gov/articles/PMC3302594/). Особенности:

- Цвет зависит от угла наблюдения
- Вызвана многослойной структурой кристаллов гуанина
- Рекомендуется усреднение нескольких измерений под разными углами

## Установка

### Требования

- Python 3.7+
- Raspberry Pi с включённым I2C
- Библиотека smbus

### Подключение

```
AS7262    Raspberry Pi
------    ------------
VCC   →   3.3V (Pin 1)
GND   →   GND (Pin 6)
SDA   →   SDA (Pin 3 / GPIO2)
SCL   →   SCL (Pin 5 / GPIO3)
```

### Включение I2C

```bash
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```

### Установка зависимостей

```bash
pip install smbus
```

## Использование

### Базовый пример

```python
from color_fish_analyzer import FishColorAnalyzer

# Инициализация
analyzer = FishColorAnalyzer(led_current=25)

# Однократное измерение
result = analyzer.measure_and_analyze()

print(f"Цвет: {result['color_class']}")
print(f"RGB: {result['rgb']}")
print(f"Свежесть: {result['freshness']['status']}")
print(f"Оценка: {result['freshness']['score']}")
```

### Непрерывный мониторинг

```python
analyzer = FishColorAnalyzer()
analyzer.start()  # Запуск фонового потока

# Получение последних данных
while True:
    data = analyzer.get_latest()
    if data:
        process(data)
    time.sleep(1)

analyzer.stop()
```

### Структура результата

```json
{
  "timestamp": 1706745600.123,
  "spectrum": {
    "violet": 0.234,
    "blue": 0.456,
    "green": 0.789,
    "yellow": 0.654,
    "orange": 0.432,
    "red": 0.321
  },
  "rgb": [180, 220, 150],
  "hsv": {
    "hue": 95.5,
    "saturation": 0.682,
    "value": 0.863
  },
  "lab": {
    "L": 82.45,
    "a": -15.32,
    "b": 28.76
  },
  "color_class": "Зелёная",
  "freshness": {
    "status": "Свежая",
    "status_en": "fresh",
    "score": 0.756,
    "chroma": 32.58,
    "spectral_ratio": 0.954,
    "l_star": 82.45
  },
  "temperature_c": 25
}
```

## Docker

```bash
docker build -t fish-color-analyzer .
docker run --privileged -v /dev/i2c-1:/dev/i2c-1 fish-color-analyzer
```

## API классов

### AS7262Sensor

Драйвер низкого уровня для работы с датчиком.

| Метод | Описание |
|-------|----------|
| `read_calibrated()` | Чтение калиброванных значений (μW/cm²) |
| `set_led(current_ma)` | Установка тока подсветки |
| `get_temperature()` | Температура датчика (°C) |

### ColorAnalyzer

Алгоритмы анализа цвета.

| Метод | Описание |
|-------|----------|
| `spectrum_to_xyz(spectrum)` | Спектр → CIE XYZ |
| `xyz_to_lab(xyz)` | XYZ → CIE L\*a\*b\* |
| `spectrum_to_rgb(spectrum)` | Спектр → sRGB |
| `calculate_hsv(rgb)` | RGB → HSV |
| `classify_fish_color(hsv)` | Классификация цвета |
| `assess_freshness(spectrum, lab)` | Оценка свежести |

### FishColorAnalyzer

Высокоуровневый класс для анализа.

| Метод | Описание |
|-------|----------|
| `measure_and_analyze()` | Полный цикл измерения и анализа |
| `start()` / `stop()` | Управление фоновым потоком |
| `get_latest()` | Последний результат |
| `get_history(count)` | История измерений |

## Научные источники

1. [Colorimetric data and ANN for fish freshness](https://www.sciencedirect.com/science/article/pii/S2772753X22001174) - ScienceDirect, 2022
2. [Emerging approaches for fish freshness evaluation](https://pmc.ncbi.nlm.nih.gov/articles/PMC9265959/) - PMC, 2022
3. [Machine vision for fish freshness based on color](https://www.scirp.org/html/2-2703017_107741.htm) - SCIRP
4. [How to measure color using spectrometers](https://journals.biologists.com/jeb/article/219/6/772/16696/How-to-measure-color-using-spectrometers-and) - Journal of Experimental Biology
5. [Underwater hyperspectral imaging for marine taxonomy](https://www.nature.com/articles/s41598-018-31261-4) - Scientific Reports
6. [Iridescence classification in marine organisms](https://pmc.ncbi.nlm.nih.gov/articles/PMC3302594/) - PMC

## Библиотеки для AS7262

- [SparkFun AS726X Arduino Library](https://github.com/sparkfun/SparkFun_AS726X_Arduino_Library)
- [Adafruit AS726x Library](https://github.com/adafruit/Adafruit_AS726x)
- [MicroPython AS726X Driver](https://github.com/jajberni/AS726X_LoPy)
- [Python Raspberry Pi Driver](https://github.com/UnfinishedStuff/AS7262_Pi)

## Лицензия

MIT License
