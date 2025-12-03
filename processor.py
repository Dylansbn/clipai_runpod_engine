import os
import json
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urlparse

import pysubs2
from yt_dlp import YoutubeDL
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

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ==============================
# 0. DOWNLOAD ENGINE PRO (YouTube / TikTok / Vimeo / liens signés)
# ==============================

def download_video(url: str) -> str:
    """
    Télécharge une vidéo depuis n'importe quelle plateforme (YouTube, TikTok, Vimeo,
    liens signés, etc.) avec :
      - User-Agent de navigateur
      - headers adaptés TikTok
      - geo-bypass US
      - retries
      - vérification ffprobe

    Retourne le chemin local vers un vrai .mp4 lisible par Whisper.
    """
    print(f"⬇️ [DOWNLOAD] URL : {url}")

    output = UPLOADS_DIR / f"input_{os.urandom(4).hex()}.mp4"
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    # User-Agent de vrai Chrome
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )

    headers = {
        "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    }

    # TikTok : très sensible au Referer + UA
    if "tiktok.com" in host or "douyin.com" in host:
        headers["Referer"] = "https://www.tiktok.com/"

    ydl_opts = {
        "outtmpl": str(output),
        "format": "bv*+ba/best/b",          # meilleure vidéo + audio possible
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "geo_bypass": True,
        "geo_bypass_country": "US",        # contourner pas mal de blocages YouTube
        "nocheckcertificate": True,
        "retries": 3,
        "user_agent": ua,
        "http_headers": headers,
    }

    last_err = None

    # === Tentatives multiples yt-dlp ===
    for attempt in range(1, 4):
        try:
            print(f"📥 Tentative yt-dlp {attempt}/3...")
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            last_err = None
            break
        except Exception as e:
            last_err = e
            print(f"⚠️ Échec tentative {attempt} : {e}")
            time.sleep(2)

    if last_err is not None and not output.exists():
        raise Exception(f"yt-dlp a échoué après 3 tentatives : {last_err}")

    if not output.exists():
        raise Exception("Téléchargement échoué : fichier inexistant après yt-dlp.")

    size = output.stat().st_size
    print(f"📦 Taille fichier téléchargé : {size} bytes")

    # Si le fichier est trop petit, c'est souvent une page HTML ou une erreur
    if size < 80_000:  # ~80 Ko
        raise Exception("Fichier téléchargé trop petit (<80ko) → probablement pas une vraie vidéo.")

    # Vérification ffprobe (important avant Whisper)
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        str(output)
    ]
    probe = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if probe.returncode != 0:
        err = probe.stderr.decode("utf-8", errors="ignore")
        raise Exception(f"ffprobe : fichier illisible ou non supporté → {err}")

    print("✅ Vidéo téléchargée & validée (OK pour Whisper).")
    return str(output)


# ==============================
# 1. TRANSCRIPTION WHISPER API
# ==============================

