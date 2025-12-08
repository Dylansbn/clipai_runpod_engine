FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# -----------------------------
# Install system dependencies
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
# Working directory
# -----------------------------
WORKDIR /app

# -----------------------------
# Install python dependencies
# -----------------------------
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# -----------------------------
# Copy whole project
# -----------------------------
COPY . .

# -----------------------------
# Run worker + API FastAPI
# -----------------------------
CMD bash -c "python3 -m clipai_runpod_engine.engine.worker & uvicorn server:app --host 0.0.0.0 --port 8000"
