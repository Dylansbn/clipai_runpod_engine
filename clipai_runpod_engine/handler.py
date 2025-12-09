# clipai_runpod_engine/handler.py
print("🔥 Handler imported successfully")

import uuid
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .job_queue.file_queue import push_job


# =========================
#  APP FASTAPI PRINCIPALE
# =========================

app = FastAPI(title="ClipAI RunPod Engine")

# CORS — tu ajusteras plus tard avec le domaine de ton front
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # ex: ["https://tonsite.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
#  MODELES D'ENTRÉE
# =========================

class ProcessRequest(BaseModel):
    video_url: str
    num_clips: int = 3


# =========================
#  ROUTES
# =========================

@app.get("/ping")
async def ping():
    """
    Simple endpoint de santé pour tester le pod.
    """
    return {"status": "ok"}


@app.post("/process")
async def process_video(req: ProcessRequest):
    """
    Reçoit une vidéo + nb de clips,
    crée un job dans la file,
    et renvoie immédiatement un job_id.
    """
    print("📩 Requête /process reçue :", req)

    if not req.video_url:
        return {
            "status": "error",
            "message": "Missing video_url",
        }

    # ID unique du job
    job_id = str(uuid.uuid4())

    # Push dans la file de jobs
    push_job({
        "job_id": job_id,
        "video_url": req.video_url,
        "num_clips": int(req.num_clips),
    })

    print(f"📌 Job créé : {job_id}")

    return {
        "status": "queued",
        "job_id": job_id,
    }

