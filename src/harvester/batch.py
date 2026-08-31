from __future__ import annotations

import json
import os
import random
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .instagram import AcquisitionError, harvest_instagram_url
from .audio import DEFAULT_AUDIO_PRESET
from .ledger import TERMINAL_STATUSES, identity_key


class BatchError(RuntimeError):
    pass


def harvest_oldest(
    index_path: Path,
    batch_path: Path,
    firefox_profile: Path,
    archive_root: Path,
    count: int = 10,
    min_delay: float = 10.0,
    max_delay: float = 15.0,
    item_ledger_path: Path | None = None,
    manual_review_path: Path | None = None,
    audio_preset: str = DEFAULT_AUDIO_PRESET,
) -> dict[str, Any]:
    if count < 1:
        raise ValueError("count must be positive")
    if min_delay < 10 or max_delay < min_delay:
        raise ValueError("delays must satisfy 10 <= min_delay <= max_delay")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    if not index.get("complete"):
        raise BatchError("Saved index is incomplete; refusing to guess the oldest items")
    selected = _select_oldest_unprocessed(index, item_ledger_path, count)
    if len(selected) < count:
        raise BatchError(f"Saved index contains only {len(selected)} eligible unprocessed items")

    if batch_path.exists():
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        expected = [item["source_id"] for item in selected]
        actual = [item["source_id"] for item in batch["items"]]
        if actual != expected:
            raise BatchError("existing batch state does not match the current oldest selection")
    else:
        batch = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "selection": "oldest-saved-first",
            "min_delay_seconds": min_delay,
            "max_delay_seconds": max_delay,
            "items": [{**item, "status": "pending"} for item in selected],
        }
        _atomic_write(batch_path, batch)

    # Failed is terminal. A later manual action may explicitly create a retry;
    # ordinary resume only continues pending or interrupted work.
    pending_positions = [
        index for index, item in enumerate(batch["items"])
        if item["status"] in {"pending", "running"}
    ]
    for pending_number, position in enumerate(pending_positions):
        record = batch["items"][position]
        record["status"] = "running"
        record["started_at"] = datetime.now(timezone.utc).isoformat()
        record.pop("error", None)
        _atomic_write(batch_path, batch)
        try:
            destination = harvest_instagram_url(
                record["source_url"], firefox_profile, archive_root, record.get("audio"), audio_preset
            )
        except AcquisitionError as error:
            record["status"] = "failed"
            record["error"] = str(error)
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_write(batch_path, batch)
            if "authentication/rate-limit stop" in str(error):
                raise BatchError("batch stopped on authentication or rate-limit signal") from error
            _append_manual_review(manual_review_path or batch_path.parent / "manual-review.json", record, str(error))
        else:
            record["status"] = "complete"
            record["archive_directory"] = str(destination)
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_write(batch_path, batch)

        if pending_number < len(pending_positions) - 1:
            delay = random.uniform(min_delay, max_delay)
            record["next_item_delay_seconds"] = round(delay, 3)
            _atomic_write(batch_path, batch)
            time.sleep(delay)

    return batch


def new_batch_path(directory: Path, count: int, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
    return directory / f"{stamp}-oldest-{count}.json"


def _select_oldest_unprocessed(
    index: dict[str, Any], item_ledger_path: Path | None, count: int
) -> list[dict[str, Any]]:
    if item_ledger_path is None:
        return index["items"][:count]
    ledger = json.loads(item_ledger_path.read_text(encoding="utf-8"))
    selected: list[dict[str, Any]] = []
    for item in index["items"]:
        record = ledger.get("items", {}).get(identity_key(item["source"], item["source_id"]), {})
        if record.get("status") in TERMINAL_STATUSES:
            continue
        selected.append(item)
        if len(selected) == count:
            break
    return selected


def _append_manual_review(destination: Path, record: dict[str, Any], error: str) -> None:
    if destination.exists():
        queue = json.loads(destination.read_text(encoding="utf-8"))
    else:
        queue = {"schema_version": 1, "items": []}
    if any(item["source_id"] == record["source_id"] for item in queue["items"]):
        return
    queue["items"].append({
        "source": record["source"],
        "source_id": record["source_id"],
        "source_url": record["source_url"],
        "status": "deferred",
        "reason": error,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    _atomic_write(destination, queue)


def _atomic_write(destination: Path, payload: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".batch-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
