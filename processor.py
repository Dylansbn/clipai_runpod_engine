import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any

import pysubs2
from openai import OpenAI
import yt_dlp


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
# 0. TÉLÉCHARGEMENT ROBUSTE (YT, TikTok, Vimeo…)
# ==============================

def download_video(url: str) -> str:
    """
    Téléchargement robuste avec yt-dlp (YouTube, TikTok, Vimeo…).

    NOTE : pour YouTube, YouTube peut parfois demander des cookies / anti-bot.
    Dans ce cas, tu peux limiter ton produit aux vidéos non protégées
    ou privilégier l'upload direct par l'utilisateur.
    """
    print(f"⬇️ Downloading: {url}")

    output_path = UPLOADS_DIR / f"input_{os.urandom(4).hex()}.mp4"

    ydl_opts = {
        "outtmpl": str(output_path),
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "noprogress": True,
        "format": "mp4/best",
        "user_agent": "Mozilla/5.0",
        "retries": 5,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise Exception(f"yt-dlp a échoué : {e}")

    if not output_path.exists():
        raise Exception("Téléchargement échoué : fichier introuvable après yt-dlp.")

    size = output_path.stat().st_size
    print(f"✅ Download OK → {output_path} ({size} bytes)")
    return str(output_path)


# ==============================
# 1. TRANSCRIPTION WHISPER API
# ==============================

def transcribe_with_whisper(video_path: str) -> Dict[str, Any]:
    """Transcription via Whisper API (pas de modèle local)."""
    print("🎙️ Envoi → Whisper API ...")

    with open(video_path, "rb") as f:
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json"
        )

    segments = [{
        "start": float(s.start),
        "end": float(s.end),
        "text": s.text.strip()
    } for s in res.segments]

    print(f"📌 Segments générés : {len(segments)}")

    return {
        "text": res.text.strip(),
        "segments": segments
    }


# ==============================
# 2. IA VIRALE PRO (GPT) — hooks, résumés, hashtags
# ==============================

def select_viral_segments(
    segments: List[Dict[str, Any]],
    num_clips: int = 8,
    min_duration: float = 20.0,
    max_duration: float = 45.0,
) -> List[Dict[str, Any]]:

    """
    Sélectionne les meilleurs moments façon Klap/OpusClip.

    Pour chaque clip, on demande à GPT :
      - start / end
      - title : titre court et viral
      - reason : pourquoi ce moment est viral
      - hook : phrase d’accroche pour début de short
      - summary : résumé 1 phrase
      - hashtags : liste de hashtags pertinents
    """

    if not segments:
        return []

    transcript = "\n".join(
        f"[{s['start']:.2f} → {s['end']:.2f}] {s['text']}"
        for s in segments
    )[:15000]

    total_duration = float(segments[-1]["end"])

    json_schema = """
{
  "clips": [
    {
      "start": 10.0,
      "end": 32.5,
      "title": "Titre viral court",
      "reason": "Pourquoi ce passage est viral.",
      "hook": "Phrase d'accroche pour les 2-3 premières secondes.",
      "summary": "Résumé très court du clip.",
      "hashtags": ["#exemple", "#tiktok", "#shorts"]
    }
  ]
}
"""

    system_prompt = (
        "Tu es un expert montage Shorts/TikTok (comme Klap.app / OpusClip). "
        "À partir d’une transcription horodatée, tu choisis les meilleurs moments "
        f"pour {num_clips} clips courts. Chaque clip doit avoir une durée entre "
        f"{min_duration} et {max_duration} secondes, rester dans la vidéo (0 → {total_duration}s), "
        "et commencer sur un hook fort (pas en plein milieu d’une phrase si possible). "
        "Réponds STRICTEMENT en JSON valide qui respecte ce schéma :"
        f"\n{json_schema}"
    )

    user_prompt = f"""
Transcription horodatée :

{transcript}

Consignes :
- Choisis les {num_clips} meilleurs extraits.
- Chaque extrait doit :
  - durer entre {min_duration} et {max_duration} secondes,
  - être intéressant du point de vue TikTok / Reels / Shorts,
  - commencer par une phrase qui accroche,
  - donner envie de regarder jusqu'au bout.

Ne renvoie AUCUN texte hors du JSON.
"""

    print("🤖 Appel GPT (IA virale PRO)...")
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",  # tu peux passer en gpt-4.1 normal si tu veux encore plus quali
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    raw = completion.choices[0].message.content
    print("🔎 JSON IA reçu (troncature) :", raw[:400])

    clips_data: List[Dict[str, Any]] = []

    try:
        data = json.loads(raw)
        clips_data = data.get("clips", [])
    except Exception as e:
        print("⚠️ Erreur parsing JSON GPT :", e)
        clips_data = []

    final: List[Dict[str, Any]] = []

    for c in clips_data:
        try:
            s = float(c["start"])
            e = float(c["end"])
            if e <= s:
                continue
            if (e - s) < min_duration or (e - s) > max_duration:
                # on tolère un peu, mais on skip les extrêmes
                continue

            final.append({
                "start": s,
                "end": e,
                "title": c.get("title", "Clip viral"),
                "reason": c.get("reason", ""),
                "hook": c.get("hook", ""),
                "summary": c.get("summary", ""),
                "hashtags": c.get("hashtags", []),
            })
        except Exception:
            continue

    # Fallback si GPT a foiré ou renvoyé trop peu de clips
    if len(final) == 0 and total_duration > 0:
        print("⚠️ Fallback IA virale : génération naïve des clips.")
        approx_len = max(min_duration, (total_duration / max(num_clips, 1)))
        t = 0.0
        idx = 0
        while t + min_duration < total_duration and idx < num_clips:
            start = t
            end = min(t + approx_len, total_duration)
            final.append({
                "start": start,
                "end": end,
                "title": f"Clip {idx+1}",
                "reason": "Fallback automatique",
                "hook": "",
                "summary": "",
                "hashtags": [],
            })
            t = end
            idx += 1

    print(f"✅ Clips retenus (IA virale PRO) : {len(final)}")
    return final


