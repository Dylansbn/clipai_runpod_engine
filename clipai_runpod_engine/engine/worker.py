# clipai_runpod_engine/engine/worker.py
# ============================================================
# WORKER GPU — VERSION KLAP PRO (SERVERLESS)
# ============================================================

import traceback
from typing import Dict, Any

from .video_analyzer import analyze_video, download_video
from .whisper_gpu import transcribe_gpu
from .clip_selector import select_clips
from .render import render_clips
from .storage import upload_results


def process_job(job_id: str, video_url: str, num_clips: int = 3) -> Dict[str, Any]:
    """
    Pipeline complet pour un job unique.
    Appelé par le handler RunPod Serverless.
    """

    print("\n==============================================")
    print(f"🚀 DÉMARRAGE JOB : {job_id}")
    print("==============================================")
    print(f"📹 URL vidéo : {video_url}")
    print(f"🎯 Clips demandés : {num_clips}")

    try:
        # 1️⃣ Téléchargement vidéo
        print("⬇️ Téléchargement de la vidéo...")
        local_path = download_video(video_url)

        # 2️⃣ Analyse vidéo
        print("📊 Analyse vidéo (peaks / énergie)...")
        analysis = analyze_video(local_path)

        # 3️⃣ Transcription Whisper GPU
        print("🎧 Transcription (Whisper GPU)...")
        segments = transcribe_gpu(local_path)

        # 4️⃣ Sélection des meilleurs moments
        print("🧠 Sélection des meilleurs moments...")
        clips = select_clips(segments, analysis, num_clips)

        # 5️⃣ Rendu des clips + sous-titres
        print("🎬 Rendu des clips (NVENC + sous-titres KLAP)...")
        outputs = render_clips(local_path, clips, segments)

        # 6️⃣ Upload final vers R2
        print("☁️ Upload vers Cloudflare R2...")
        urls = upload_results(job_id, outputs)

        print(f"✅ JOB TERMINÉ → {job_id}")
        print(f"🌐 URLs générées : {urls}\n")

        # Réponse structurée pour le frontend
        return {
            "video_url": video_url,
            "num_clips": num_clips,
            "clips": [
                {
                    "index": i,
                    "start": clip.get("start"),
                    "end": clip.get("end"),
                    "url": url,
                }
                for i, (clip, url) in enumerate(zip(clips, urls))
            ],
            "urls": urls,
        }

    except Exception as e:
        print(f"🔥 ERREUR dans le job {job_id} !")
        print(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e),
        }
