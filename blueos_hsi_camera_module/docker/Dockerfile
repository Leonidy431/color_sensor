# HSI Camera Module for BlueOS
# Underwater Hyperspectral Imaging - material classification (SAM)
# Camera: Ecotone AS UHI (см. README.md, раздел 1)

FROM python:3.11-slim-bookworm

LABEL maintainer="HSI Camera Team"
LABEL version="1.0.0"
LABEL description="Underwater hyperspectral imaging analysis for BlueOS"

# BlueOS extension labels.
# Куб данных обрабатывается на GPU (NVIDIA Orin), а не на Hailo-8L NPU,
# используемом в Fish AI / SBP AI модулях этого проекта - см. README.md
# раздел 2.1 (спектральное сжатие куба - тензорная линейная алгебра,
# не свёрточная сеть детекции).
LABEL permissions='{\
  "ExposedPorts": {"8081/tcp": {}},\
  "HostConfig": {\
    "Privileged": false,\
    "NetworkMode": "host",\
    "Binds": [\
      "/data/hsi:/data/hsi"\
    ],\
    "PortBindings": {"8081/tcp": [{"HostPort": "8081"}]}\
  }\
}'

LABEL authors='[{"name": "HSI Camera Team", "email": "contact@example.com"}]'
LABEL docs="https://github.com/example/hsi-camera-module"
LABEL company='{"name": "HSI Camera", "about": "Underwater hyperspectral imaging"}'
LABEL website="https://example.com"
LABEL readme="https://raw.githubusercontent.com/example/hsi-camera-module/main/README.md"
LABEL requirements="core >= 1.1"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /app/data /app/logs /data/hsi

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8081/api/v1/health || exit 1

EXPOSE 8081

ENTRYPOINT ["uvicorn", "api.routes:create_app", "--factory", "--host", "0.0.0.0", "--port", "8081"]
