"""Small, defensive Native Messaging boundary for the browser extension."""

from __future__ import annotations

import json
import os
import configparser
import re
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from . import __version__
from .audio import AUDIO_PRESETS, DEFAULT_AUDIO_PRESET

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024
SETTINGS_SCHEMA_VERSION = 1
MAX_DIAGNOSTIC_EVENTS = 100


@dataclass(frozen=True)
class ProtocolError(Exception):
    code: str
    message: str
    request_id: str | None = None


def read_message(stream: BinaryIO) -> dict[str, object] | None:
    """Read one Native Messaging frame, returning None on clean EOF."""
    header = stream.read(4)
    if header == b"":
        return None
    if len(header) != 4:
        raise ProtocolError("invalid_request", "Incomplete message header")
    length = struct.unpack("<I", header)[0]
    if length == 0 or length > MAX_MESSAGE_BYTES:
        raise ProtocolError("invalid_request", "Message size is outside the allowed range")
    body = stream.read(length)
    if len(body) != length:
        raise ProtocolError("invalid_request", "Incomplete message body")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProtocolError("invalid_request", "Message must be valid UTF-8 JSON") from None
    if not isinstance(value, dict):
        raise ProtocolError("invalid_request", "Message must be a JSON object")
    return value


def write_message(stream: BinaryIO, message: dict[str, object]) -> None:
    body = json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_MESSAGE_BYTES:
        raise ProtocolError("processing_failed", "Response exceeds the safe message size")
    stream.write(struct.pack("<I", len(body)))
    stream.write(body)
    stream.flush()


