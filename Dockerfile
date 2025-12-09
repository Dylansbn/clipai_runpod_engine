FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime

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

# ---- Dépendances Python ----
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ---- Code de l'application ----
COPY clipai_runpod_engine /app/clipai_runpod_engine

# (Optionnel) Pré-chargement du modèle Whisper pour éviter le téléchargement lors du premier job
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('medium')"

# Si tu as d'autres fichiers à copier (README, etc.)
COPY . .

# ---- Commande de démarrage ----
# On lance directement le handler qui contient runpod.serverless.start(...)
CMD ["python3", "-u", "-m", "clipai_runpod_engine.handler"]
