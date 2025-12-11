# 🔥 Base officielle RunPod Serverless (CUDA + cuDNN compatibles)
FROM runpod/python:3.10-ubuntu-22.04

ARG DEBIAN_FRONTEND=noninteractive

# ---------------------
# Dépendances système
# ---------------------
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    wget \
    curl \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------------------
# Dépendances Python
# ---------------------
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------
# Code de ton moteur
# ---------------------
COPY clipai_runpod_engine /app/clipai_runpod_engine
COPY . .

# ---------------------
# Commande RunPod Serverless
# ---------------------
CMD ["python3", "-u", "-m", "clipai_runpod_engine.handler"]
