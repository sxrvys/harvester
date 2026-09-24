"""Acquire one explicitly submitted public media page with yt-dlp extractors."""
from __future__ import annotations

from .limits import acquisition_limits

import hashlib
import ipaddress
import json
import math
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class WebSourceError(ValueError):
    pass


def public_page(value):
    """Offline queue validation; temporary/authenticated media URLs aren't journaled."""
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ValueError("Use a public media page URL")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
        raise ValueError("Use a public HTTP(S) media page without credentials")
    if host == "localhost" or host.endswith((".localhost", ".local")) or "." not in host:
        raise ValueError("Local network addresses are not supported")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("Local network addresses are not supported")
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower().startswith("utm_") or key.lower() in {"fbclid", "gclid", "si", "feature"}:
            continue
        # Only ordinary item identifiers are persisted for general sources.
        # Signed/player URLs belong in a transient capture workflow, not a queue.
        if key.lower() not in {"id", "v", "video", "video_id", "clip", "clip_id", "item"}:
            raise ValueError("Use the public page link, without temporary tokens or extra query parameters")
        query.append((key, item))
    authority = f"[{host}]" if ":" in host else host
    return urlunsplit((parsed.scheme, authority, parsed.path or "/", urlencode(query), ""))


def validate_info(info):
    from .limits import acquisition_limits
    if not isinstance(info, dict):
        raise WebSourceError("This page did not provide usable media details")
    if info.get("_type") in {"playlist", "multi_video", "url", "url_transparent"} or "entries" in info:
        raise WebSourceError("This link contains multiple items. Open one video or audio item and try again")
    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
        raise WebSourceError("Live or upcoming streams are not supported. Try a finished recording")
    if info.get("has_drm"):
        raise WebSourceError("This media is protected by DRM and cannot be harvested")
    duration = info.get("duration")
    if isinstance(duration, (int, float)) and math.isfinite(duration) and duration > acquisition_limits.get().duration:
        raise WebSourceError("Source exceeds the duration limit configured in Harvester Settings")
    for field in ("filesize", "filesize_approx"):
        size = info.get(field)
        if isinstance(size, (int, float)) and size > acquisition_limits.get().size:
            raise WebSourceError("Source exceeds the download size limit configured in Harvester Settings")


def harvest_web_url(url, archive_root, audio_preset="wav_48k_24", video_preset="h264_all_keyframes"):
    from .generic import safe_http_url, _probe_duration, GenericMediaError
    from .instagram import _build_bundle, _media_files
    from .media import probe
    from .model import HarvestItem
    from .progress import download
    canonical = public_page(url)
    try:
        safe_http_url(canonical)
    except GenericMediaError:
        raise WebSourceError("Could not reach a public source. Check the link and network connection") from None
    common = ["yt-dlp", "--ignore-config", "--no-playlist", "--playlist-items", "1",
              "--retries", "0", "--fragment-retries", "0", "--socket-timeout", "20"]
    try:
        metadata = subprocess.run([*common, "--dump-single-json", "--skip-download", canonical],
                                  capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        raise WebSourceError("The site took too long to respond. Try again later") from None
    if metadata.returncode:
        diagnostic = metadata.stderr.lower()
        if "drm" in diagnostic:
            raise WebSourceError("This media is protected by DRM and cannot be harvested")
        if any(marker in diagnostic for marker in ("sign in", "login", "403", "429", "private video")):
            raise WebSourceError("This source requires login or has blocked access. Public-page harvesting cannot access it")
        raise WebSourceError("No downloadable media found on this page. Try the individual media page or a direct file link")
    try:
        info = json.loads(metadata.stdout)
    except ValueError:
        raise WebSourceError("This page did not provide usable media details") from None
    validate_info(info)
    with tempfile.TemporaryDirectory(prefix="harvester-web-") as temporary:
        staging = Path(temporary)
        command = [*common, "--no-progress", "--no-write-info-json", "--no-write-thumbnail",
                   "--max-filesize", str(acquisition_limits.get().size),
                   "--match-filter", f"!is_live & duration <=? {acquisition_limits.get().duration}",
                   "--output", str(staging / "source.%(ext)s"), canonical]
        result = download(command)
        files = _media_files(staging)
        if result.returncode or len(files) != 1:
            raise WebSourceError("The source could not be downloaded as one media item. Check access and source limits")
        source = files[0]
        if source.stat().st_size > acquisition_limits.get().size:
            raise WebSourceError("Source exceeds the download size limit configured in Harvester Settings")
        duration = _probe_duration(probe(source))
        if duration is None or not math.isfinite(duration) or duration <= 0:
            raise WebSourceError("The downloaded item is not a playable audio or video file")
        if duration > acquisition_limits.get().duration:
            raise WebSourceError("Source exceeds the duration limit configured in Harvester Settings")
        item = HarvestItem(source="generic", source_id=hashlib.sha256(canonical.encode()).hexdigest()[:16],
                           source_url=canonical, retrieved_at=datetime.now(timezone.utc),
                           title=info.get("title") if isinstance(info.get("title"), str) else "Found media",
                           creator=info.get("uploader") if isinstance(info.get("uploader"), str) else None,
                           source_metadata={"selection": "explicit-public-page", "duration": duration})
        return _build_bundle(item, files, archive_root, audio_preset, video_preset=video_preset)
