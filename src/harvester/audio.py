from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioPreset:
    key: str
    label: str
    extension: str
    ffmpeg_args: tuple[str, ...]
    metadata: dict[str, object]


DEFAULT_AUDIO_PRESET = "wav_48k_24"
AUDIO_PRESETS = {
    "wav_48k_24": AudioPreset(
        "wav_48k_24", "Production WAV — 48 kHz / 24-bit", ".wav",
        ("-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le"),
        {"preset": "wav_48k_24", "format": "wav", "sample_rate": 48000, "bit_depth": 24, "channels": 2},
    ),
    "wav_44k_16": AudioPreset(
        "wav_44k_16", "Standard WAV — 44.1 kHz / 16-bit", ".wav",
        ("-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le"),
        {"preset": "wav_44k_16", "format": "wav", "sample_rate": 44100, "bit_depth": 16, "channels": 2},
    ),
    "flac_48k_24": AudioPreset(
        "flac_48k_24", "FLAC — 48 kHz / 24-bit", ".flac",
        ("-ar", "48000", "-ac", "2", "-c:a", "flac", "-sample_fmt", "s32"),
        {"preset": "flac_48k_24", "format": "flac", "sample_rate": 48000, "bit_depth": 24, "channels": 2},
    ),
    "mp3_320": AudioPreset(
        "mp3_320", "MP3 — 320 kbps", ".mp3",
        ("-ar", "48000", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "320k"),
        {"preset": "mp3_320", "format": "mp3", "sample_rate": 48000, "bitrate_kbps": 320, "channels": 2},
    ),
    "mp3_192": AudioPreset(
        "mp3_192", "MP3 — 192 kbps", ".mp3",
        ("-ar", "48000", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k"),
        {"preset": "mp3_192", "format": "mp3", "sample_rate": 48000, "bitrate_kbps": 192, "channels": 2},
    ),
}


def get_audio_preset(key: object) -> AudioPreset:
    if not isinstance(key, str) or key not in AUDIO_PRESETS:
        raise ValueError("unknown audio preset")
    return AUDIO_PRESETS[key]


def extract_audio(source: Path, destination: Path, preset_key: str = DEFAULT_AUDIO_PRESET) -> None:
    preset = get_audio_preset(preset_key)
    if destination.suffix.casefold() != preset.extension:
        raise ValueError("audio derivative extension does not match preset")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vn", *preset.ffmpeg_args, str(destination),
        ],
        check=True,
    )