def _settings_path() -> Path:
    override = os.environ.get("HARVESTER_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "harvester" / "settings.json"


def _read_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "archive_root": None,
            "firefox_profile": None,
            "audio_preset": DEFAULT_AUDIO_PRESET,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ProtocolError("output_unavailable", "Local settings could not be read") from None
    if not isinstance(value, dict):
        raise ProtocolError("output_unavailable", "Local settings are invalid")
    return value


def _public_settings(settings: dict[str, object]) -> dict[str, object]:
    profile = settings.get("firefox_profile")
    if not isinstance(profile, str) or not (Path(profile).expanduser() / "cookies.sqlite").is_file():
        detected = _detect_firefox_profile()
        profile = str(detected) if detected else profile
    effective = {**settings, "firefox_profile": profile}
    return {
        "archive_root": settings.get("archive_root"),
        "firefox_profile": profile,
        "audio_preset": _audio_preset(settings),
        "configured": _settings_configured(effective),
    }


def _detect_firefox_profile() -> Path | None:
    firefox_root = Path.home() / "Library" / "Application Support" / "Firefox"
    profiles_file = firefox_root / "profiles.ini"
    parser = configparser.ConfigParser()
    try:
        if profiles_file.is_file():
            parser.read(profiles_file, encoding="utf-8")
            candidates: list[tuple[int, Path]] = []
            for section in parser.sections():
                if section.startswith("Install") and parser.has_option(section, "Default"):
                    raw = parser.get(section, "Default")
                    candidates.append((0, firefox_root / raw))
                    continue
                if not section.startswith("Profile") or not parser.has_option(section, "Path"):
                    continue
                raw = parser.get(section, "Path")
                candidate = Path(raw) if parser.get(section, "IsRelative", fallback="1") == "0" else firefox_root / raw
                priority = 1 if parser.get(section, "Default", fallback="0") == "1" else 2
                candidates.append((priority, candidate))
            for _, candidate in sorted(candidates, key=lambda value: value[0]):
                if (candidate / "cookies.sqlite").is_file():
                    return candidate.resolve()
    except (OSError, configparser.Error, ValueError):
        pass
    profiles_root = firefox_root / "Profiles"
    try:
        candidates = sorted(
            (path for path in profiles_root.iterdir() if (path / "cookies.sqlite").is_file()),
            key=lambda path: ("default-release" not in path.name, path.name),
        )
    except OSError:
        return None
    return candidates[0].resolve() if candidates else None


def _update_settings(path: Path, payload: dict[str, object], request_id: str) -> dict[str, object]:
    if set(payload) not in (
        {"archive_root", "firefox_profile"},
        {"archive_root", "firefox_profile", "audio_preset"},
    ):
        raise ProtocolError(
            "invalid_request",
            "update_settings requires output and Firefox profile paths",
            request_id,
        )
    archive_value = payload.get("archive_root")
    profile_value = payload.get("firefox_profile")
    audio_preset = payload.get("audio_preset", DEFAULT_AUDIO_PRESET)
    if not all(isinstance(value, str) and value.strip() and len(value) <= 4096 for value in (archive_value, profile_value)):
        raise ProtocolError("invalid_request", "Settings paths must be non-empty strings", request_id)
    if not isinstance(audio_preset, str) or audio_preset not in AUDIO_PRESETS:
        raise ProtocolError("invalid_request", "Choose a supported audio preset", request_id)
    archive_root = Path(archive_value).expanduser().resolve()
    firefox_profile = Path(profile_value).expanduser().resolve()
    if not archive_root.is_dir():
        raise ProtocolError("output_unavailable", "The output folder does not exist", request_id)
    if not (firefox_profile / "cookies.sqlite").is_file():
        raise ProtocolError("output_unavailable", "The folder is not a Firefox profile", request_id)
    settings = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "archive_root": str(archive_root),
        "firefox_profile": str(firefox_profile),
        "audio_preset": audio_preset,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return _public_settings(settings)


def _configured_path(settings: dict[str, object], key: str, request_id: str) -> Path:
    value = settings.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("output_unavailable", "Configure the local companion before harvesting", request_id)
    return Path(value).expanduser()


def _audio_preset(settings: dict[str, object]) -> str:
    value = settings.get("audio_preset", DEFAULT_AUDIO_PRESET)
    return value if isinstance(value, str) and value in AUDIO_PRESETS else DEFAULT_AUDIO_PRESET


def _archival_root() -> Path:
    override = os.environ.get("HARVESTER_STATE_ROOT")
    return Path(override).expanduser() if override else Path(__file__).resolve().parents[2] / "state"


def _archival_paths(archive_id: str | None = None) -> dict[str, Path]:
    root = _archival_root()
    if archive_id is not None:
        from .archive_sources import state_directory
        root = state_directory(root, archive_id)
    return {
        "root": root,
        "index": root / "saved-index.json",
        "partial": root / "saved-sync-partial.json",
        "ledger": root / "item-ledger.json",
        "manual_review": root / "manual-review.json",
        "batches": root / "batches",
    }


def _archive_list() -> dict[str, object]:
    from .archive_sources import public_archives
    return {"archives": public_archives(_archival_root())}


def _single_archive_id(request_id: str) -> str:
    from .archive_sources import public_archives
    archives = public_archives(_archival_root())
    if len(archives) != 1:
        raise ProtocolError("invalid_request", "Choose an archive in Harvester 1.0.2", request_id)
    return archives[0]["id"]


def _save_archive_source(payload: dict[str, object], request_id: str) -> dict[str, object]:
    if set(payload) not in ({"name", "source_url"}, {"archive_id", "name", "source_url"}):
        raise ProtocolError("invalid_request", "Archive name and Instagram URL are required", request_id)
    if not isinstance(payload.get("name"), str) or not isinstance(payload.get("source_url"), str):
        raise ProtocolError("invalid_request", "Archive name and Instagram URL must be text", request_id)
    archive_id = payload.get("archive_id")
    if archive_id is not None and not isinstance(archive_id, str):
        raise ProtocolError("invalid_request", "Archive ID is invalid", request_id)
    from .archive_sources import ArchiveSourceError, save_archive
    try:
        return save_archive(_archival_root(), payload["name"], payload["source_url"], archive_id)
    except ArchiveSourceError as error:
        raise ProtocolError("invalid_archive_source", str(error), request_id) from None


def _rename_archive_source(payload: dict[str, object], request_id: str) -> dict[str, object]:
    if set(payload) != {"archive_id", "name"} or not all(isinstance(payload.get(key), str) for key in payload):
        raise ProtocolError("invalid_request", "Archive ID and name are required", request_id)
    from .archive_sources import ArchiveSourceError, rename_archive
    try:
        return rename_archive(_archival_root(), payload["archive_id"], payload["name"])
    except ArchiveSourceError as error:
        raise ProtocolError("invalid_archive_source", str(error), request_id) from None


def _remove_archive_source(payload: dict[str, object], request_id: str) -> dict[str, object]:
    if set(payload) != {"archive_id"} or not isinstance(payload.get("archive_id"), str):
        raise ProtocolError("invalid_request", "Archive ID is required", request_id)
    from .archive_sources import ArchiveSourceError, remove_archive
    try:
        return remove_archive(_archival_root(), payload["archive_id"])
    except ArchiveSourceError as error:
        raise ProtocolError("invalid_archive_source", str(error), request_id) from None


def _archive_scan_context(archive_id: str, request_id: str) -> dict[str, object]:
    from .archive_sources import ArchiveSourceError, get_archive
    try:
        archive = get_archive(_archival_root(), archive_id)
    except ArchiveSourceError as error:
        raise ProtocolError("invalid_archive_source", str(error), request_id) from None
    if not archive.get("source_url"):
        raise ProtocolError("invalid_archive_source", "Add this archive's Instagram URL before scanning", request_id)
    paths = _archival_paths(archive_id)
    known: list[str] = []
    if paths["index"].is_file():
        try:
            value = json.loads(paths["index"].read_text(encoding="utf-8"))
            known = [item["source_id"] for item in value.get("items", []) if isinstance(item, dict) and isinstance(item.get("source_id"), str)]
        except (OSError, json.JSONDecodeError, TypeError):
            raise ProtocolError("archival_state_unavailable", "Archive queue could not be read", request_id) from None
    return {"archive": dict(archive), "known_source_ids": known[-5000:]}


def _sync_archive_items(payload: dict[str, object], request_id: str, settings_path: Path) -> dict[str, object]:
    if set(payload) != {"archive_id", "items"} or not isinstance(payload.get("archive_id"), str) or not isinstance(payload.get("items"), list):
        raise ProtocolError("invalid_request", "Archive ID and scanned posts are required", request_id)
    if len(payload["items"]) > 5000:
        raise ProtocolError("invalid_request", "Saved-page scan exceeds the supported limit", request_id)
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    paths = _archival_paths(payload["archive_id"])
    from .saved import SavedEnumerationError, sync_supplied_saved_items
    from .ledger import sync_item_ledger
    try:
        result = sync_supplied_saved_items(payload["items"], paths["index"], 5)
        ledger = sync_item_ledger(paths["index"], paths["ledger"], archive_root, paths["manual_review"])
    except SavedEnumerationError as error:
        raise ProtocolError("scan_failed", str(error), request_id) from None
    except ValueError:
        raise ProtocolError("scan_failed", "Saved-page scan returned invalid state", request_id) from None
    return {"state": "complete", "scan": result["scan"], "summary": ledger["summary"]}


def _sync_all_archive_ledgers(archive_root: Path) -> None:
    from .archive_sources import public_archives, state_directory
    from .ledger import sync_item_ledger
    for archive in public_archives(_archival_root()):
        state_root = state_directory(_archival_root(), archive["id"])
        index_path = state_root / "saved-index.json"
        if index_path.is_file():
            sync_item_ledger(
                index_path, state_root / "item-ledger.json", archive_root,
                state_root / "manual-review.json",
            )


def _archival_status(settings_path: Path, archive_id: str) -> dict[str, object]:
    paths = _archival_paths(archive_id)
    settings = _read_settings(settings_path)
    index: dict[str, object] = {}
    ledger: dict[str, object] = {}
    try:
        if paths["index"].is_file():
            value = json.loads(paths["index"].read_text(encoding="utf-8"))
            index = value if isinstance(value, dict) else {}
        if paths["ledger"].is_file():
            value = json.loads(paths["ledger"].read_text(encoding="utf-8"))
            ledger = value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        raise ProtocolError("archival_state_unavailable", "Archival state could not be read") from None
    summary = ledger.get("summary") if isinstance(ledger.get("summary"), dict) else {}
    scan = index.get("last_incremental_sync") if isinstance(index.get("last_incremental_sync"), dict) else {}
    batch_progress: dict[str, object] | None = None
    try:
        batch_files = sorted(paths["batches"].glob("*-oldest-*.json")) if paths["batches"].is_dir() else []
        if batch_files:
            latest = json.loads(batch_files[-1].read_text(encoding="utf-8"))
            items = latest.get("items", []) if isinstance(latest, dict) else []
            if isinstance(items, list):
                statuses = [item.get("status") for item in items if isinstance(item, dict)]
                batch_progress = {
                    "count": len(statuses),
                    "complete": statuses.count("complete"),
                    "failed": statuses.count("failed"),
                    "running": statuses.count("running"),
                    "pending": statuses.count("pending"),
                    "batch_path": str(batch_files[-1]),
                }
    except (OSError, json.JSONDecodeError):
        batch_progress = None
    return {
        "available": bool(index.get("complete")),
        "configured": _settings_configured(settings),
        "indexed": index.get("count", 0),
        "summary": summary,
        "last_scan_at": index.get("last_incremental_sync_at") or index.get("enumerated_at"),
        "last_scan": scan,
        "latest_batch": batch_progress,
    }


def _latest_batch_review(request_id: str, settings_path: Path, archive_id: str) -> dict[str, object]:
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    paths = _archival_paths(archive_id)
    batches = sorted(paths["batches"].glob("*-oldest-*.json")) if paths["batches"].is_dir() else []
    if not batches:
        return {"summary": {"items": 0, "present": 0, "deleted": 0, "failed": 0}, "items": []}
    from .review import build_batch_review
    review = build_batch_review(batches[-1], archive_root, paths["ledger"])
    review.pop("batch", None)
    for item in review["items"]:
        item.pop("source_url", None)
    return review


def _archival_bundle(source_id: str, request_id: str, settings_path: Path, archive_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id):
        raise ProtocolError("invalid_request", "Invalid archival item", request_id)
    paths = _archival_paths(archive_id)
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id).resolve()
    try:
        ledger = json.loads(paths["ledger"].read_text(encoding="utf-8"))
        record = ledger["items"][f"instagram:{source_id}"]
        bundle = Path(record["archive_directory"]).resolve()
        metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))["item"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise ProtocolError("archive_unavailable", "Archived item is unavailable", request_id) from None
    if bundle.parent != archive_root or (metadata.get("source"), metadata.get("source_id")) != ("instagram", source_id):
        raise ProtocolError("archive_unavailable", "Archived item could not be verified", request_id)
    return bundle


def _reveal_archival_item(source_id: str, request_id: str, settings_path: Path, archive_id: str) -> dict[str, object]:
    bundle = _archival_bundle(source_id, request_id, settings_path, archive_id)
    try:
        subprocess.run(["open", "-R", str(bundle)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        raise ProtocolError("output_unavailable", "Archived item could not be revealed", request_id) from None
    return {"state": "revealed"}


def _delete_archival_item(source_id: str, request_id: str, settings_path: Path, archive_id: str) -> dict[str, object]:
    _archival_bundle(source_id, request_id, settings_path, archive_id)
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    paths = _archival_paths(archive_id)
    from .deletion import ArchiveDeletionError, delete_archive_item
    try:
        result = delete_archive_item(paths["ledger"], archive_root, Path.home() / ".Trash", source_id)
    except ArchiveDeletionError:
        raise ProtocolError("deletion_failed", "Archived item could not be moved to Trash", request_id) from None
    from .archive_sources import public_archives, state_directory
    from .ledger import identity_key, set_item_status
    for archive in public_archives(_archival_root()):
        if archive.get("id") == archive_id:
            continue
        other_root = state_directory(_archival_root(), archive["id"])
        other_ledger = other_root / "item-ledger.json"
        try:
            value = json.loads(other_ledger.read_text(encoding="utf-8"))
            if identity_key("instagram", source_id) in value.get("items", {}):
                set_item_status(other_ledger, "instagram", source_id, "retired-deleted", "User removed from archive")
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return {"state": "deleted", "source_id": result["source_id"]}


def _rename_archival_item(source_id: str, title: str, request_id: str, settings_path: Path, archive_id: str) -> dict[str, object]:
    _archival_bundle(source_id, request_id, settings_path, archive_id)
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    paths = _archival_paths(archive_id)
    from .deletion import ArchiveDeletionError, rename_archive_item
    from .archive_sources import public_archives, state_directory
    related = [
        state_directory(_archival_root(), archive["id"])
        for archive in public_archives(_archival_root()) if archive.get("id") != archive_id
    ]
    try:
        result = rename_archive_item(
            paths["ledger"], paths["index"], paths["batches"], archive_root, source_id, title,
            related_state_roots=related,
        )
    except ArchiveDeletionError as error:
        raise ProtocolError("rename_failed", str(error), request_id) from None
    except Exception:
        raise ProtocolError("rename_failed", "Archived item could not be renamed safely", request_id) from None
    return {"state": "renamed", "source_id": result["source_id"], "title": result["title"]}


def _scan_saved(request_id: str, settings_path: Path, archive_id: str) -> dict[str, object]:
    settings = _read_settings(settings_path)
    profile = _configured_path(settings, "firefox_profile", request_id)
    archive_root = _configured_path(settings, "archive_root", request_id)
    paths = _archival_paths(archive_id)
    from .ledger import sync_item_ledger
    from .saved import SavedEnumerationError, sync_saved_incremental, enumerate_saved
    try:
        if paths["index"].is_file():
            result = sync_saved_incremental(profile, paths["index"], paths["partial"], 5)
            scan = result["scan"]
        else:
            index = enumerate_saved(profile, paths["index"])
            scan = {
                "boundary": "initial-enumeration",
                "known_streak_required": 5,
                "known_streak_reached": 0,
                "scanned_count": index["count"],
                "new_count": index["count"],
            }
        ledger = sync_item_ledger(
            paths["index"], paths["ledger"], archive_root, paths["manual_review"]
        )
    except (ValueError, SavedEnumerationError) as error:
        message = str(error).casefold()
        code = "authentication_stop" if any(term in message for term in ("session", "authentication", "rate-limit")) else "scan_failed"
        safe = "Instagram authorization stopped the scan" if code == "authentication_stop" else "Saved-post scan failed safely"
        raise ProtocolError(code, safe, request_id) from None
    except Exception:
        raise ProtocolError("scan_failed", "Saved-post scan failed safely", request_id) from None
    return {"state": "complete", "scan": scan, "summary": ledger["summary"]}


def _harvest_archival_batch(
    payload: dict[str, object], request_id: str, settings_path: Path
) -> dict[str, object]:
    if set(payload) != {"archive_id", "count", "min_delay", "max_delay"} or not isinstance(payload.get("archive_id"), str):
        raise ProtocolError("invalid_request", "Archival batch requires count and delay range", request_id)
    count, minimum, maximum = payload.get("count"), payload.get("min_delay"), payload.get("max_delay")
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 25:
        raise ProtocolError("invalid_request", "Batch size must be from 1 through 25", request_id)
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in (minimum, maximum)):
        raise ProtocolError("invalid_request", "Batch delays must be numbers", request_id)
    minimum, maximum = float(minimum), float(maximum)
    if not 10 <= minimum <= maximum <= 300:
        raise ProtocolError("invalid_request", "Batch delays must satisfy 10 <= minimum <= maximum <= 300", request_id)

    settings = _read_settings(settings_path)
    profile = _configured_path(settings, "firefox_profile", request_id)
    archive_root = _configured_path(settings, "archive_root", request_id)
    paths = _archival_paths(payload["archive_id"])
    if not paths["index"].is_file() or not paths["ledger"].is_file():
        raise ProtocolError("archival_state_unavailable", "Scan saved posts before harvesting a batch", request_id)
    from .batch import BatchError, harvest_oldest, new_batch_path
    from .ledger import sync_item_ledger
    batch_path = new_batch_path(paths["batches"], count)
    try:
        # Refresh every configured queue against the shared output directory so
        # a post acquired through one collection is not downloaded again through another.
        _sync_all_archive_ledgers(archive_root)
        try:
            batch = harvest_oldest(
                paths["index"], batch_path, profile, archive_root, count,
                minimum, maximum, paths["ledger"], paths["manual_review"],
                _audio_preset(settings),
            )
        finally:
            if batch_path.is_file():
                _sync_all_archive_ledgers(archive_root)
                ledger = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    except BatchError as error:
        message = str(error).casefold()
        code = "authentication_stop" if "authentication" in message or "rate-limit" in message else "batch_failed"
        safe = "Instagram authorization stopped the batch" if code == "authentication_stop" else "Archival batch failed safely"
        raise ProtocolError(code, safe, request_id) from None
    except Exception:
        raise ProtocolError("batch_failed", "Archival batch failed safely", request_id) from None
    complete = sum(item.get("status") == "complete" for item in batch["items"])
    failed = sum(item.get("status") == "failed" for item in batch["items"])
    return {
        "state": "complete", "complete": complete, "failed": failed,
        "batch_path": str(batch_path), "summary": ledger["summary"],
    }


def _settings_configured(settings: dict[str, object]) -> bool:
    archive_value = settings.get("archive_root")
    profile_value = settings.get("firefox_profile")
    if not isinstance(archive_value, str) or not isinstance(profile_value, str):
        return False
    return Path(archive_value).expanduser().is_dir() and (
        Path(profile_value).expanduser() / "cookies.sqlite"
    ).is_file()


def _harvest_url(payload: dict[str, object], request_id: str, settings_path: Path) -> dict[str, object]:
    if set(payload) != {"url"}:
        raise ProtocolError("invalid_request", "harvest_url requires only a URL", request_id)
    url = payload.get("url")
    if not isinstance(url, str) or len(url) > 4096:
        raise ProtocolError("invalid_url", "URL must be a short HTTP(S) string", request_id)
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise ProtocolError("invalid_url", "URL is invalid", request_id) from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProtocolError("invalid_url", "Only HTTP(S) URLs are accepted", request_id)
    hostname = parsed.hostname.casefold()
    from .instagram import POST_URL
    from .reddit import POST_URL as REDDIT_POST_URL
    from .youtube import WATCH_URL
    if hostname in {"instagram.com", "www.instagram.com"}:
        source = "instagram"
        if not POST_URL.fullmatch(url):
            raise ProtocolError("invalid_url", "Use one canonical Instagram post or reel URL", request_id)
    elif hostname in {"youtube.com", "www.youtube.com"}:
        source = "youtube"
        if not WATCH_URL.fullmatch(url):
            raise ProtocolError("invalid_url", "Use one canonical YouTube watch URL", request_id)
    elif hostname == "www.reddit.com":
        source = "reddit"
        if not REDDIT_POST_URL.fullmatch(url):
            raise ProtocolError("invalid_url", "Use one canonical Reddit post URL", request_id)
    else:
        raise ProtocolError("unsupported_source", "This source is not supported yet", request_id)

    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    firefox_profile = _configured_path(settings, "firefox_profile", request_id)
    audio_preset = _audio_preset(settings)
    if not archive_root.is_dir():
        raise ProtocolError("output_unavailable", "The configured output folder is unavailable", request_id)
    if not (firefox_profile / "cookies.sqlite").is_file():
        raise ProtocolError("output_unavailable", "The configured Firefox profile is unavailable", request_id)

    try:
        if source == "instagram":
            from .instagram import harvest_instagram_url
            destination = harvest_instagram_url(
                url, firefox_profile, archive_root, audio_preset=audio_preset
            )
        elif source == "youtube":
            from .youtube import harvest_youtube_url
            destination = harvest_youtube_url(url, firefox_profile, archive_root, audio_preset)
        else:
            from .reddit import harvest_reddit_url
            destination = harvest_reddit_url(url, firefox_profile, archive_root, audio_preset)
    except ValueError:
        raise ProtocolError("invalid_url", f"Use one canonical {source.title()} URL", request_id) from None
    except Exception as error:
        from .instagram import AcquisitionError
        from .reddit import RedditAcquisitionError
        from .youtube import YouTubeAcquisitionError
        if not isinstance(error, (AcquisitionError, RedditAcquisitionError, YouTubeAcquisitionError)):
            raise ProtocolError("processing_failed", "Harvest processing failed safely", request_id) from None
        message = str(error).casefold()
        code = "authentication_stop" if "authentication" in message or "rate-limit" in message else "acquisition_failed"
        safe_message = f"{source.title()} authorization stopped the harvest" if code == "authentication_stop" else f"{source.title()} acquisition failed"
        raise ProtocolError(code, safe_message, request_id) from None
    return {"state": "complete", "source": source, "output_path": str(destination)}


def _open_output_folder(request_id: str, settings_path: Path) -> dict[str, object]:
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    if not archive_root.is_dir():
        raise ProtocolError("output_unavailable", "The configured output folder is unavailable", request_id)
    try:
        subprocess.run(["open", str(archive_root)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        raise ProtocolError("output_unavailable", "The output folder could not be opened", request_id) from None
    return {"state": "opened"}


def _open_failure_log(request_id: str, archive_id: str) -> dict[str, object]:
    paths = _archival_paths(archive_id)
    failure_log = paths["manual_review"]
    readable_log = paths["root"] / "failure-log.txt"
    if not failure_log.is_file():
        raise ProtocolError("output_unavailable", "No archival failures have been recorded", request_id)
    try:
        payload = json.loads(failure_log.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError("invalid failure log")
        lines = ["Harvester archival failure log", "", f"Items requiring manual review: {len(items)}", ""]
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            clean = lambda value: " ".join(str(value or "Unavailable").splitlines())
            lines.extend([
                f"{index}. {clean(item.get('source_id'))}",
                f"   Source: {clean(item.get('source'))}",
                f"   Status: {clean(item.get('status'))}",
                f"   Reason: {clean(item.get('reason'))}",
                f"   Recorded: {clean(item.get('recorded_at'))}",
                f"   URL: {clean(item.get('source_url'))}",
                "",
            ])
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".failure-log-", suffix=".tmp", dir=paths["root"]
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, readable_log)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        subprocess.run(["open", str(readable_log)], check=True, capture_output=True)
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError, subprocess.CalledProcessError):
        raise ProtocolError("output_unavailable", "The failure log could not be opened", request_id) from None
    return {"state": "opened"}


def _record_diagnostic(error: ProtocolError, command: object = None) -> None:
    """Persist one bounded, sanitized native failure without request payload data."""
    paths = _archival_paths()
    destination = paths["root"] / "diagnostics.json"
    paths["root"].mkdir(parents=True, exist_ok=True)
    events: list[dict[str, str]] = []
    try:
        if destination.is_file():
            existing = json.loads(destination.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("events"), list):
                events = [event for event in existing["events"] if isinstance(event, dict)]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        events = []
    operation = command if isinstance(command, str) and len(command) <= 80 else "unknown"
    events.append({
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "code": error.code[:80],
        "message": " ".join(error.message.splitlines())[:500],
        "application_version": __version__,
    })
    payload = {"schema_version": 1, "events": events[-MAX_DIAGNOSTIC_EVENTS:]}
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".diagnostics-", suffix=".tmp", dir=paths["root"]
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _open_diagnostics(request_id: str) -> dict[str, object]:
    paths = _archival_paths()
    structured_log = paths["root"] / "diagnostics.json"
    readable_log = paths["root"] / "diagnostics.txt"
    if not structured_log.is_file():
        raise ProtocolError("output_unavailable", "No diagnostics have been recorded", request_id)
    try:
        payload = json.loads(structured_log.read_text(encoding="utf-8"))
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            raise ValueError("invalid diagnostics")
        lines = ["Harvester diagnostics", "", f"Most recent events retained: {len(events)}", ""]
        for index, event in enumerate(events, start=1):
            if not isinstance(event, dict):
                continue
            clean = lambda value: " ".join(str(value or "Unavailable").splitlines())
            lines.extend([
                f"{index}. {clean(event.get('recorded_at'))}",
                f"   Operation: {clean(event.get('operation'))}",
                f"   Error: {clean(event.get('code'))}",
                f"   Detail: {clean(event.get('message'))}",
                f"   Harvester: {clean(event.get('application_version'))}",
                "",
            ])
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".diagnostics-", suffix=".tmp", dir=paths["root"]
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, readable_log)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        subprocess.run(["open", str(readable_log)], check=True, capture_output=True)
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError, subprocess.CalledProcessError):
        raise ProtocolError("output_unavailable", "Diagnostics could not be opened", request_id) from None
    return {"state": "opened"}


def _get_diagnostics() -> dict[str, object]:
    """Return only the already-sanitized diagnostic fields for user review."""
    structured_log = _archival_paths()["root"] / "diagnostics.json"
    if not structured_log.is_file():
        return {"events": []}
    try:
        payload = json.loads(structured_log.read_text(encoding="utf-8"))
        events = payload.get("events") if isinstance(payload, dict) else []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"events": []}
    safe: list[dict[str, str]] = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        safe.append({
            key: " ".join(str(event.get(key) or "Unavailable").splitlines())[:500]
            for key in ("recorded_at", "operation", "code", "message", "application_version")
        })
    return {"events": safe[-MAX_DIAGNOSTIC_EVENTS:]}


