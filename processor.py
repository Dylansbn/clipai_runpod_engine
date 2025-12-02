import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any

import pysubs2
from openai import OpenAI


# ==============================
#  CONFIG & DOSSIERS
# ==============================

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
SHORTS_DIR = BASE_DIR / "shorts"
SUBS_DIR = BASE_DIR / "subs"

for d in (UPLOADS_DIR, SHORTS_DIR, SUBS_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ==============================
#  CLIENT OPENAI
# ==============================

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ==============================
# 1. TRANSCRIPTION WHISPER API
# ==============================

def transcribe_with_whisper(video_path: str) -> Dict[str, Any]:
    """
    Utilise Whisper API officielle pour transcrire la vidéo.
    Compatible RunPod.
    """
    print("🎙️ Envoi vidéo → Whisper API ...")

    with open(video_path, "rb") as f:
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json"
        )

    segments = [
        {
            "start": float(s["start"]),
            "end": float(s["end"]),
            "text": s["text"].strip()
        }
        for s in res.segments
    ]

    return {
        "text": res.text.strip(),
        "segments": segments
    }


# ==============================
# 2. IA VIRALE (GPT-4.1-mini)
# ==============================

def select_viral_segments(
    segments: List[Dict[str, Any]],
    num_clips: int = 8,
    min_duration: float = 20.0,
    max_duration: float = 45.0,
    language: str = "fr"
):
    if not segments:
        return []

    transcript_for_ai = [
        f"[{s['start']:.2f} → {s['end']:.2f}] {s['text']}"
        for s in segments
    ]
    joined = "\n".join(transcript_for_ai)[:15000]

    system_prompt = (
        "Tu es un expert TikTok/YouTube Shorts. "
        "Sélectionne uniquement les moments les plus viraux. "
        f"Durée par clip : {min_duration}-{max_duration} secondes. "
        "Réponds STRICTEMENT en JSON."
    )

    user_prompt = f"""
Transcription :

{joined}

Retourne STRICTEMENT ce JSON :

{{
  "clips": [
    {{"start": 12.0, "end": 34.0, "title": "Titre viral", "reason": "Pourquoi"}}
  ]
}}
"""

    print("🤖 Appel IA virale…")
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    # ✅ FIX OpenAI SDK : accès via .content
    raw = completion.choices[0].message.content
    print("🔎 RAW JSON IA :", raw[:300])

    try:
        data = json.loads(raw)
        clips = data.get("clips", [])
    except Exception as e:
        print("⚠️ JSON invalide :", e)
        clips = []

    final = []
    for c in clips:
        try:
            start = float(c["start"])
            end = float(c["end"])
            if end > start:
                final.append(c)
        except:
            pass

    print(f"✅ Clips viraux sélectionnés : {len(final)}")
    return final


# ==============================
# 3. SOUS-TITRES KARAOKÉ (Style KLAP)
# ==============================

def build_karaoke_text(text: str, start_sec: float, end_sec: float) -> str:
    words = text.strip().split()
    if not words:
        return ""

    duration_ms = max(int((end_sec - start_sec) * 1000), 1)
    per_word = max(duration_ms // len(words), 1)

    return " ".join([f"{{\\k{per_word}}}{w}" for w in words])


def generate_ass_subs_for_clip(
    clip_start: float,
    clip_end: float,
    segments: List[Dict[str, Any]],
    subs_path: Path,
):
    subs = pysubs2.SSAFile()

    style = pysubs2.SSAStyle()
    style.name = "Klap"
    style.fontname = "Poppins"
    style.fontsize = 60
    style.bold = True
    style.borderstyle = 1
    style.outline = 4
    style.primarycolor = pysubs2.Color(255, 255, 0)
    style.outlinecolor = pysubs2.Color(0, 0, 0)
    style.alignment = 2
    subs.styles[style.name] = style

    for seg in segments:
        if seg["end"] <= clip_start or seg["start"] >= clip_end:
            continue

        local_start = max(seg["start"], clip_start) - clip_start
        local_end = min(seg["end"], clip_end) - clip_start

        kar = build_karaoke_text(seg["text"], seg["start"], seg["end"])

        ev = pysubs2.SSAEvent()
        ev.start = int(local_start * 1000)
        ev.end = int(local_end * 1000)
        ev.style = "Klap"
        ev.text = kar
        subs.events.append(ev)

    subs.save(str(subs_path))


# ==============================
# 4. FFMPEG CUT + 9:16 + SUBS
# ==============================

def ffmpeg_extract_and_style(input_video: Path, output_video: Path, subs: Path, start: float, end: float):
    duration = max(end - start, 0.5)

    vf = f"scale=-2:1920,crop=1080:1920,subtitles='{subs}'"

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start}",
        "-i", str(input_video),
        "-t", f"{duration}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k",
        str(output_video)
    ]

    print("🎬 FFmpeg :", " ".join(cmd))
    subprocess.run(cmd, check=True)


# ==============================
# 5. PIPELINE GLOBAL
# ==============================

def generate_shorts(input_video_path: str, num_clips: int = 8, min_duration: float = 20, max_duration: float = 45):

    video = Path(input_video_path)
    if not video.exists():
        raise FileNotFoundError(video)

    print("🚀 Lancement pipeline…")

    # 1️⃣ Whisper transcription
    transcription = transcribe_with_whisper(str(video))
    segments = transcription["segments"]

    # 2️⃣ IA virale
    viral = select_viral_segments(segments, num_clips, min_duration, max_duration)

    outputs = []

    # 3️⃣ Création des shorts
    for i, clip in enumerate(viral, start=1):
        out_video = SHORTS_DIR / f"short_{i:02d}.mp4"
        out_ass = SUBS_DIR / f"short_{i:02d}.ass"

        print(f"▶️ Clip {i} | {clip['start']} → {clip['end']}")

        generate_ass_subs_for_clip(clip["start"], clip["end"], segments, out_ass)

        ffmpeg_extract_and_style(video, out_video, out_ass, clip["start"], clip["end"])

        outputs.append({
            "index": i,
            "title": clip.get("title", ""),
            "reason": clip.get("reason", ""),
            "start": clip["start"],
            "end": clip["end"],
            "video_path": str(out_video),
            "subs_path": str(out_ass),
        })

    print("🎉 Shorts générés :", len(outputs))
    return outputs
