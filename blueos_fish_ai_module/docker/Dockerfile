# Fish AI Module for BlueOS
# Raspberry Pi 5 + Hailo-8L + AS7262

FROM python:3.11-slim-bookworm

LABEL maintainer="Fish AI Team"
LABEL version="1.0.0"
LABEL description="Fish detection and color analysis module for BlueOS"

# BlueOS extension labels
LABEL permissions='{\
  "ExposedPorts": {"8080/tcp": {}},\
  "HostConfig": {\
    "Privileged": false,\
    "Devices": [\
      {"PathOnHost": "/dev/i2c-1", "PathInContainer": "/dev/i2c-1", "CgroupPermissions": "rwm"},\
      {"PathOnHost": "/dev/video0", "PathInContainer": "/dev/video0", "CgroupPermissions": "rwm"},\
      {"PathOnHost": "/dev/hailo0", "PathInContainer": "/dev/hailo0", "CgroupPermissions": "rwm"}\
    ],\
    "Binds": [\
      "/lib/firmware:/lib/firmware:ro",\
      "/sys/class/hailo_chardev:/sys/class/hailo_chardev:ro"\
    ],\
    "PortBindings": {"8080/tcp": [{"HostPort": "8080"}]},\
    "NetworkMode": "host"\
  }\
}'

LABEL authors='[{"name": "Fish AI Team", "email": "contact@example.com"}]'
LABEL docs="https://github.com/example/fish-ai-module"
LABEL company='{"name": "Fish AI", "about": "AI-powered marine life analysis"}'
LABEL website="https://example.com"
LABEL readme="https://raw.githubusercontent.com/example/fish-ai-module/main/README.md"
LABEL links='{"support": "https://github.com/example/fish-ai-module/issues"}'
LABEL requirements="core >= 1.1"

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    i2c-tools \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    libopencv-dev \
    python3-opencv \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

# Установка Hailo Runtime (wheel для arm64)
# Примечание: в реальной среде скопировать hailort wheel из хост-системы
COPY wheels/hailort*.whl /tmp/
RUN pip install /tmp/hailort*.whl || echo "Hailo wheel not found, will use mock"

# Рабочая директория
WORKDIR /app

# Копирование requirements и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY src/ ./src/
COPY config/ ./config/
COPY models/ ./models/
COPY web/ ./web/

# Создание директорий для данных
RUN mkdir -p /app/data /app/logs

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV HAILO_DEVICE=/dev/hailo0
ENV I2C_BUS=1
ENV LOG_LEVEL=INFO

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

# Expose порты
EXPOSE 8080

# Точка входа
ENTRYPOINT ["python", "-m", "src.main"]