def _choose_output_folder(request_id: str) -> dict[str, object]:
    script = 'POSIX path of (choose folder with prompt "Choose Harvester output folder")'
    try:
        completed = subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, text=True
        )
    except OSError:
        raise ProtocolError("output_unavailable", "The folder picker could not open", request_id) from None
    if completed.returncode != 0:
        if "cancel" in completed.stderr.casefold():
            return {"selected": False}
        raise ProtocolError("output_unavailable", "The folder picker could not open", request_id)
    selected = Path(completed.stdout.strip()).expanduser()
    if not selected.is_dir():
        raise ProtocolError("output_unavailable", "The selected output folder is unavailable", request_id)
    return {"selected": True, "path": str(selected.resolve())}


def _harvest_local_file(request_id: str, settings_path: Path) -> dict[str, object]:
    script = 'POSIX path of (choose file with prompt "Choose one media file to harvest")'
    try:
        completed = subprocess.run(
            ["osascript", "-e", script], check=False, capture_output=True, text=True
        )
    except OSError:
        raise ProtocolError("invalid_file", "The file picker could not open", request_id) from None
    if completed.returncode != 0:
        if "cancel" in completed.stderr.casefold():
            return {"state": "cancelled"}
        raise ProtocolError("invalid_file", "The file picker could not open", request_id)
    selected = Path(completed.stdout.strip()).expanduser()
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    from .local_file import LocalFileError, harvest_local_file
    try:
        destination = harvest_local_file(selected, archive_root, _audio_preset(settings))
    except LocalFileError as error:
        raise ProtocolError(error.code, error.message, request_id) from None
    except Exception:
        raise ProtocolError("processing_failed", "Local file processing failed safely", request_id) from None
    return {"state": "complete", "source": "local", "output_path": str(destination)}


