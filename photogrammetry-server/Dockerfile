# Phase D 초안: Ubuntu + COLMAP + Photogrammetry API
# 빌드: docker build -t origin-real-photogrammetry photogrammetry-server
# 실행(CPU 예시): docker run --rm -p 8002:8002 -v photogrammetry-data:/app/data origin-real-photogrammetry
# GPU 밀집: --gpus all 및 NVIDIA 컨테이너 툴킷 필요(호스트·드라이버에 맞게 조정)

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    colmap \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY main.py .
COPY scripts ./scripts

ENV PHOTOGRAMMETRY_DATA_DIR=/app/data
RUN mkdir -p /app/data/jobs

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
