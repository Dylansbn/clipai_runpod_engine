FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# -----------------------------
# System dependencies
# -----------------------------
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    wget \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Install python dependencies
# -----------------------------
WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# -----------------------------
# Copy engine
# -----------------------------
COPY . .

# -----------------------------
# Start command (worker GPU)
# -----------------------------
CMD ["bash", "-c", "python3 -m clipai_runpod_engine.engine.worker"]
