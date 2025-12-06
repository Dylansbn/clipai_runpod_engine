import os
import traceback
from typing import Any, Dict

import runpod

from processor import (
    download_video,
    generate_shorts,
)


# ============================================
#  HANDLER PRINCIPAL — VERSION PRO
# ============================================

def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compatible frontend + CURL :

    event = {
        "input": {
            "url": "...",
            "video_url": "...",
            "task": "process" | "ping" | "debug_download",
            "num_clips": 3,
            "min_duration": 6,
            "max_duration": 25
        }
    }
    """

    print("📩 EVENT REÇU :", event)

    try:
        inp = event.get("input", {})
        if not isinstance(inp, dict):
            return {"status": "error", "error": "Invalid input payload"}

        # -------------------------
        # Extraction des champs
        # -------------------------
        url = inp.get("video_url") or inp.get("url")

        task = inp.get("task")
        if not task:
            # si une URL est présente → tâche = process
            task = "process" if url else "ping"

        num_clips = int(inp.get("num_clips", 3))
        min_duration = float(inp.get("min_duration", 6))
        max_duration = float(inp.get("max_duration", 25))

        print(f"🔧 Task: {task}")
        print(f"🎞 URL: {url}")
        print(f"🎬 Clips: {num_clips} ({min_duration}s → {max_duration}s)")

        # ============================================
        # 1️⃣ TASK : PING — Vérifier si le moteur tourne
        # ============================================
        if task == "ping":
            return {
                "status": "ok",
                "message": "ClipAI Engine Alive 🔥",
                "version": "serverless-pro"
            }

        # ============================================
        # 2️⃣ TASK : Téléchargement simple
        # ============================================
        if task == "debug_download":
            if not url:
                return {"status": "error", "error": "Missing URL"}

            print("⬇️ Téléchargement simple…")
            local_path = download_video(url)

            size = os.path.getsize(local_path)

            print(f"📦 Fichier téléchargé : {size/1_000_000:.2f} MB")

            return {
                "status": "downloaded",
                "local_path": local_path,
                "size_bytes": size
            }

        # ============================================
        # 3️⃣ TASK : Pipeline complet (shorts)
        # ============================================
        if task == "process":
            if not url:
                return {"status": "error", "error": "Missing URL"}

            print("⬇️ Téléchargement…", url)
            local_path = download_video(url)

            print("🎥 Génération des shorts…")
            clips = generate_shorts(
                input_video_path=local_path,
                num_clips=num_clips,
                min_duration=min_duration,
                max_duration=max_duration,
            )

            print(f"✅ {len(clips)} clips générés")

            return {
                "status": "done",
                "clips": clips
            }

        # ============================================
        # 4️⃣ Task inconnue
        # ============================================
        return {
            "status": "error",
            "error": f"Unknown task: {task}"
        }

    except Exception as e:
        print("🔥 ERREUR handler :", e)
        print(traceback.format_exc())

        # Toujours retourner un format 100% exploitable par ton frontend
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# ============================================
#  RUNPOD — Entrée du worker
# ============================================
runpod.serverless.start({"handler": handler})
