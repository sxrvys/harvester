from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def probe(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def has_audio(probe_result: dict[str, Any]) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in probe_result.get("streams", []))


def extract_wav(source: Path, destination: Path) -> None:
    """Create the V0 DAW contract: stereo 48 kHz, signed 24-bit PCM WAV."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vn", "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_s24le", str(destination),
        ],
        check=True,
    )

