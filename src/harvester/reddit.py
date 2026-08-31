from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .generic import DEFAULT_MAX_DURATION_SECONDS, DEFAULT_MAX_SOURCE_BYTES
from .audio import DEFAULT_AUDIO_PRESET
from .instagram import _build_bundle, _media_files
from .model import HarvestItem
from .naming import propose_name


POST_URL = re.compile(
    r"^https://www\.reddit\.com/r/[^/?#]+/comments/([A-Za-z0-9]+)/[^/?#]+/?$"
)


class RedditAcquisitionError(RuntimeError):
    pass


def harvest_reddit_url(
    url: str,
    browser_profile: Path,
    archive_root: Path,
    audio_preset: str = DEFAULT_AUDIO_PRESET,
) -> Path:
    """Acquire media from exactly one explicitly supplied Reddit post URL."""
    match = POST_URL.fullmatch(url)
    if not match:
        raise ValueError("expected one canonical Reddit post URL")
    if not (browser_profile / "cookies.sqlite").is_file():
        raise ValueError("browser profile does not contain cookies.sqlite")

    post_id = match.group(1).casefold()
    with tempfile.TemporaryDirectory(prefix="harvester-reddit-") as temporary:
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
            url,
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        diagnostic = "\n".join((completed.stdout, completed.stderr)).casefold()
        if any(marker in diagnostic for marker in (
            "login required", "sign in", "http error 401", "http error 403",
            "http error 429", "too many requests", "drm",
        )):
            raise RedditAcquisitionError("authorization or access control stopped the harvest")
        media_files = _media_files(staging)
        if completed.returncode != 0 or len(media_files) != 1:
            if "duration" in diagnostic:
                raise RedditAcquisitionError("post media exceeds the duration limit")
            if "filesize" in diagnostic or "file is larger" in diagnostic:
                raise RedditAcquisitionError("post media exceeds the size limit")
            raise RedditAcquisitionError("single-post media download failed")
        if media_files[0].stat().st_size > DEFAULT_MAX_SOURCE_BYTES:
            raise RedditAcquisitionError("post media exceeds the size limit")

        info = _read_info(sorted(staging.glob("*.info.json")))
        duration = info.get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise RedditAcquisitionError("post media duration is unavailable")
        if duration > DEFAULT_MAX_DURATION_SECONDS:
            raise RedditAcquisitionError("post media exceeds the duration limit")
        title = info.get("title") if isinstance(info.get("title"), str) else None
        uploader = info.get("uploader") if isinstance(info.get("uploader"), str) else None
        _, readable_title, creator, _ = propose_name({
            "source_id": post_id, "caption": title, "author": uploader,
        })
        item = HarvestItem(
            source="reddit",
            source_id=post_id,
            source_url=url,
            retrieved_at=datetime.now(timezone.utc),
            author=uploader,
            caption=info.get("description") if isinstance(info.get("description"), str) else title,
            title=readable_title,
            creator=creator,
            source_metadata={
                "extractor": info.get("extractor"),
                "media_id": info.get("id"),
                "duration": duration,
            },
        )
        return _build_bundle(item, media_files, archive_root, audio_preset)


def _read_info(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise RedditAcquisitionError("post media metadata is unavailable")
    try:
        with paths[0].open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError):
        raise RedditAcquisitionError("post media metadata is unavailable") from None
    if not isinstance(value, dict):
        raise RedditAcquisitionError("post media metadata is unavailable")
    return value
