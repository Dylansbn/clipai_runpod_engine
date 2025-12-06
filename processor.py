import os
import json
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urlparse

import pysubs2
import yt_dlp
import boto3
import requests
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
#  CLIENT R2 (S3 compatible)
# ==============================

def get_r2_client():
    access = os.getenv("R2_ACCESS_KEY_ID")
    secret = os.getenv("R2_SECRET_ACCESS_KEY")
    endpoint = os.getenv("R2_ENDPOINT_URL")

    if not (access and secret and endpoint):
        print("ℹ️ R2 non configuré → on travaille en local.")
        return None

    session = boto3.session.Session()
    return session.client(
        service_name="s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name="auto",
    )


def upload_to_r2(local_path: str, key_prefix: str = "") -> str:
    s3 = get_r2_client()
    bucket = os.getenv("R2_BUCKET_NAME")

    if not s3 or not bucket:
        return local_path

    local = Path(local_path)
    key_prefix = key_prefix.strip("/")
    key = f"{key_prefix}/{local.name}" if key_prefix else local.name

    print(f"☁️ Upload vers R2 : {key}")

    content_type = "video/mp4" if local.suffix.lower() == ".mp4" else "text/plain"

    s3.upload_file(
        Filename=str(local),
        Bucket=bucket,
        Key=key,
        ExtraArgs={"ContentType": content_type},
    )

    public_base = os.getenv("R2_PUBLIC_BASE_URL", "").rstrip("/")
    return f"{public_base}/{key}"


# ======================================================
# 0. DOWNLOAD VIDEO (R2 / direct mp4 / TikTok / YouTube)
# ======================================================

def download_video(url: str) -> str:
    print(f"⬇️ [DOWNLOAD] URL : {url}")
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    dest = UPLOADS_DIR / f"input_{os.urandom(4).hex()}.mp4"

    # 🟣 1. URL directe (R2, .mp4)
    if url.endswith(".mp4") or "r2.dev" in host or "r2.cloudflarestorage.com" in host:
        print("📥 Téléchargement direct HTTP ...")
        try:
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)
        except Exception as e:
            raise Exception(f"Téléchargement direct HTTP a échoué : {e}")

    else:
        # 🟣 2. Téléchargement via yt-dlp (YouTube, TikTok…)
        try:
            ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123 Safari/537.36"
            )

            ydl_opts = {
                "outtmpl": str(dest),
                "format": "bv*+ba/best/b",
                "merge_output_format": "mp4",
                "noplaylist": True,
                "quiet": True,
                "user_agent": ua,
                "http_headers": {"User-Agent": ua},
            }

            print("📥 yt-dlp ...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            raise Exception(f"yt-dlp a échoué : {e}")

    if not dest.exists() or dest.stat().st_size < 200_000:
        raise Exception("Téléchargement incomplet ou fichier trop petit.")

    print(f"✅ Vidéo téléchargée : {dest} ({dest.stat().st_size} bytes)")
    return str(dest)


# ======================================================
# EXTRACTION AUDIO COMPATIBLE WHISPER (<25MB)
# ======================================================

def extract_audio_mp3(video_path: str) -> str:
    """
    Extrait l'audio en MP3 à 64 kbps pour garantir <25MB même sur de longues vidéos.
    """
    audio_path = str(Path(video_path).with_suffix(".mp3"))

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", "64k",
        audio_path,
    ]

    print("🎧 Extraction audio :", " ".join(cmd))
    subprocess.run(cmd, check=True)

    size = Path(audio_path).stat().st_size
    print(f"🎧 Audio extrait ({size/1_000_000:.2f} Mo) → {audio_path}")

    if size > 25_000_000:
        raise Exception("Audio MP3 > 25 MB → réduire bitrate si besoin.")

    return audio_path


# ======================================================
# TRANSCRIPTION WHISPER (avec MP3)
# ======================================================

