from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .instagram import _build_bundle, _media_files
from .audio import DEFAULT_AUDIO_PRESET
from .media import probe
from .model import HarvestItem

DEFAULT_MAX_DURATION_SECONDS = 10 * 60
DEFAULT_MAX_SOURCE_BYTES = 500 * 1024 * 1024


@dataclass(frozen=True)
class GenericMediaError(Exception):
    code: str
    message: str


def safe_http_url(url: object) -> str:
    if not isinstance(url, str) or not url or len(url) > 4096:
        raise GenericMediaError("invalid_url", "Media URL must be a short HTTP(S) URL")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise GenericMediaError("invalid_url", "Media URL is invalid") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise GenericMediaError("unsafe_url", "Only public HTTP(S) media URLs are accepted")
    if port is not None and not 1 <= port <= 65535:
        raise GenericMediaError("unsafe_url", "Media URL port is invalid")
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise GenericMediaError("unsafe_url", "Local and private destinations are not accepted")
    try:
        addresses = {result[4][0] for result in socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)}
    except OSError:
        raise GenericMediaError("acquisition_failed", "Media destination could not be resolved") from None
    if not addresses or any(not ipaddress.ip_address(address.split("%", 1)[0]).is_global for address in addresses):
        raise GenericMediaError("unsafe_url", "Local and private destinations are not accepted")
    return url


def stable_page_url(url: object) -> str:
    safe_http_url(url)
    parsed = urlsplit(str(url))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def harvest_selected_media(
    media_url: str,
    page_url: str,
    archive_root: Path,
    max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
    audio_preset: str = DEFAULT_AUDIO_PRESET,
) -> Path:
    """Harvest one explicitly selected ordinary media URL within strict defaults."""
    selected_url = safe_http_url(media_url)
    source_url = stable_page_url(page_url)
    info = _preflight(selected_url)
    if info.get("_type") in {"playlist", "multi_video"} or info.get("entries"):
        raise GenericMediaError("unsupported_media", "Only one selected media item is accepted")
    direct = info.get("direct") is True
    duration = _positive_number(info.get("duration"))
    if duration is None and not direct:
        raise GenericMediaError("unsupported_media", "Selected media duration is unavailable")
    if duration is not None and duration > max_duration_seconds:
        raise GenericMediaError("duration_limit", "Selected media exceeds the duration limit")
    source_bytes = _positive_number(info.get("filesize")) or _positive_number(info.get("filesize_approx"))
    if source_bytes is None and direct:
        source_bytes = _remote_size(selected_url)
    if source_bytes is None:
        raise GenericMediaError("unsupported_media", "Selected media size is unavailable")
    if source_bytes > max_source_bytes:
        raise GenericMediaError("size_limit", "Selected media exceeds the size limit")

    resolved_url = info.get("url")
    if not isinstance(resolved_url, str):
        raise GenericMediaError("unsupported_media", "Selected media has no ordinary downloadable URL")
    safe_http_url(resolved_url)

    identity_input = f"{source_url}\n{urlunsplit(urlsplit(selected_url)._replace(query='', fragment=''))}"
    source_id = hashlib.sha256(identity_input.encode("utf-8")).hexdigest()[:16]
    with tempfile.TemporaryDirectory(prefix="harvester-selected-") as temporary:
        staging = Path(temporary)
        if direct:
            suffix = Path(urlsplit(resolved_url).path).suffix.lower()
            if not suffix or len(suffix) > 10:
                suffix = ".media"
            _download_direct(resolved_url, staging / f"selected{suffix}", max_source_bytes)
            completed = subprocess.CompletedProcess([], 0, "", "")
        else:
            command = [
                "yt-dlp",
                "--no-playlist",
                "--max-downloads", "1",
                "--retries", "0",
                "--no-progress",
                "--max-filesize", str(max_source_bytes),
                "--match-filter", f"duration <= {max_duration_seconds} & duration != NA",
                "--output", str(staging / "selected.%(ext)s"),
                resolved_url,
            ]
            completed = subprocess.run(command, capture_output=True, text=True)
        media_files = _media_files(staging)
        if completed.returncode != 0 or len(media_files) != 1:
            raise GenericMediaError("acquisition_failed", "Selected media acquisition failed")
        acquired = media_files[0]
        if acquired.stat().st_size > max_source_bytes:
            raise GenericMediaError("size_limit", "Selected media exceeds the size limit")
        facts = probe(acquired)
        actual_duration = _probe_duration(facts)
        if actual_duration is None or actual_duration > max_duration_seconds:
            code = "duration_limit" if actual_duration else "unsupported_media"
            raise GenericMediaError(code, "Selected media duration is unsupported")
        item = HarvestItem(
            source="generic",
            source_id=source_id,
            source_url=source_url,
            retrieved_at=datetime.now(timezone.utc),
            title=_text(info.get("title")) or "selected-media",
            creator=_text(info.get("uploader")) or _text(info.get("channel")),
            source_metadata={"selection": "visible-media-element"},
        )
        return _build_bundle(item, [acquired], archive_root, audio_preset)


def _preflight(url: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["yt-dlp", "--dump-single-json", "--no-playlist", "--retries", "0", url],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise GenericMediaError("acquisition_failed", "Selected media preflight failed")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise GenericMediaError("unsupported_media", "Selected media metadata is unavailable") from None
    if not isinstance(value, dict):
        raise GenericMediaError("unsupported_media", "Selected media metadata is unavailable")
    return value


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request | None:
        safe_http_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _remote_size(url: str) -> float | None:
    opener = build_opener(_SafeRedirectHandler())
    try:
        with opener.open(Request(url, method="HEAD"), timeout=20) as response:
            value = response.headers.get("Content-Length")
    except (OSError, ValueError):
        return None
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return float(size) if size > 0 else None


def _download_direct(url: str, destination: Path, maximum_bytes: int) -> None:
    opener = build_opener(_SafeRedirectHandler())
    total = 0
    try:
        with opener.open(Request(url), timeout=30) as response, destination.open("wb") as output:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                total += len(chunk)
                if total > maximum_bytes:
                    raise GenericMediaError("size_limit", "Selected media exceeds the size limit")
                output.write(chunk)
    except GenericMediaError:
        raise
    except (OSError, ValueError):
        raise GenericMediaError("acquisition_failed", "Selected media acquisition failed") from None


def _positive_number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _probe_duration(facts: dict[str, Any]) -> float | None:
    try:
        value = float(facts["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        return None
    return value if value > 0 else None


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