# ==============================
# 3. SOUS-TITRES KLAP PRO
# ==============================

def _sanitize_ass_text(text: str) -> str:
    cleaned = text.replace("\n", " ").replace("\r", " ")
    cleaned = cleaned.replace("{", "(").replace("}", ")")
    return " ".join(cleaned.split())


def _split_into_lines(words: List[str], max_words_per_line: int = 7):
    if len(words) <= max_words_per_line:
        return [words]

    mid = len(words) // 2
    return [words[:mid], words[mid:]]


def build_karaoke_text(text: str, start: float, end: float) -> str:
    clean = _sanitize_ass_text(text)
    words = clean.split()
    if not words:
        return ""

    duration_ms = max((end - start) * 1000, 1)
    per_word = max(int(duration_ms / len(words)), 1)

    lines = _split_into_lines(words, max_words_per_line=7)
    ass_lines = []

    for line_words in lines:
        parts = [f"{{\\k{per_word}}}{w}" for w in line_words]
        ass_lines.append(" ".join(parts))

    prefix = r"{\an2\fad(80,120)}"
    return prefix + r"\N".join(ass_lines)


def generate_ass_subs_for_clip(
    clip_start: float,
    clip_end: float,
    segments: List[Dict[str, Any]],
    subs_path: Path,
):

    subs = pysubs2.SSAFile()

    style = pysubs2.SSAStyle()
    style.name = "KlapMain"
    style.fontname = "Poppins"
    style.fontsize = 64
    style.bold = True

    style.primarycolor = pysubs2.Color(255, 255, 255)   # blanc
    style.secondarycolor = pysubs2.Color(255, 220, 0)   # jaune highlight
    style.outlinecolor = pysubs2.Color(0, 0, 0)         # noir
    style.backcolor = pysubs2.Color(0, 0, 0, 0)

    style.outline = 5
    style.shadow = 0
    style.borderstyle = 1

    style.marginl = 40
    style.marginr = 40
    style.marginv = 120
    style.alignment = 2  # bas-centre

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
        ev.style = "KlapMain"
        ev.text = ktext

        subs.events.append(ev)

    subs.save(str(subs_path))


# ==============================
# 4. FFMPEG : CUT + 9:16 + SUBTITLES
# ==============================

def ffmpeg_extract_and_style(src: str, out: str, subs: str, start: float, end: float):
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
        "-pix_fmt", "yuv420p",
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

    print("🚀 Pipeline lancé…")

    video = Path(input_video_path)
    if not video.exists():
        raise FileNotFoundError(video)

    # 1. Transcription
    tr = transcribe_with_whisper(str(video))
    segments = tr["segments"]

    # 2. IA virale PRO
    viral = select_viral_segments(segments, num_clips, min_duration, max_duration)

    results = []

    # 3. Génération
    for i, c in enumerate(viral, start=1):
        out_vid = SHORTS_DIR / f"short_{i:02d}.mp4"
        out_ass = SUBS_DIR / f"short_{i:02d}.ass"

        print(f"▶️ Clip {i} | {c['start']} → {c['end']}")

        generate_ass_subs_for_clip(c["start"], c["end"], segments, out_ass)
        ffmpeg_extract_and_style(str(video), str(out_vid), str(out_ass), c["start"], c["end"])

        results.append({
            "index": i,
            "title": c.get("title", f"Clip {i}"),
            "reason": c.get("reason", ""),
            "hook": c.get("hook", ""),
            "summary": c.get("summary", ""),
            "hashtags": c.get("hashtags", []),
            "start": c["start"],
            "end": c["end"],
            "video_path": str(out_vid),
            "subs_path": str(out_ass),
        })

    print("🎉 Shorts générés :", len(results))
    return results
