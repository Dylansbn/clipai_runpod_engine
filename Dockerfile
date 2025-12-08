FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# --- dépendances système ---
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- requirements ---
COPY requirements.txt .
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt

# --- code ---
COPY . .

# --- variables par défaut (seront écrasées par RunPod) ---
ENV PYTHONUNBUFFERED=1

# --- entrypoint RunPod Serverless ---
CMD ["python3", "handler.py"]
