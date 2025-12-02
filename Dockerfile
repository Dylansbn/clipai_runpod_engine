FROM python:3.10-slim

# Installer ffmpeg + dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Définir dossier de travail
WORKDIR /app

# Copier les requirements
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier tout ton code dans le conteneur
COPY . .

# Commande de démarrage pour RunPod serverless
CMD ["python", "handler.py"]
