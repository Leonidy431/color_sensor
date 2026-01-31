# SBP AI Module for BlueOS
# Sub-Bottom Profiler Analysis with Hailo-8L
# Archaeological Object Detection

FROM python:3.11-slim-bookworm

LABEL maintainer="SBP AI Team"
LABEL version="1.0.0"
LABEL description="Sub-Bottom Profiler AI analysis for archaeological detection"

# BlueOS extension labels
LABEL permissions='{\
  "ExposedPorts": {"8080/tcp": {}},\
  "HostConfig": {\
    "Privileged": false,\
    "NetworkMode": "host",\
    "Devices": [\
      {"PathOnHost": "/dev/hailo0", "PathInContainer": "/dev/hailo0", "CgroupPermissions": "rwm"}\
    ],\
    "Binds": [\
      "/lib/firmware:/lib/firmware:ro",\
      "/data/sbp:/data/sbp"\
    ],\
    "PortBindings": {"8080/tcp": [{"HostPort": "8080"}]}\
  }\
}'

LABEL authors='[{"name": "SBP AI Team", "email": "contact@example.com"}]'
LABEL docs="https://github.com/example/sbp-ai-module"
LABEL company='{"name": "SBP AI", "about": "AI-powered sub-bottom profiler analysis"}'
LABEL website="https://example.com"
LABEL readme="https://raw.githubusercontent.com/example/sbp-ai-module/main/README.md"
LABEL requirements="core >= 1.1"

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    libglib2.0-0 \
    libgl1-mesa-glx \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование requirements и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY src/ ./src/
COPY config/ ./config/
COPY models/ ./models/

# Создание директорий для данных
RUN mkdir -p /app/data /app/logs /data/sbp

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV HAILO_DEVICE=/dev/hailo0
ENV LOG_LEVEL=INFO

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

# Expose порты
EXPOSE 8080

# Точка входа
ENTRYPOINT ["python", "-m", "src.main"]
