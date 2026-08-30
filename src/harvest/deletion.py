from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .ledger import identity_key, set_item_status


class ArchiveDeletionError(RuntimeError):
    pass


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
