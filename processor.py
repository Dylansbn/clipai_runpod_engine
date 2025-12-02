import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any

import pysubs2
import ffmpeg   # ffmpeg-python
from openai import OpenAI

# ==========================================
#  CONFIG DOSSIERS
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
SHORTS_DIR = BASE_DIR / "shorts"
SUBS_DIR = BASE_DIR / "subs"

for d in (UPLOADS_DIR, SHORTS_DIR, SUBS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ==========================================
#  CLIENT OPENAI
# ==========================================

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    project=os.getenv("OPENAI_PROJECT_ID")
)

# ==========================================
# 1️⃣ TRANSCRIPTION WHISPER API (CORRIGÉ)
# ==========================================

def transcribe_with_whisper(video_path: str) -> Dict[str, Any]:
    """
    Convertit MP4 → WAV puis appelle Whisper API.
    Corrige l'erreur: "something went wrong reading your request".
    """

    wav_path = str(Path(video_path).with_suffix(".wav"))

    print("🎧 Conversion MP4 → WAV (16kHz mono)...")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-ac", "1",       # mono
        "-ar", "16000",   # 16 kHz
        wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print(f"🔊 WAV généré : {wav_path}")

    # ---- Appel Whisper API ----
    with open(wav_path, "rb") as f:
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json"
        )

    # ---- Extraction segments ----
    segments = [
        {
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text.strip()
        }
        for s in res.segments
    ]

    print(f"📝 Transcription OK, segments : {len(segments)}")

    return {
        "text": res.text.strip(),
        "segments": segments
    }

# ==========================================
# 2️⃣ IA VIRALE (GPT-4.1-mini)
# ==========================================

def select_viral_segments(
    segments: List[Dict[str, Any]],
    num_clips: int = 8,
    min_duration: float = 15.0,
    max_duration: float = 45.0,
    language: str = "fr"
) -> List[Dict[str, Any]]:

    if not segments:
        print("⚠️ Aucun segment pour analyse IA.")
        return []

    transcript_for_ai = [
        f"[{s['start']:.2f} → {s['end']:.2f}] {s['text']}"
        for s in segments
    ]
    joined = "\n".join(transcript_for_ai)[:15000]

    system_prompt = (
        "Tu es expert TikTok/YouTube Shorts. "
        "Choisis les extraits les plus viraux, impactants, émotionnels. "
        "Chaque extrait doit faire un bon hook dès la première seconde. "
        "Réponds STRICTEMENT en JSON."
    )

    user_prompt = f"""
Transcription :

{joined}

Réponds en JSON :
{{
  "clips": [
    {{"start": 12, "end": 35, "title": "Hook fort", "reason": "punchline"}} 
  ]
}}
"""

    print("🤖 Appel GPT sélection virale...")

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    raw_text = response.choices[0].message["content"]
    print("🔎 Réponse IA :", raw_text[:400])

    try:
        clips = json.loads(raw_text)["clips"]
    except:
        print("⚠️ JSON IA invalide → aucun clip.")
        return []

    final = []
    for c in clips:
        try:
            if float(c["end"]) > float(c["start"]):
                final.append(c)
        except:
            pass

    print(f"🔥 Clips viraux retenus : {len(final)}")
    return final

# ==========================================
# 3️⃣ SOUS-TITRES KARAOKÉ STYLE KLAP
# ==========================================

def build_karaoke_text(text: str, start: float, end: float) -> str:
    words = text.strip().split()
    if not words:
        return ""

    duration = max((end - start) * 1000, 1)
    per_word = max(int(duration / len(words)), 1)

    return " ".join([f"{{\\k{per_word}}}{w}" for w in words])


def generate_ass_subs_for_clip(start, end, segments, output_path):
    subs = pysubs2.SSAFile()

    style = pysubs2.SSAStyle()
    style.name = "Klap"
    style.fontname = "Poppins"
    style.fontsize = 62
    style.bold = True
    style.outline = 4
    style.primarycolor = pysubs2.Color(255, 255, 0)
    style.outlinecolor = pysubs2.Color(0, 0, 0)
    style.alignment = 2
    subs.styles[style.name] = style

    for seg in segments:
        if seg["end"] <= start or seg["start"] >= end:
            continue

        local_s = max(seg["start"], start) - start
        local_e = min(seg["end"], end) - start

        karaoke = build_karaoke_text(seg["text"], seg["start"], seg["end"])
        if not karaoke:
            continue

        ev = pysubs2.SSAEvent()
        ev.start = int(local_s * 1000)
        ev.end = int(local_e * 1000)
        ev.style = "Klap"
        ev.text = karaoke
        subs.events.append(ev)

    subs.save(str(output_path))
    print("🟡 Sous-titres générés :", output_path)

# ==========================================
# 4️⃣ FFMPEG 9:16 + SOUS-TITRES
# ==========================================

def ffmpeg_extract_and_style(input_video, output_video, subs, start, end):
    duration = max(end - start, 0.5)

    vf = f"scale=-2:1920,crop=1080:1920,subtitles='{subs}'"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(input_video),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k",
        str(output_video)
    ]

    print("🎬 FFmpeg :", " ".join(cmd))
    subprocess.run(cmd, check=True)

# ==========================================
# 5️⃣ PIPELINE COMPLET
# ==========================================

def generate_shorts(input_video_path, num_clips=4, min_duration=15, max_duration=45):

    video = Path(input_video_path)
    if not video.exists():
        raise FileNotFoundError(video)

    print("🚀 Pipeline lancé sur :", video)

    # --- Transcription ---
    transcription = transcribe_with_whisper(str(video))
    segments = transcription["segments"]

    # --- IA virale ---
    viral = select_viral_segments(segments, num_clips, min_duration, max_duration)

    outputs = []

    for i, clip in enumerate(viral, 1):
        out_vid = SHORTS_DIR / f"short_{i:02d}.mp4"
        out_sub = SUBS_DIR / f"short_{i:02d}.ass"

        print(f"▶️ Clip {i} : {clip['start']} → {clip['end']}")

        generate_ass_subs_for_clip(clip["start"], clip["end"], segments, out_sub)
        ffmpeg_extract_and_style(video, out_vid, out_sub, clip["start"], clip["end"])

        outputs.append({
            "index": i,
            "title": clip.get("title", ""),
            "reason": clip.get("reason", ""),
            "video_path": str(out_vid),
            "subs_path": str(out_sub)
        })

    print("🎉 Shorts générés :", len(outputs))
    return outputs
