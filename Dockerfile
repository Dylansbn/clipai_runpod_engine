# =========================================================
#  KLAP PRO ENGINE - GPU DOCKERFILE (RUNPOD POD)
# =========================================================

FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------
# 1️⃣ Install system dependencies
# ---------------------------------------------------------
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    ffmpeg \
    libsm6 \
    libxext6 \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------------------------------------------------------
# 2️⃣ Python dependencies
# ---------------------------------------------------------
COPY requirements.txt .
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt

# Install whisper GPU dependency
RUN pip3 install --no-cache-dir faster-whisper

# ---------------------------------------------------------
# 3️⃣ Copy engine code
# ---------------------------------------------------------
COPY . .

# ---------------------------------------------------------
# 4️⃣ Start worker (Pod GPU mode)
# ---------------------------------------------------------
CMD ["python3", "-m", "clipai_runpod_engine.engine.worker"]
