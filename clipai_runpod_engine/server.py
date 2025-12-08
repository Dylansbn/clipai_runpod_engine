from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import uuid

from job_queue.file_queue import push_job

app = FastAPI(title="ClipAI Pod API")

class ProcessRequest(BaseModel):
    video_url: str
    num_clips: int = 3

@app.post("/process")
def process_video(req: ProcessRequest):
    job_id = str(uuid.uuid4())

    push_job({
        "job_id": job_id,
        "video_url": req.video_url,
        "num_clips": req.num_clips
    })

    return {
        "status": "queued",
        "job_id": job_id
    }

@app.get("/")
def root():
    return {"status": "ok", "message": "ClipAI Pod API is running"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