def _harvest_media_url(payload: dict[str, object], request_id: str, settings_path: Path) -> dict[str, object]:
    if set(payload) != {"media_url", "page_url"}:
        raise ProtocolError("invalid_request", "harvest_media_url requires one media and page URL", request_id)
    media_url = payload.get("media_url")
    page_url = payload.get("page_url")
    if isinstance(media_url, str) and media_url.startswith("blob:"):
        raise ProtocolError("unsupported_media", "Blob and Media Source media are unsupported", request_id)
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    audio_preset = _audio_preset(settings)
    if not archive_root.is_dir():
        raise ProtocolError("output_unavailable", "The configured output folder is unavailable", request_id)
    from .generic import GenericMediaError, harvest_selected_media

    try:
        destination = harvest_selected_media(
            media_url, page_url, archive_root, audio_preset=audio_preset
        )
    except GenericMediaError as error:
        raise ProtocolError(error.code, error.message, request_id) from None
    except Exception:
        raise ProtocolError("processing_failed", "Selected media processing failed safely", request_id) from None
    return {"state": "complete", "source": "generic", "output_path": str(destination)}


def handle_message(
    message: dict[str, object], *, settings_path: Path | None = None
) -> dict[str, object]:
    request_id = message.get("request_id")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ProtocolError("invalid_request", "request_id must be a short non-empty string")
    if message.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("invalid_request", "Unsupported protocol version", request_id)
    command = message.get("command")
    if not isinstance(command, str):
        raise ProtocolError("invalid_request", "command must be a string", request_id)
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_request", "payload must be an object", request_id)

    if command == "get_status":
        if payload:
            raise ProtocolError("invalid_request", "get_status payload must be empty", request_id)
        settings = _read_settings(settings_path or _settings_path())
        configured = bool(_public_settings(settings)["configured"])
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": {
                "state": "ready",
                "application": "harvester",
                "application_version": __version__,
                "configured": configured,
            },
        }
    if command == "get_settings":
        if payload:
            raise ProtocolError("invalid_request", "get_settings payload must be empty", request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": _public_settings(_read_settings(settings_path or _settings_path())),
        }
    if command == "update_settings":
        result = _update_settings(settings_path or _settings_path(), payload, request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    if command == "choose_output_folder":
        if payload:
            raise ProtocolError("invalid_request", "choose_output_folder payload must be empty", request_id)
        result = _choose_output_folder(request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    if command == "list_archives":
        if payload:
            raise ProtocolError("invalid_request", "list_archives payload must be empty", request_id)
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True, "result": _archive_list()}
    if command == "save_archive_source":
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True,
                "result": _save_archive_source(payload, request_id)}
    if command == "rename_archive_source":
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True,
                "result": _rename_archive_source(payload, request_id)}
    if command == "remove_archive_source":
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True,
                "result": _remove_archive_source(payload, request_id)}
    if command == "get_archive_scan_context":
        if set(payload) != {"archive_id"} or not isinstance(payload.get("archive_id"), str):
            raise ProtocolError("invalid_request", "Archive ID is required", request_id)
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True,
                "result": _archive_scan_context(payload["archive_id"], request_id)}
    if command == "sync_archive_items":
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True,
                "result": _sync_archive_items(payload, request_id, settings_path or _settings_path())}
    if command == "get_archival_status":
        if payload == {}:
            payload = {"archive_id": _single_archive_id(request_id)}
        if set(payload) != {"archive_id"} or not isinstance(payload.get("archive_id"), str):
            raise ProtocolError("invalid_request", "Archive ID is required", request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": _archival_status(settings_path or _settings_path(), payload["archive_id"]),
        }
    if command == "get_latest_batch_review":
        if payload == {}:
            payload = {"archive_id": _single_archive_id(request_id)}
        if set(payload) != {"archive_id"} or not isinstance(payload.get("archive_id"), str):
            raise ProtocolError("invalid_request", "Archive ID is required", request_id)
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True,
                "result": _latest_batch_review(request_id, settings_path or _settings_path(), payload["archive_id"])}
    if command in {"reveal_archival_item", "delete_archival_item"}:
        if set(payload) == {"source_id"}:
            payload = {**payload, "archive_id": _single_archive_id(request_id)}
        if set(payload) != {"archive_id", "source_id"} or not all(isinstance(payload.get(key), str) for key in payload):
            raise ProtocolError("invalid_request", "One archival source ID is required", request_id)
        result = (_reveal_archival_item if command == "reveal_archival_item" else _delete_archival_item)(
            payload["source_id"], request_id, settings_path or _settings_path(), payload["archive_id"]
        )
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True, "result": result}
    if command == "rename_archival_item":
        if set(payload) == {"source_id", "title"}:
            payload = {**payload, "archive_id": _single_archive_id(request_id)}
        if set(payload) != {"archive_id", "source_id", "title"} or not all(isinstance(payload.get(key), str) for key in payload):
            raise ProtocolError("invalid_request", "One archival source ID and title are required", request_id)
        result = _rename_archival_item(payload["source_id"], payload["title"], request_id, settings_path or _settings_path(), payload["archive_id"])
        return {"version": PROTOCOL_VERSION, "request_id": request_id, "ok": True, "result": result}
    if command == "scan_saved_posts":
        if payload == {}:
            payload = {"archive_id": _single_archive_id(request_id)}
        if set(payload) != {"archive_id"} or not isinstance(payload.get("archive_id"), str):
            raise ProtocolError("invalid_request", "Archive ID is required", request_id)
        result = _scan_saved(request_id, settings_path or _settings_path(), payload["archive_id"])
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    if command == "harvest_archival_batch":
        if set(payload) == {"count", "min_delay", "max_delay"}:
            payload = {**payload, "archive_id": _single_archive_id(request_id)}
        result = _harvest_archival_batch(payload, request_id, settings_path or _settings_path())
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    if command == "harvest_local_file":
        if payload:
            raise ProtocolError("invalid_request", "harvest_local_file payload must be empty", request_id)
        result = _harvest_local_file(request_id, settings_path or _settings_path())
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    if command == "open_output_folder":
        if payload:
            raise ProtocolError("invalid_request", "open_output_folder payload must be empty", request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": _open_output_folder(request_id, settings_path or _settings_path()),
        }
    if command == "open_failure_log":
        if payload == {}:
            payload = {"archive_id": _single_archive_id(request_id)}
        if set(payload) != {"archive_id"} or not isinstance(payload.get("archive_id"), str):
            raise ProtocolError("invalid_request", "Archive ID is required", request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": _open_failure_log(request_id, payload["archive_id"]),
        }
    if command == "open_diagnostics":
        if payload:
            raise ProtocolError("invalid_request", "open_diagnostics payload must be empty", request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": _open_diagnostics(request_id),
        }
    if command == "get_diagnostics":
        if payload:
            raise ProtocolError("invalid_request", "get_diagnostics payload must be empty", request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": _get_diagnostics(),
        }
    if command == "harvest_media_url":
        result = _harvest_media_url(payload, request_id, settings_path or _settings_path())
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    if command == "harvest_url":
        result = _harvest_url(payload, request_id, settings_path or _settings_path())
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    raise ProtocolError("unsupported_command", "Command is not implemented", request_id)


def error_response(error: ProtocolError) -> dict[str, object]:
    return {
        "version": PROTOCOL_VERSION,
        "request_id": error.request_id,
        "ok": False,
        "error": {"code": error.code, "message": error.message},
    }


def main() -> int:
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    while True:
        message: dict[str, object] | None = None
        try:
            message = read_message(input_stream)
            if message is None:
                return 0
            response = handle_message(message)
        except ProtocolError as error:
            try:
                _record_diagnostic(error, message.get("command") if isinstance(message, dict) else None)
            except Exception:
                pass
            response = error_response(error)
        except Exception:
            # Native stdout is protocol-only. Never expose paths, commands,
            # downloader output, or exception details to the extension.
            error = ProtocolError("processing_failed", "Native companion failed safely")
            try:
                _record_diagnostic(error, message.get("command") if isinstance(message, dict) else None)
            except Exception:
                pass
            response = error_response(error)
        write_message(output_stream, response)


if __name__ == "__main__":
    raise SystemExit(main())
