from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class ArchiveSourceError(ValueError):
    pass


def normalize_instagram_saved_url(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 4096:
        raise ArchiveSourceError("Enter an Instagram Saved-page URL")
    try:
        parsed = urlsplit(raw.strip())
    except ValueError:
        raise ArchiveSourceError("Enter a valid Instagram Saved-page URL") from None
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or hostname not in {"instagram.com", "www.instagram.com"}:
        raise ArchiveSourceError("Archive URLs must be HTTPS Instagram pages")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if "saved" not in [segment.casefold() for segment in segments]:
        raise ArchiveSourceError("Choose an Instagram Saved page or Saved collection")
    path = "/" + "/".join(segments) + "/"
    return urlunsplit(("https", "www.instagram.com", path, "", ""))


def read_registry(root: Path) -> dict[str, Any]:
    path = root / "archives.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise ArchiveSourceError("Archive list could not be read") from None
        if not isinstance(value, dict) or not isinstance(value.get("archives"), list):
            raise ArchiveSourceError("Archive list is invalid")
        return value
    return {"schema_version": 1, "archives": []}


def write_registry(root: Path, registry: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "archives.json"
    descriptor, temporary = tempfile.mkstemp(prefix=".archives-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(registry, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def public_archives(root: Path) -> list[dict[str, Any]]:
    return [dict(item) for item in read_registry(root)["archives"]]


def get_archive(root: Path, archive_id: str) -> dict[str, Any]:
    if not isinstance(archive_id, str):
        raise ArchiveSourceError("Choose an archive")
    for archive in read_registry(root)["archives"]:
        if archive.get("id") == archive_id:
            return archive
    raise ArchiveSourceError("Archive was not found")


def save_archive(root: Path, name: str, source_url: str, archive_id: str | None = None) -> dict[str, Any]:
    clean_url = normalize_instagram_saved_url(source_url)
    clean_name = _name(name)
    registry = read_registry(root)
    if any(item.get("source_url") == clean_url and item.get("id") != archive_id for item in registry["archives"]):
        raise ArchiveSourceError("That Instagram archive has already been added")
    if archive_id is None:
        archive = {
            "id": uuid.uuid4().hex,
            "name": clean_name or f"Instagram archive {len(registry['archives']) + 1}",
            "source_url": clean_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        registry["archives"].append(archive)
    else:
        archive = next((item for item in registry["archives"] if item.get("id") == archive_id), None)
        if archive is None:
            raise ArchiveSourceError("Archive was not found")
        archive["name"] = clean_name or archive["name"]
        archive["source_url"] = clean_url
    write_registry(root, registry)
    return dict(archive)


def rename_archive(root: Path, archive_id: str, name: str) -> dict[str, Any]:
    registry = read_registry(root)
    archive = next((item for item in registry["archives"] if item.get("id") == archive_id), None)
    if archive is None:
        raise ArchiveSourceError("Archive was not found")
    archive["name"] = _name(name, required=True)
    write_registry(root, registry)
    return dict(archive)


def remove_archive(root: Path, archive_id: str) -> dict[str, Any]:
    registry = read_registry(root)
    archive = next((item for item in registry["archives"] if item.get("id") == archive_id), None)
    if archive is None:
        raise ArchiveSourceError("Archive was not found")
    registry["archives"] = [item for item in registry["archives"] if item.get("id") != archive_id]
    write_registry(root, registry)
    shutil.rmtree(root / "archives" / archive_id, ignore_errors=True)
    return dict(archive)


def state_directory(root: Path, archive_id: str) -> Path:
    get_archive(root, archive_id)
    return root / "archives" / archive_id


def _name(value: str, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ArchiveSourceError("Archive name must be text")
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)[:80].strip()
    if required and not cleaned:
        raise ArchiveSourceError("Enter an archive name")
    return cleaned
