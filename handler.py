import os
import uuid
import traceback
from pathlib import Path
from typing import Any, Dict

import requests
import runpod

from processor import generate_shorts, UPLOADS_DIR


# ===============================
#  UTILITAIRE : téléchargement
# ===============================

def download_video_to_uploads(url: str) -> str:
    """
    Télécharge une vidéo depuis une URL HTTP(S) et la stocke dans uploads/.
    Retourne le chemin local complet.
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    # Extension
    ext = ".mp4"
    filename_raw = url.split("/")[-1]
    if "." in filename_raw:
        ext = "." + filename_raw.split(".")[-1].split("?")[0]

    filename = f"input_{uuid.uuid4().hex}{ext}"
    dest = UPLOADS_DIR / filename

    print(f"⬇️ Téléchargement depuis : {url}")

    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()

    with dest.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    print(f"✅ Vidéo téléchargée → {dest}")

    # Taille du fichier
    try:
        size = os.path.getsize(dest)
        print(f"📏 Taille : {size} octets")
    except:
        print("⚠️ Impossible de lire la taille du fichier")

    return str(dest)


# ===============================
#  HANDLER RUNPOD
# ===============================

def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    event = {
      "input": {
         "task": "ping"
      }
    }
    ou :
    {
      "input": {
        "task": "process",
        "video_url": "...",
        "num_clips": 8,
        "min_duration": 20,
        "max_duration": 45
      }
    }
    """

    try:
        inp = event.get("input") or {}
        task = inp.get("task", "ping")

        # -------------------------
        # 1️⃣ Ping test
        # -------------------------
        if task == "ping":
            return {
                "status": "ok",
                "message": "clipai-runpod-engine is alive 🔥"
            }

        # -------------------------
        # 2️⃣ Traitement vidéo
        # -------------------------
        if task == "process":
            url = inp.get("video_url")
            if not url:
                return {
                    "status": "error",
                    "error": "Missing 'video_url'"
                }

            num_clips = int(inp.get("num_clips", 8))
            min_duration = float(inp.get("min_duration", 20))
            max_duration = float(inp.get("max_duration", 45))

            # Télécharger la vidéo
            local_path = download_video_to_uploads(url)

            # Pipeline IA
            clips = generate_shorts(
                input_video_path=local_path,
                num_clips=num_clips,
                min_duration=min_duration,
                max_duration=max_duration,
            )

            return {
                "status": "done",
                "clips": clips
            }

        # -------------------------
        # 3️⃣ Task inconnue
        # -------------------------
        return {
            "status": "error",
            "error": f"Unknown task '{task}'"
        }

    except Exception as e:
        print("🔥 ERREUR HANDLER :", e)
        print(traceback.format_exc())

        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# Lancement RunPod
runpod.serverless.start({"handler": handler})
