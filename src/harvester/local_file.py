from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .archive import _sha256
from .audio import DEFAULT_AUDIO_PRESET
from .generic import DEFAULT_MAX_DURATION_SECONDS, DEFAULT_MAX_SOURCE_BYTES
from .instagram import _build_bundle
from .media import probe
from .model import HarvestItem


class LocalFileError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def harvest_local_file(
    source: Path,
    archive_root: Path,
    audio_preset: str = DEFAULT_AUDIO_PRESET,
    max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> Path:
    """Ingest exactly one local file without retaining its original path."""
    source = source.expanduser().resolve()
    if not source.is_file():
        raise LocalFileError("invalid_file", "Choose one existing local file")
    source_bytes = source.stat().st_size
    if source_bytes <= 0:
        raise LocalFileError("invalid_file", "The selected file is empty")
    if source_bytes > max_source_bytes:
        raise LocalFileError("size_limit", "The selected file exceeds the size limit")
    try:
        facts = probe(source)
    except Exception:
        raise LocalFileError("unsupported_media", "The selected file is not supported media") from None
    streams = facts.get("streams", [])
    if not any(stream.get("codec_type") in {"audio", "video"} for stream in streams):
        raise LocalFileError("unsupported_media", "The selected file has no audio or video stream")
    try:
        duration = float(facts["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise LocalFileError("unsupported_media", "The selected file duration is unavailable") from None
    if duration <= 0:
        raise LocalFileError("unsupported_media", "The selected file duration is unavailable")
    if duration > max_duration_seconds:
        raise LocalFileError("duration_limit", "The selected file exceeds the duration limit")

    digest = _sha256(source)
    item = HarvestItem(
        source="local",
        source_id=digest[:16],
        source_url=None,
        retrieved_at=datetime.now(timezone.utc),
        title=source.stem,
        source_metadata={
            "selection": "finder-file-picker",
            "original_filename": source.name,
            "original_bytes": source_bytes,
            "sha256": digest,
            "duration": duration,
        },
    )
    return _build_bundle(item, [source], archive_root, audio_preset)
