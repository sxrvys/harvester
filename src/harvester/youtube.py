from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .generic import DEFAULT_MAX_DURATION_SECONDS, DEFAULT_MAX_SOURCE_BYTES
from .instagram import _build_bundle, _media_files
from .model import HarvestItem
from .naming import propose_name


WATCH_URL = re.compile(
    r"^https://(?:www\.)?youtube\.com/watch\?v=([A-Za-z0-9_-]{11})(?:&[^#]*)?$"
)


class YouTubeAcquisitionError(RuntimeError):
    pass


def harvest_youtube_url(url: str, browser_profile: Path, archive_root: Path) -> Path:
    """Acquire exactly one explicitly supplied YouTube watch URL."""
    match = WATCH_URL.fullmatch(url)
    if not match:
        raise ValueError("expected one canonical YouTube watch URL")
    if not (browser_profile / "cookies.sqlite").is_file():
        raise ValueError("browser profile does not contain cookies.sqlite")

    video_id = match.group(1)
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory(prefix="harvester-youtube-") as temporary:
        staging = Path(temporary)
        command = [
            "yt-dlp",
            "--cookies-from-browser", f"firefox:{browser_profile}",
            "--no-playlist",
            "--write-info-json",
            "--no-write-playlist-metafiles",
            "--no-progress",
            "--newline",
            "--retries", "0",
            "--fragment-retries", "0",
            "--max-filesize", str(DEFAULT_MAX_SOURCE_BYTES),
            "--match-filter", f"duration <= {DEFAULT_MAX_DURATION_SECONDS} & duration != NA",
            "--restrict-filenames",
            "--output", str(staging / "%(id)s.%(ext)s"),
            canonical_url,
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        diagnostic = "\n".join((completed.stdout, completed.stderr)).casefold()
        if any(marker in diagnostic for marker in ("drm", "sign in", "login required", "http error 429")):
            raise YouTubeAcquisitionError("authorization or access control stopped the harvest")
        media_files = _media_files(staging)
        if completed.returncode != 0 or len(media_files) != 1:
            if "duration" in diagnostic:
                raise YouTubeAcquisitionError("video exceeds the duration limit")
            if "filesize" in diagnostic or "file is larger" in diagnostic:
                raise YouTubeAcquisitionError("video exceeds the size limit")
            raise YouTubeAcquisitionError("single-video download failed")
        if media_files[0].stat().st_size > DEFAULT_MAX_SOURCE_BYTES:
            raise YouTubeAcquisitionError("video exceeds the size limit")

        info = _read_info(sorted(staging.glob("*.info.json")))
        duration = info.get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise YouTubeAcquisitionError("video duration is unavailable")
        if duration > DEFAULT_MAX_DURATION_SECONDS:
            raise YouTubeAcquisitionError("video exceeds the duration limit")
        title = info.get("title") if isinstance(info.get("title"), str) else None
        uploader = info.get("uploader") if isinstance(info.get("uploader"), str) else None
        _, readable_title, creator, _ = propose_name({
            "source_id": video_id, "caption": title, "author": uploader,
        })
        item = HarvestItem(
            source="youtube",
            source_id=video_id,
            source_url=canonical_url,
            retrieved_at=datetime.now(timezone.utc),
            author=uploader,
            caption=info.get("description") if isinstance(info.get("description"), str) else None,
            title=readable_title,
            creator=creator,
            source_metadata={
                "extractor": info.get("extractor"),
                "channel_id": info.get("channel_id"),
                "duration": duration,
            },
        )
        return _build_bundle(item, media_files, archive_root)


def _read_info(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise YouTubeAcquisitionError("video metadata is unavailable")
    try:
        with paths[0].open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError):
        raise YouTubeAcquisitionError("video metadata is unavailable") from None
    if not isinstance(value, dict):
        raise YouTubeAcquisitionError("video metadata is unavailable")
    return value