def transcribe_with_whisper(video_path: str) -> Dict[str, Any]:
    print("🎙️ Envoi vidéo → Whisper API...")

    with open(video_path, "rb") as f:
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json"
        )

    segments = [
        {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
        for s in res.segments
    ]

    print(f"📌 Segments trouvés : {len(segments)}")

    return {
        "text": res.text.strip(),
        "segments": segments
    }


# ==============================
# 2. IA VIRAL GPT (sélection des clips)
# ==============================

def select_viral_segments(
    segments: List[Dict[str, Any]],
    num_clips: int,
    min_duration: float,
    max_duration: float
) -> List[Dict[str, Any]]:

    if not segments:
        return []

    transcript = "\n".join(
        f"[{s['start']:.2f} → {s['end']:.2f}] {s['text']}"
        for s in segments
    )[:15000]

    system_prompt = (
        "Tu es expert TikTok. Tu choisis les clips les plus viraux. "
        "Réponds STRICTEMENT en JSON valide."
    )

    user_prompt = f"""
Transcription :

{transcript}

Choisis {num_clips} clips de {min_duration}–{max_duration} secondes.

Format JSON strict :
{{
 "clips":[
   {{
     "start": 10,
     "end": 28,
     "title": "Titre viral",
     "reason": "Why viral"
   }}
 ]
}}
"""

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    data = json.loads(completion.choices[0].message.content)
    clips = data.get("clips", [])

    final = []
    for c in clips:
        try:
            s = float(c["start"])
            e = float(c["end"])
            if e > s:
                final.append({
                    "start": s,
                    "end": e,
                    "title": c.get("title", "Clip"),
                    "reason": c.get("reason", "")
                })
        except:
            pass

    print(f"🔥 Clips sélectionnés : {len(final)}")
    return final


# ==============================
# 3. GÉNÉRATION SOUS-TITRES KARAOKÉ
# ==============================

def build_karaoke_text(text: str, start: float, end: float) -> str:
    words = text.split()
    if not words:
        return ""

    duration_ms = max((end - start) * 1000, 1)
    per = max(int(duration_ms / len(words)), 1)

    return " ".join([f"{{\\k{per}}}{w}" for w in words])


def generate_ass_subs_for_clip(
    clip_start: float,
    clip_end: float,
    segments: List[Dict[str, Any]],
    subs_path: Path,
):
    subs = pysubs2.SSAFile()

    # Style KLAP-like
    style = pysubs2.SSAStyle()
    style.name = "Klap"
    style.fontname = "Poppins"
    style.fontsize = 60
    style.bold = True
    style.outline = 4
    style.primarycolor = pysubs2.Color(255, 255, 0)
    style.outlinecolor = pysubs2.Color(0, 0, 0)
    style.alignment = 2  # centré
    subs.styles[style.name] = style

    for seg in segments:
        if seg["end"] <= clip_start or seg["start"] >= clip_end:
            continue

        start = max(seg["start"], clip_start) - clip_start
        end = min(seg["end"], clip_end) - clip_start

        ktext = build_karaoke_text(seg["text"], seg["start"], seg["end"])
        if not ktext:
            continue

        ev = pysubs2.SSAEvent()
        ev.start = int(start * 1000)
        ev.end = int(end * 1000)
        ev.style = "Klap"
        ev.text = ktext

        subs.events.append(ev)

    subs.save(str(subs_path))


# ==============================
# 4. FFMPEG (9:16 + sous-titres)
# ==============================

def ffmpeg_extract_and_style(
    src: str,
    out: str,
    subs: str,
    start: float,
    end: float
):
    duration = max(end - start, 0.5)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", src,
        "-t", str(duration),
        "-vf", f"scale=-2:1920,crop=1080:1920,subtitles='{subs}'",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "160k",
        out
    ]

    print("🎬 FFmpeg →", " ".join(cmd))
    subprocess.run(cmd, check=True)


# ==============================
# 5. PIPELINE GLOBAL
# ==============================

def generate_shorts(
    input_video_path: str,
    num_clips: int = 8,
    min_duration: float = 20,
    max_duration: float = 45
):
    print("🚀 Pipeline IA lancé...")

    # 1. Transcription
    tr = transcribe_with_whisper(input_video_path)
    segments = tr["segments"]

    # 2. Sélection IA
    viral_clips = select_viral_segments(
        segments, num_clips, min_duration, max_duration
    )

    results = []

    # 3. Génération des shorts
    for i, c in enumerate(viral_clips, start=1):
        out_vid = SHORTS_DIR / f"short_{i:02d}.mp4"
        out_ass = SUBS_DIR / f"short_{i:02d}.ass"

        print(f"▶️ Clip {i} : {c['start']} → {c['end']}")

        generate_ass_subs_for_clip(
            c["start"], c["end"], segments, out_ass
        )

        ffmpeg_extract_and_style(
            input_video_path, str(out_vid), str(out_ass),
            c["start"], c["end"]
        )

        results.append({
            "index": i,
            "title": c["title"],
            "reason": c["reason"],
            "start": c["start"],
            "end": c["end"],
            "video_path": str(out_vid),
            "subs_path": str(out_ass),
        })

    print(f"🎉 Shorts générés : {len(results)}")
    return results
