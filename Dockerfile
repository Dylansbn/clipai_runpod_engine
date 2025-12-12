FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive

# Dépendances système
RUN apt-get update && apt-get install -y \
    tzdata \
    ffmpeg \
    git \
    curl \
    wget \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Dépendances Python
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Install PyTorch compatible CUDA 12.4
RUN pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124

# Code
COPY clipai_runpod_engine /app/clipai_runpod_engine
COPY . .

# Pré-chargement Whisper
RUN python3 - <<EOF
from faster_whisper import WhisperModel
WhisperModel("medium")
EOF

# Démarrage RunPod serverless
CMD ["python3", "-u", "-m", "clipai_runpod_engine.handler"]
