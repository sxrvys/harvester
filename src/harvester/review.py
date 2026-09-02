from __future__ import annotations

import json
import re
import base64
import subprocess
from pathlib import Path
from typing import Any

from .ledger import identity_key
from .naming import propose_name


def build_batch_review(
    batch_path: Path,
    archive_root: Path,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Build a read-only review model from local batch, ledger, and bundle metadata."""

    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    ledger_items: dict[str, dict[str, Any]] = {}
    if ledger_path and ledger_path.is_file():
        ledger_items = json.loads(ledger_path.read_text(encoding="utf-8")).get("items", {})
    bundles = _bundles_by_id(archive_root)
    items: list[dict[str, Any]] = []
    for batch_item in batch.get("items", []):
        source = str(batch_item.get("source", "instagram"))
        source_id = str(batch_item["source_id"])
        ledger_record = ledger_items.get(identity_key(source, source_id), {})
        bundle = bundles.get((source, source_id))
        metadata = _read_metadata(bundle) if bundle else None
        item_metadata = metadata.get("item", {}) if metadata else {}
        file_records = metadata.get("files", []) if metadata else []
        proposed = propose_name(item_metadata)[0] if item_metadata else None
        audio = item_metadata.get("source_metadata", {}).get("audio") if item_metadata else None
        items.append({
            "source": source,
            "source_id": source_id,
            "source_url": batch_item.get("source_url"),
            "batch_status": batch_item.get("status"),
            "lifecycle_status": ledger_record.get("status"),
            "archive_present": bundle is not None,
            "bundle": bundle.name if bundle else None,
            "title": item_metadata.get("archive_display_title") or item_metadata.get("title") or proposed or source_id,
            "proposed_bundle": proposed,
            "media": _media_summary(file_records),
            "duration_seconds": _duration(file_records),
            "audio_attribution": audio,
            "caption_excerpt": _excerpt(item_metadata.get("caption")),
            "thumbnail": _thumbnail(bundle, file_records),
        })
    return {
        "schema_version": 1,
        "batch": str(batch_path),
        "summary": {
            "items": len(items),
            "present": sum(item["archive_present"] for item in items),
            "deleted": sum(item["lifecycle_status"] == "retired-deleted" for item in items),
            "failed": sum(item["batch_status"] == "failed" for item in items),
        },
        "items": items,
    }


def render_batch_review(review: dict[str, Any]) -> str:
    summary = review["summary"]
    lines = [
        f"batch review: {summary['items']} items, {summary['present']} present, "
        f"{summary['deleted']} deleted, {summary['failed']} failed"
    ]
    for index, item in enumerate(review["items"], start=1):
        status = item["lifecycle_status"] or item["batch_status"] or "unknown"
        lines.append(f"\n{index}. {item['source_id']} [{status}]")
        lines.append(f"   bundle: {item['bundle'] or 'not present'}")
        if item["proposed_bundle"] and item["proposed_bundle"] != item["bundle"]:
            lines.append(f"   proposed: {item['proposed_bundle']}")
        media = ", ".join(f"{role}={count}" for role, count in sorted(item["media"].items())) or "none"
        duration = item["duration_seconds"]
        lines.append(f"   media: {media}; duration: {duration:.1f}s" if duration is not None else f"   media: {media}")
        audio = item["audio_attribution"] or {}
        if audio.get("title") or audio.get("artist"):
            lines.append(f"   music: {audio.get('artist') or 'unknown artist'} — {audio.get('title') or 'unknown title'}")
        elif audio.get("label"):
            lines.append(f"   audio: {audio['label']}")
        if item["caption_excerpt"]:
            lines.append(f"   caption: {item['caption_excerpt']}")
    return "\n".join(lines)


def _bundles_by_id(root: Path) -> dict[tuple[str, str], Path]:
    result: dict[tuple[str, str], Path] = {}
    for metadata_path in root.glob("*/metadata.json") if root.is_dir() else []:
        metadata = _read_metadata(metadata_path.parent)
        if metadata:
            item = metadata.get("item", {})
            source, source_id = item.get("source"), item.get("source_id")
            if isinstance(source, str) and isinstance(source_id, str):
                result[(source, source_id)] = metadata_path.parent
    return result


def _read_metadata(bundle: Path | None) -> dict[str, Any] | None:
    if bundle is None:
        return None
    try:
        value = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _media_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for record in records:
        role = record.get("role")
        if isinstance(role, str):
            summary[role] = summary.get(role, 0) + 1
    return summary


def _duration(records: list[dict[str, Any]]) -> float | None:
    durations: list[float] = []
    for record in records:
        value = record.get("probe", {}).get("format", {}).get("duration")
        try:
            durations.append(float(value))
        except (TypeError, ValueError):
            continue
    return max(durations) if durations else None


def _excerpt(caption: Any, limit: int = 180) -> str | None:
    if not isinstance(caption, str):
        return None
    clean = re.sub(r"\s+", " ", caption).strip()
    if not clean:
        return None
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def _thumbnail(bundle: Path | None, records: list[dict[str, Any]]) -> str | None:
    if bundle is None:
        return None
    record = next((item for item in records if item.get("role") in {"video", "image"}), None)
    if not record or not isinstance(record.get("path"), str):
        return None
    media = (bundle / record["path"]).resolve()
    if media.parent != bundle.resolve() and bundle.resolve() not in media.parents:
        return None
    try:
        completed = subprocess.run([
            "ffmpeg", "-v", "error", "-ss", "1", "-i", str(media),
            "-frames:v", "1", "-vf", "scale=160:-2", "-q:v", "8",
            "-f", "image2pipe", "-vcodec", "mjpeg", "-",
        ], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode or not completed.stdout or len(completed.stdout) > 40_000:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(completed.stdout).decode("ascii")
