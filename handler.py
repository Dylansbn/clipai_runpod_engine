import os
import uuid
import traceback
from typing import Any, Dict

from job_queue.file_queue import push_job  # <-- IMPORTANT : nouveau chemin


# ============================================
#  HANDLER PRINCIPAL — MODE JOB (PRO)
# ============================================

def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compatible avec :
    - RunPod Runsync (cloud)
    - test local via test_handler.py

    event = {
        "input": {
            "task": "process" | "ping",
            "video_url": "...",
            "num_clips": 3
        }
    }
    """
    print("📩 EVENT REÇU :", event)

    try:
        inp = event.get("input", {})
        if not isinstance(inp, dict):
            return {"status": "error", "error": "Invalid input payload"}

        url = inp.get("video_url") or inp.get("url")
        task = inp.get("task") or ("process" if url else "ping")
        num_clips = int(inp.get("num_clips", 3))

        # 1️⃣ PING
        if task == "ping":
            return {
                "status": "ok",
                "message": "ClipAI Engine Alive 🔥",
                "version": "pro-job-system"
            }

        # 2️⃣ PROCESS : on NE TRAITE PLUS ici, on crée un JOB
        if task == "process":
            if not url:
                return {"status": "error", "error": "Missing video_url"}

            job_id = str(uuid.uuid4())

            job_data = {
                "job_id": job_id,
                "video_url": url,
                "num_clips": num_clips,
            }

            # On pousse le job dans la file
            push_job(job_data)
            print(f"📌 Job créé : {job_id}")

            return {
                "status": "queued",
                "job_id": job_id,
            }

        return {"status": "error", "error": f"Unknown task: {task}"}

    except Exception as e:
        print("🔥 ERREUR handler :", e)
        print(traceback.format_exc())

        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# ============================================
#  ENTRYPOINT RUNPOD (uniquement si exécuté en main)
# ============================================
if __name__ == "__main__":
    import runpod
    runpod.serverless.start({"handler": handler})
