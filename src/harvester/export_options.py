"""Validated, per-job export choices. Legacy jobs retain their original defaults."""
import math


def seconds(value):
    if isinstance(value, bool):
        raise ValueError("Use seconds or HH:MM:SS")
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError("Use seconds or HH:MM:SS")
    numbers = [float(part) for part in parts]
    if any(not math.isfinite(n) or n < 0 for n in numbers) or any(n >= 60 for n in numbers[1:]):
        raise ValueError("Use a valid nonnegative time")
    total = 0
    for number in numbers:
        total = total * 60 + number
    return total


def normalize(options=None):
    from .video import VIDEO_PRESETS
    from .audio import AUDIO_PRESETS
    if options is None:
        return {}
    if not isinstance(options, dict) or set(options) - {"start", "end", "video_preset", "audio_preset"}:
        raise ValueError("Unknown export option")
    result = {}
    for key, presets in (("video_preset", VIDEO_PRESETS), ("audio_preset", AUDIO_PRESETS)):
        if key in options:
            if not isinstance(options[key], str) or options[key] not in presets:
                raise ValueError("Unknown export preset")
            # Canonical defaults keep existing jobs deduplicated.
            if options[key] not in {"h264_all_keyframes", "wav_48k_24"}:
                result[key] = options[key]
    start = seconds(options.get("start", 0))
    if start >= 21600:
        raise ValueError("Clip start must be less than 6 hours")
    if start:
        result["start"] = start
    if options.get("end") not in (None, ""):
        end = seconds(options["end"])
        if not start < end <= 21600:
            raise ValueError("Clip end must follow start and be within 6 hours")
        result["end"] = end
    return result


def trim_arguments(source):
    from .processing import export_options
    options = export_options.get()
    if not options.get("start") and "end" not in options:
        return [], None
    from .media import probe
    duration = float(probe(source).get("format", {}).get("duration", 0))
    start = options.get("start", 0)
    end = options.get("end", duration)
    if not math.isfinite(duration) or duration <= start or end > duration + 0.1:
        raise ValueError("Clip range is outside the source duration")
    args = ["-ss", str(start)] if start else []
    return args + ["-t", str(min(end, duration) - start)], min(end, duration) - start
