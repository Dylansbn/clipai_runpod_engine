import traceback
from typing import Any, Dict
import os
import subprocess

import runpod
from processor import generate_shorts, download_video


def debug_download(url: str):
    path = download_video(url)

    size = os.path.getsize(path)

    # ffprobe check
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        path
    ]
    probe = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return {
        "file_path": path,
        "size_bytes": size,
        "stdout": probe.stdout.decode(errors="ignore"),
        "stderr": probe.stderr.decode(errors="ignore")
    }


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        inp = event.get("input", {})
        task = inp.get("task", "ping")

        # 1) PING
        if task == "ping":
            return {"status": "ok", "message": "alive"}

        # 2) DEBUG DOWNLOAD
        if task == "debug_download":
            url = inp.get("video_url")
            if not url:
                return {"status": "error", "error": "missing video_url"}

            return debug_download(url)

        # 3) PROCESS FULL PIPELINE
        if task == "process":
            url = inp.get("video_url")
            if not url:
                return {"status": "error", "error": "missing video_url"}

            local_path = download_video(url)

            clips = generate_shorts(
                input_video_path=local_path,
                num_clips=int(inp.get("num_clips", 8)),
                min_duration=float(inp.get("min_duration", 20)),
                max_duration=float(inp.get("max_duration", 45))
            )

            return {"status": "done", "clips": clips}

        return {"status": "error", "error": "unknown task"}

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


runpod.serverless.start({"handler": handler})
