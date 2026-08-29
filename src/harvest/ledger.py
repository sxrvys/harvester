from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"complete", "deferred", "retired-used", "retired-deleted"}
VALID_STATUSES = {"discovered", *TERMINAL_STATUSES}


def sync_item_ledger(
    saved_index_path: Path,
    ledger_path: Path,
    archive_root: Path,
    manual_review_path: Path | None = None,
) -> dict[str, Any]:
    saved_index = json.loads(saved_index_path.read_text(encoding="utf-8"))
    if not saved_index.get("complete"):
        raise ValueError("Saved index must be complete before syncing item ledger")
    existing = (
        json.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger_path.exists()
        else {"schema_version": 1, "items": {}}
    )
    existing_items = existing.get("items", {})
    now = datetime.now(timezone.utc).isoformat()
    items: dict[str, dict[str, Any]] = {}

    for position, saved in enumerate(saved_index["items"], start=1):
        key = identity_key(saved["source"], saved["source_id"])
        previous = existing_items.get(key, {})
        status = previous.get("status", "discovered")
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid existing ledger status for {key}: {status}")
        items[key] = {
            "source": saved["source"],
            "source_id": saved["source_id"],
            "source_url": saved["source_url"],
            "saved_order_oldest_first": position,
            "status": status,
            "status_updated_at": previous.get("status_updated_at", now),
            **({"archive_directory": previous["archive_directory"]} if previous.get("archive_directory") else {}),
        }

    for metadata_path in archive_root.glob("*/metadata.json") if archive_root.is_dir() else []:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            source = metadata["item"]["source"]
            source_id = metadata["item"]["source_id"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        key = identity_key(source, source_id)
        if key not in items:
            continue
        if items[key]["status"] not in {"retired-used", "retired-deleted"}:
            items[key]["status"] = "complete"
            items[key]["status_updated_at"] = now
            items[key]["archive_directory"] = str(metadata_path.parent)

    if manual_review_path and manual_review_path.is_file():
        review = json.loads(manual_review_path.read_text(encoding="utf-8"))
        for deferred in review.get("items", []):
            key = identity_key(deferred["source"], deferred["source_id"])
            if key in items and items[key]["status"] == "discovered":
                items[key]["status"] = "deferred"
                items[key]["status_updated_at"] = deferred.get("recorded_at", now)
                items[key]["reason"] = deferred.get("reason")

    payload = {
        "schema_version": 1,
        "updated_at": now,
        "items": items,
        "summary": _summary(items),
    }
    _atomic_json(ledger_path, payload)
    return payload


def set_item_status(
    ledger_path: Path,
    source: str,
    source_id: str,
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    key = identity_key(source, source_id)
    if key not in ledger["items"]:
        raise KeyError(key)
    record = ledger["items"][key]
    record["status"] = status
    record["status_updated_at"] = datetime.now(timezone.utc).isoformat()
    if status == "retired-deleted" and record.get("archive_directory"):
        record["last_archive_directory"] = record.pop("archive_directory")
    if reason:
        record["reason"] = reason
    ledger["updated_at"] = record["status_updated_at"]
    ledger["summary"] = _summary(ledger["items"])
    _atomic_json(ledger_path, ledger)
    return record


def identity_key(source: str, source_id: str) -> str:
    return f"{source}:{source_id}"


def _summary(items: dict[str, dict[str, Any]]) -> dict[str, int]:
    summary = {status: 0 for status in sorted(VALID_STATUSES)}
    for item in items.values():
        summary[item["status"]] += 1
    summary["total"] = len(items)
    return summary


def _atomic_json(destination: Path, payload: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".item-ledger-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
