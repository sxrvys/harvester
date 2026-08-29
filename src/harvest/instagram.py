from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .archive import Archive
from .media import extract_wav, has_audio, probe
from .model import HarvestItem
from .naming import propose_name


POST_URL = re.compile(r"^https://(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)/?(?:\?.*)?$")
AUTH_FAILURE_MARKERS = (
    "login required", "log in", "checkpoint", "challenge", "authentication",
    "http error 401", "http error 403", "http error 429", "too many requests",
)


class AcquisitionError(RuntimeError):
    pass


def harvest_instagram_url(url: str, browser_profile: Path, archive_root: Path) -> Path:
    """Acquire exactly one supplied Instagram URL through one explicit Firefox profile."""

    match = POST_URL.fullmatch(url)
    if not match:
        raise ValueError("expected one canonical Instagram /p/ or /reel/ URL")
    if not (browser_profile / "cookies.sqlite").is_file():
        raise ValueError("browser profile does not contain cookies.sqlite")

    shortcode = match.group(1)
    canonical_url = f"https://www.instagram.com/p/{shortcode}/"
    with tempfile.TemporaryDirectory(prefix="harvest-instagram-") as temporary:
        staging = Path(temporary)
        command = [
            "yt-dlp",
            "--cookies-from-browser", f"firefox:{browser_profile}",
            "--write-info-json",
            "--no-write-playlist-metafiles",
            "--no-progress",
            "--newline",
            "--sleep-requests", "3",
            "--sleep-interval", "10",
            "--max-sleep-interval", "15",
            "--retries", "0",
            "--restrict-filenames",
            "--output", str(staging / "%(playlist_index|1)02d_%(id)s.%(ext)s"),
            url,
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        diagnostic = "\n".join((completed.stdout, completed.stderr)).lower()
        if completed.returncode != 0 and any(marker in diagnostic for marker in AUTH_FAILURE_MARKERS):
            raise AcquisitionError(f"authentication/rate-limit stop; yt-dlp exited {completed.returncode}")

        if completed.returncode != 0 and not _media_files(staging):
            raise AcquisitionError(f"download failed; yt-dlp exited {completed.returncode}")

        info_files = sorted(staging.glob("*.info.json"))
        media_files = _media_files(staging)
        if not media_files:
            raise AcquisitionError("download completed without any media files")

        info = _read_info(info_files)
        caption = info.get("description")
        _, title, creator, _ = propose_name({
            "source_id": shortcode,
            "caption": caption,
            "author": info.get("uploader") or info.get("channel"),
        })
        item = HarvestItem(
            source="instagram",
            source_id=shortcode,
            source_url=canonical_url,
            retrieved_at=datetime.now(timezone.utc),
            author=info.get("uploader") or info.get("channel"),
            caption=caption,
            title=title,
            creator=creator,
            source_metadata={
                "extractor": info.get("extractor"),
                "webpage_url": info.get("webpage_url"),
                "display_id": info.get("display_id"),
                "audio": audio_metadata_from_info(info),
            },
        )
        return _build_bundle(item, media_files, archive_root)


def _read_info(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return {}
    with paths[0].open(encoding="utf-8") as handle:
        return json.load(handle)


def audio_metadata_from_info(info: dict[str, Any]) -> dict[str, Any]:
    """Preserve platform-provided music attribution without guessing."""

    nested = info.get("music_metadata")
    music = nested if isinstance(nested, dict) else {}
    title = _first_text(info.get("track"), info.get("audio_title"), music.get("track"), music.get("title"))
    artist = _first_text(info.get("artist"), info.get("audio_artist"), music.get("artist"))
    label = _first_text(info.get("audio_label"), music.get("label"), title)
    original = bool(label and label.casefold().strip() in {"original audio", "original sound"})
    return {
        "label": label,
        "title": None if original else title,
        "artist": None if original else artist,
        "is_original": original,
    }


def _first_text(*values: Any) -> str | None:
    return next((value.strip() for value in values if isinstance(value, str) and value.strip()), None)


def _media_files(staging: Path) -> list[Path]:
    return sorted(
        path for path in staging.iterdir()
        if path.is_file() and not path.name.endswith(".info.json")
    )




def _build_bundle(item: HarvestItem, media_files: list[Path], archive_root: Path) -> Path:
    archive = Archive(archive_root)
    records: list[dict[str, Any]] = []
    inspected: list[tuple[Path, dict[str, Any], str]] = []
    for index, source in enumerate(media_files, start=1):
        original = archive.preserve_original(item, source, index, len(media_files))
        facts = probe(source)
        kind = _media_kind(facts)
        original["media_kind"] = kind
        original["probe"] = facts
        records.append(original)
        inspected.append((source, facts, kind))

    video_count = sum(kind == "video" for _, _, kind in inspected)
    image_count = sum(kind == "image" for _, _, kind in inspected)
    audible_count = sum(kind in {"video", "audio"} and has_audio(facts) for _, facts, kind in inspected)
    video_index = image_index = audio_index = 0
    for source, facts, kind in inspected:
        if kind == "video":
            video_index += 1
            name = archive.asset_relative_path(item, "video", source.suffix, video_index, video_count).as_posix()
            records.append(archive.copy_derivative(item, source, name, "video"))
        elif kind == "image":
            image_index += 1
            name = archive.asset_relative_path(item, "image", source.suffix, image_index, image_count).as_posix()
            records.append(archive.copy_derivative(item, source, name, "image"))

        if kind in {"video", "audio"} and has_audio(facts):
            audio_index += 1
            name = archive.asset_relative_path(item, "audio", ".wav", audio_index, audible_count).as_posix()
            destination = archive.item_directory(item) / name
            if not destination.exists():
                extract_wav(source, destination)
            wav_facts = probe(destination)
            record = archive.copy_derivative(item, destination, name, "audio")
            record["probe"] = wav_facts
            records.append(record)

    tools = {
        "yt-dlp": _tool_version("yt-dlp", "--version"),
        "ffmpeg": _tool_version("ffmpeg", "-version").splitlines()[0],
    }
    archive.write_metadata(item, records, tools)
    return archive.item_directory(item)


def _media_kind(facts: dict[str, Any]) -> str:
    stream_types = {stream.get("codec_type") for stream in facts.get("streams", [])}
    if "video" in stream_types:
        video_streams = [stream for stream in facts["streams"] if stream.get("codec_type") == "video"]
        if video_streams and all(stream.get("codec_name") in {"mjpeg", "png", "webp"} for stream in video_streams):
            return "image"
        return "video"
    if "audio" in stream_types:
        return "audio"
    return "unknown"


def _tool_version(program: str, argument: str) -> str:
    return subprocess.run([program, argument], check=True, capture_output=True, text=True).stdout.strip()