def transcribe_with_whisper(video_path: str) -> Dict[str, Any]:
    print("🎙️ Préparation Whisper...")

    # 1) Extraire audio
    audio_path = extract_audio_mp3(video_path)

    # 2) Envoyer MP3 à Whisper
    print("🎙️ Envoi MP3 → Whisper...")
    with open(audio_path, "rb") as f:
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
        )

    segments = [
        {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
        for s in res.segments
    ]

    print(f"📌 Segments générés : {len(segments)}")

    return {"text": res.text.strip(), "segments": segments}


# ======================================================
# SELECT VIRAL SEGMENTS (GPT)
# ======================================================

def select_viral_segments(segments, num_clips=8, min_duration=20, max_duration=45):
    if not segments:
        return []

    transcript = "\n".join(
        f"[{s['start']:.2f} → {s['end']:.2f}] {s['text']}" for s in segments
    )[:15000]

    system_prompt = (
        "Tu es un expert TikTok/Shorts. "
        "Donne les meilleurs moments viraux. "
        "Réponds STRICTEMENT en JSON."
    )

    user_prompt = f"""
Transcription :

{transcript}

Choisis {num_clips} clips de {min_duration}-{max_duration} secondes.
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

    data = json.loads(completion.choices[0].message.content)
    clips = data.get("clips", [])

    final = []
    for c in clips:
        s, e = float(c["start"]), float(c["end"])
        if e > s and (e - s) >= min_duration:
            final.append({
                "start": s,
                "end": e,
                "title": c.get("title", "Clip viral"),
                "reason": c.get("reason", "")
            })

    print(f"✅ Clips retenus : {len(final)}")
    return final


# ======================================================
# SUBS (ASS / KLAP STYLE)
# ======================================================

def _sanitize_ass_text(text):
    cleaned = text.replace("\n", " ").replace("\r", " ")
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    return " ".join(cleaned.split())


def _split_into_lines(words, max_words_per_line=7):
    if len(words) <= max_words_per_line:
        return [words]
    mid = len(words) // 2
    return [words[:mid], words[mid:]]


def build_karaoke_text(text, start, end):
    clean = _sanitize_ass_text(text)
    words = clean.split()
    if not words:
        return ""

    duration_ms = max((end - start) * 1000, 1)
    per_word = max(int(duration_ms / len(words)), 1)

    lines = _split_into_lines(words)
    ass_lines = [" ".join([f"{{\\k{per_word}}}{w}" for w in line]) for line in lines]

    return r"{\an2\fad(80,120)}" + r"\N".join(ass_lines)


def generate_ass_subs_for_clip(clip_start, clip_end, segments, subs_path):
    subs = pysubs2.SSAFile()

    style = pysubs2.SSAStyle()
    style.name = "KlapMain"
    style.fontname = "Poppins"
    style.fontsize = 64
    style.bold = True
    style.primarycolor = pysubs2.Color(255, 255, 255)
    style.secondarycolor = pysubs2.Color(255, 220, 0)
    style.outlinecolor = pysubs2.Color(0, 0, 0)
    style.marginv = 120
    style.alignment = 2

    subs.styles[style.name] = style

    for seg in segments:
        if seg["end"] <= clip_start or seg["start"] >= clip_end:
            continue

        start = max(seg["start"], clip_start) - clip_start
        end = min(seg["end"], clip_end) - clip_start

        ktext = build_karaoke_text(seg["text"], seg["start"], seg["end"])
        if not ktext:
            continue

        subs.events.append(
            pysubs2.SSAEvent(
                start=int(start * 1000),
                end=int(end * 1000),
                style="KlapMain",
                text=ktext,
            )
        )

    subs.save(str(subs_path))


# ======================================================
# FFMPEG CLIP EXPORT
# ======================================================

def ffmpeg_extract_and_style(src, out, subs, start, end):
    duration = max(end - start, 0.5)

    vf = f"scale=-2:1920,crop=1080:1920,subtitles='{subs}'"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", src,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        out,
    ]

    print("🎬 FFmpeg :", " ".join(cmd))
    subprocess.run(cmd, check=True)


# ======================================================
# PIPELINE GLOBAL
# ======================================================

def generate_shorts(
    input_video_path,
    num_clips=8,
    min_duration=20,
    max_duration=45,
):
    video = Path(input_video_path)
    if not video.exists():
        raise FileNotFoundError(video)

    print("🚀 Lancement pipeline IA...")

    # 1) Whisper
    tr = transcribe_with_whisper(str(video))
    segments = tr["segments"]

    # 2) GPT viral
    viral = select_viral_segments(segments, num_clips, min_duration, max_duration)

    results = []

    # 3) Génération des shorts
    for i, c in enumerate(viral, start=1):
        out_vid = SHORTS_DIR / f"short_{i:02d}.mp4"
        out_ass = SUBS_DIR / f"short_{i:02d}.ass"

        print(f"▶️ Clip {i} | {c['start']} → {c['end']}")

        generate_ass_subs_for_clip(c["start"], c["end"], segments, out_ass)
        ffmpeg_extract_and_style(str(video), str(out_vid), str(out_ass), c["start"], c["end"])

        video_url = upload_to_r2(str(out_vid), key_prefix="shorts")
        subs_url = upload_to_r2(str(out_ass), key_prefix="subs")

        results.append({
            "index": i,
            "title": c["title"],
            "reason": c["reason"],
            "start": c["start"],
            "end": c["end"],
            "video_url": video_url,
            "subs_url": subs_url,
        })

    print("🎉 Shorts générés :", len(results))
    return results
