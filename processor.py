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

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    project=os.getenv("OPENAI_PROJECT_ID"),
)


# ==============================
# 1. TRANSCRIPTION WHISPER API  – FIX TOTAL
# ==============================

def transcribe_with_whisper(video_path: str) -> Dict[str, Any]:
    """Transcription via Whisper API (pas de modèle local)."""
    print("🎙️ Envoi vidéo → Whisper API ...")

    with open(video_path, "rb") as f:
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json"
        )

    # FIX : res.segments = objets, pas des dicts
    segments = []
    for s in res.segments:
        segments.append({
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text.strip()
        })

    print(f"📌 Segments générés : {len(segments)}")

    return {
        "text": res.text.strip(),
        "segments": segments
    }


# ==============================
# 2. IA VIRALE (GPT) — FIX JSON + modèle chat complet
# ==============================

def select_viral_segments(
    segments: List[Dict[str, Any]],
    num_clips: int = 8,
    min_duration: float = 20.0,
    max_duration: float = 45.0,
) -> List[Dict[str, Any]]:

    if not segments:
        return []

    transcript = "\n".join(
        f"[{s['start']:.2f} → {s['end']:.2f}] {s['text']}"
        for s in segments
    )[:15000]

    system_prompt = (
        "Tu es un expert TikTok/Shorts. "
        "Tu choisis les moments les plus viraux avec un hook fort. "
        "Réponds STRICTEMENT en JSON : {\"clips\": [{\"start\": x, \"end\": y, \"title\": \"\", \"reason\": \"\"}]}"
    )

    user_prompt = f"""
Transcription :

{transcript}

Choisis {num_clips} clips de {min_duration}-{max_duration} secondes.
Réponds en JSON strict.
"""

    print("🤖 Appel GPT...")
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content
    print("🔎 JSON IA reçu :", raw[:300])

    try:
        data = json.loads(raw)
        clips = data.get("clips", [])
    except:
        clips = []

    # Validation
    final = []
    for c in clips:
        try:
            s = float(c["start"])
            e = float(c["end"])
            if e > s:
                final.append({
                    "start": s,
                    "end": e,
                    "title": c.get("title", "Clip viral"),
                    "reason": c.get("reason", "")
                })
        except:
            pass

    print(f"✅ Clips retenus : {len(final)}")
    return final


# ==============================
# 3. SOUS-TITRES KARAOKÉ (STYLE KLAP)
# ==============================

def build_karaoke_text(text: str, start_sec: float, end_sec: float) -> str:
    words = text.split()
    if not words:
        return ""

    duration = max((end_sec - start_sec) * 1000, 1)
    per = max(int(duration / len(words)), 1)

    return " ".join([f"{{\\k{per}}}{w}" for w in words])


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
    style.outline = 4
    style.primarycolor = pysubs2.Color(255, 255, 0)
    style.outlinecolor = pysubs2.Color(0, 0, 0)
    style.alignment = 2
    subs.styles[style.name] = style

    for seg in segments:
        if seg["end"] <= clip_start or seg["start"] >= clip_end:
            continue

        start = max(seg["start"], clip_start) - clip_start
        end = min(seg["end"], clip_end) - clip_start

        kar = build_karaoke_text(seg["text"], seg["start"], seg["end"])
        if not kar:
            continue

        ev = pysubs2.SSAEvent()
        ev.start = int(start * 1000)
        ev.end = int(end * 1000)
        ev.style = "Klap"
        ev.text = kar
        subs.events.append(ev)

    subs.save(str(subs_path))


# ==============================
# 4. FFMPEG : CUT + FORMAT 9:16 + SUBS
# ==============================

def ffmpeg_extract_and_style(input_video: Path, output_video: Path, subs: Path, start: float, end: float):
    """Découpe + crop 9:16 + sous-titres."""
    duration = max(end - start, 0.5)

    vf = f"scale=-2:1920,crop=1080:1920,subtitles='{subs}'"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(input_video),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "160k",
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

    # 1. Transcription Whisper API
    tr = transcribe_with_whisper(str(video))
    segments = tr["segments"]

    # 2. IA virale (GPT)
    viral = select_viral_segments(segments, num_clips, min_duration, max_duration)

    results = []

    # 3. Génération des shorts
    for i, c in enumerate(viral, start=1):
        out_vid = SHORTS_DIR / f"short_{i:02d}.mp4"
        out_ass = SUBS_DIR / f"short_{i:02d}.ass"

        print(f"▶️ Clip {i} | {c['start']} → {c['end']}")

        generate_ass_subs_for_clip(c["start"], c["end"], segments, out_ass)
        ffmpeg_extract_and_style(video, out_vid, out_ass, c["start"], c["end"])

        results.append({
            "index": i,
            "title": c["title"],
            "reason": c["reason"],
            "start": c["start"],
            "end": c["end"],
            "video_path": str(out_vid),
            "subs_path": str(out_ass),
        })

    print("🎉 Shorts générés :", len(results))
    return results
