"""Silent, editing-friendly MP4 derivatives; input files are never modified."""

from __future__ import annotations

import subprocess
from pathlib import Path


DEFAULT_VIDEO_PRESET = "h264_all_keyframes"
VIDEO_PRESETS = {
    key: {
        "preset": key, "format": "mp4", "video_codec": "h264",
        "audio_codec": None, "pixel_format": "yuv420p", "crf": 18,
        "all_keyframes": all_keyframes,
    }
    for key, all_keyframes in (("h264", False), ("h264_all_keyframes", True))
}
VIDEO_PRESETS["h264_small"] = {**VIDEO_PRESETS["h264"], "preset": "h264_small", "crf": 23}


def get_video_preset(key: object) -> dict[str, object]:
    if not isinstance(key, str) or key not in VIDEO_PRESETS:
        raise ValueError("unknown video preset")
    return VIDEO_PRESETS[key]


def transcode_video(source: Path, destination: Path, preset_key: str = DEFAULT_VIDEO_PRESET) -> None:
    preset = get_video_preset(preset_key)
    if destination.suffix.lower() != ".mp4":
        raise ValueError("video derivative must be MP4")
    if source.resolve() == destination.resolve() or destination.exists():
        raise FileExistsError("refusing to overwrite existing media")
    destination.parent.mkdir(parents=True, exist_ok=True)
    from .export_options import trim_arguments
    from .progress import encode
    trim, duration = trim_arguments(source)
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
        "-i", str(source), *trim, "-map", "0:v:0", "-an",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(preset["crf"]),
        "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-movflags", "+faststart",
    ]
    if preset["all_keyframes"]:
        command.extend(["-g", "1", "-keyint_min", "1", "-bf", "0"])
    try:
        encode([*command, str(destination)], source, "Encoding video", duration)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
