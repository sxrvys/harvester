from __future__ import annotations

import json
import os
import shutil
import tempfile
import re
from pathlib import Path
from typing import Any

from .ledger import identity_key, set_item_status


class ArchiveDeletionError(RuntimeError):
    pass


def rename_archive_item(
    ledger_path: Path,
    index_path: Path,
    batches_root: Path,
    archive_root: Path,
    source_id: str,
    requested_title: str,
    source: str = "instagram",
    related_state_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Rename one verified archival bundle and every local state reference atomically."""
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    key = identity_key(source, source_id)
    record = ledger.get("items", {}).get(key)
    if not isinstance(record, dict) or not isinstance(record.get("saved_order_oldest_first"), int):
        raise ArchiveDeletionError("archival item is not present in the ledger")
    old = Path(str(record.get("archive_directory", ""))).resolve()
    root = archive_root.resolve()
    if old.parent != root or not old.is_dir():
        raise ArchiveDeletionError("archival bundle is missing or outside archive root")
    try:
        metadata = json.loads((old / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ArchiveDeletionError("archival metadata is unreadable") from None
    if (metadata.get("item", {}).get("source"), metadata.get("item", {}).get("source_id")) != (source, source_id):
        raise ArchiveDeletionError("bundle metadata identity does not match rename target")
    title = re.sub(r"[^a-z0-9]+", "-", requested_title.casefold()).strip("-")
    if not title:
        raise ArchiveDeletionError("choose a non-empty title")
    if len(title) > 44:
        shortened = title[:44].rstrip("-")
        title = shortened.rsplit("-", 1)[0] if "-" in shortened else shortened
    existing_order = re.match(r"^(\d+)__", old.name)
    order = existing_order.group(1) if existing_order else f"{record['saved_order_oldest_first']:04d}"
    new = root / f"{order}__{title}"
    if new != old and new.exists():
        raise ArchiveDeletionError("another archival bundle already uses that name")

    paths = [ledger_path]
    if index_path.is_file():
        paths.append(index_path)
    paths.extend(sorted(batches_root.glob("*.json")) if batches_root.is_dir() else [])
    for state_root in related_state_roots or []:
        paths.append(state_root / "item-ledger.json")
        paths.append(state_root / "saved-index.json")
        paths.extend(sorted((state_root / "batches").glob("*.json")) if (state_root / "batches").is_dir() else [])
    paths = list(dict.fromkeys(path for path in paths if path.is_file()))
    originals: dict[Path, dict[str, Any]] = {}
    changed: dict[Path, dict[str, Any]] = {}
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        originals[path] = payload
        mapped_items = payload.get("items")
        if isinstance(mapped_items, dict) and isinstance(mapped_items.get(key), dict) and mapped_items[key].get("archive_directory"):
            mapped_items[key]["archive_directory"] = str(new)
        for item in payload.get("items", []) if isinstance(payload.get("items"), list) else []:
            if isinstance(item, dict) and item.get("source") == source and item.get("source_id") == source_id and item.get("archive_directory"):
                current = Path(str(item["archive_directory"]))
                item["archive_directory"] = str(current.parent / new.name) if not current.is_absolute() else str(new)
        changed[path] = payload
    metadata_original = json.loads(json.dumps(metadata))
    metadata.setdefault("item", {})["archive_display_title"] = requested_title.strip()[:200]

    written: list[Path] = []
    renamed = False
    try:
        if new != old:
            old.rename(new)
            renamed = True
        _atomic_json(new / "metadata.json", metadata)
        for path, payload in changed.items():
            _atomic_json(path, payload)
            written.append(path)
    except BaseException:
        for path in reversed(written):
            _atomic_json(path, originals[path])
        _atomic_json(new / "metadata.json", metadata_original)
        if renamed and new.exists() and not old.exists():
            new.rename(old)
        raise
    return {"source_id": source_id, "directory": str(new), "title": requested_title.strip()[:200]}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def delete_archive_item(
    ledger_path: Path,
    archive_root: Path,
    trash_root: Path,
    source_id: str,
    source: str = "instagram",
    reason: str = "User removed from archive",
) -> dict[str, Any]:
    """Move one verified bundle to an explicit Trash directory and retire its identity."""

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    key = identity_key(source, source_id)
    if key not in ledger.get("items", {}):
        raise ArchiveDeletionError(f"item is not present in ledger: {key}")
    record = ledger["items"][key]
    if record.get("status") == "retired-deleted":
        return {"source_id": source_id, "status": "already-retired-deleted", "destination": None}
    archive_directory = record.get("archive_directory")
    if not archive_directory:
        raise ArchiveDeletionError(f"item has no recorded archive directory: {key}")

    archive_base = archive_root.resolve()
    bundle = Path(archive_directory)
    bundle = bundle if bundle.is_absolute() else Path.cwd() / bundle
    bundle = bundle.resolve()
    if bundle.parent != archive_base or not bundle.is_dir():
        raise ArchiveDeletionError(f"recorded bundle is missing or outside archive root: {bundle}")
    metadata_path = bundle / "metadata.json"
    try:
        item = json.loads(metadata_path.read_text(encoding="utf-8"))["item"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ArchiveDeletionError(f"bundle metadata is unreadable: {metadata_path}") from error
    if (item.get("source"), item.get("source_id")) != (source, source_id):
        raise ArchiveDeletionError("bundle metadata identity does not match deletion target")

    trash_root.mkdir(parents=True, exist_ok=True)
    destination = trash_root / bundle.name
    if destination.exists():
        raise ArchiveDeletionError(f"Trash destination already exists: {destination}")
    shutil.move(str(bundle), str(destination))
    try:
        updated = set_item_status(ledger_path, source, source_id, "retired-deleted", reason)
    except BaseException:
        shutil.move(str(destination), str(bundle))
        raise
    return {"source_id": source_id, "status": updated["status"], "destination": str(destination)}
