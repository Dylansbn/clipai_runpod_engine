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

# Dépendances Python
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copie TOUT le dossier de ton projet (et une seule fois)
COPY . /app

# Préchargement du modèle Whisper
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('medium')"

# Commande de démarrage RunPod
CMD ["python3", "-u", "-m", "clipai_runpod_engine.handler"]
