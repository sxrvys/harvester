from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .model import slugify, title_from_caption


EXCLUDED_PREFIXES = ("#", "@", "follow ", "courtesy ", "available ", "http", "📍", "📞", "📅", "💬")
ARCHIVAL_TITLE_LIMIT = 44


def archival_bundle_name(order: int, title: str | None, creator: str | None = None) -> str:
    if order < 1:
        raise ValueError("archival order must be positive")
    descriptive = "-".join(part for part in (slugify(title), slugify(creator)) if part)
    descriptive = descriptive or "instagram-post"
    if len(descriptive) > ARCHIVAL_TITLE_LIMIT:
        shortened = descriptive[:ARCHIVAL_TITLE_LIMIT].rstrip("-")
        descriptive = shortened.rsplit("-", 1)[0] if "-" in shortened else shortened
    return f"{order:04d}__{descriptive}"


def preview_names(root: Path) -> dict[str, Any]:
    proposals: list[dict[str, Any]] = []
    for bundle in sorted(path for path in root.iterdir() if path.is_dir()):
        metadata_path = bundle / "metadata.json"
        if not metadata_path.is_file():
            continue
        try:
            item = json.loads(metadata_path.read_text(encoding="utf-8"))["item"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        proposed, title, creator, rule = propose_name(item)
        proposals.append({
            "source_id": item.get("source_id"),
            "current": bundle.name,
            "proposed": proposed,
            "changed": proposed != bundle.name,
            "title": title,
            "creator": creator,
            "rule": rule,
        })
    return {
        "schema_version": 1,
        "archive": str(root),
        "summary": {
            "bundles": len(proposals),
            "changes": sum(proposal["changed"] for proposal in proposals),
        },
        "proposals": proposals,
    }


def preview_asset_migration(root: Path, overrides_path: Path | None = None) -> dict[str, Any]:
    overrides = {}
    if overrides_path and overrides_path.is_file():
        overrides = json.loads(overrides_path.read_text(encoding="utf-8")).get("items", {})
    bundles: list[dict[str, Any]] = []
    for bundle in sorted(path for path in root.iterdir() if path.is_dir()):
        metadata_path = bundle / "metadata.json"
        if not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            item = metadata["item"]
            records = metadata["files"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        source_id = str(item["source_id"])
        preview_item = dict(item)
        if source_id in overrides:
            preview_item["manual_stem"] = overrides[source_id]["manual_stem"]
        proposed_folder, _, _, rule = propose_name(preview_item)
        suffix = f"_{source_id}"
        stem = proposed_folder[:-len(suffix)] if proposed_folder.endswith(suffix) else proposed_folder
        totals: dict[str, int] = {}
        for record in records:
            role = str(record.get("role"))
            totals[role] = totals.get(role, 0) + 1
        indexes: dict[str, int] = {}
        files: list[dict[str, Any]] = []
        for record in records:
            role = str(record.get("role"))
            indexes[role] = indexes.get(role, 0) + 1
            current = str(record["path"])
            extension = Path(current).suffix.lower()
            role_suffix = role if totals[role] == 1 else f"{role}-{indexes[role]:02d}"
            filename = f"{stem}__{role_suffix}{extension}"
            proposed = (Path("original") / filename).as_posix() if role == "original" else filename
            files.append({"current": current, "proposed": proposed, "changed": current != proposed})
        bundles.append({
            "source_id": source_id,
            "current_folder": bundle.name,
            "proposed_folder": proposed_folder,
            "rule": rule,
            "files": files,
        })
    return {
        "schema_version": 1,
        "archive": str(root),
        "summary": {
            "bundles": len(bundles),
            "file_changes": sum(file["changed"] for bundle in bundles for file in bundle["files"]),
        },
        "bundles": bundles,
    }


def propose_name(item: dict[str, Any]) -> tuple[str, str, str | None, str]:
    source_id = str(item["source_id"])
    manual_stem = _clean(item.get("manual_stem"))
    manual_title = _clean(item.get("manual_title"))
    manual_creator = _clean(item.get("manual_creator"))
    if manual_stem:
        stem = "_".join(slugify(part) for part in manual_stem.split("_") if slugify(part))
        stem = stem[:72].rstrip("-_") or "untitled"
        return f"{stem}_{source_id}", manual_title or manual_stem, manual_creator or None, "manual-stem"
    if manual_title:
        title, creator, rule = manual_title, manual_creator, "manual"
    else:
        caption = str(item.get("caption") or "")
        structured = _structured_caption(caption)
        if structured:
            title, creator, rule = structured
        else:
            title, rule = _caption_title(caption)
            creator = None
        if rule == "short-first-line":
            split_title, split_creator = title_from_caption(title)
            if split_creator and len(split_title or "") <= 60 and len(split_creator) <= 60:
                title, creator = split_title or title, split_creator
        if not title:
            title = _clean(item.get("title")) or _clean(item.get("author")) or "untitled"
            rule = "metadata-fallback"
    descriptive = "_".join(part for part in (slugify(title), slugify(creator)) if part)
    descriptive = descriptive[:72].rstrip("-_") or "untitled"
    return f"{descriptive}_{source_id}", title, creator, rule


def apply_asset_migration(root: Path, overrides_path: Path | None = None) -> dict[str, Any]:
    overrides = {}
    if overrides_path and overrides_path.is_file():
        overrides = json.loads(overrides_path.read_text(encoding="utf-8")).get("items", {})

    results: list[dict[str, Any]] = []
    for bundle in sorted(path for path in root.iterdir() if path.is_dir()):
        metadata_path = bundle / "metadata.json"
        if not metadata_path.is_file():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        item = metadata["item"]
        source_id = str(item["source_id"])
        override = overrides.get(source_id)
        if override:
            item["manual_stem"] = override["manual_stem"]
        proposed_folder, _, _, rule = propose_name(item)
        suffix = f"_{source_id}"
        stem = proposed_folder[:-len(suffix)] if proposed_folder.endswith(suffix) else proposed_folder

        totals: dict[str, int] = {}
        for record in metadata["files"]:
            role = str(record["role"])
            totals[role] = totals.get(role, 0) + 1
        indexes: dict[str, int] = {}
        renames: list[tuple[Path, Path, dict[str, Any], str]] = []
        for record in metadata["files"]:
            role = str(record["role"])
            indexes[role] = indexes.get(role, 0) + 1
            current_relative = str(record["path"])
            extension = Path(current_relative).suffix.lower()
            role_suffix = role if totals[role] == 1 else f"{role}-{indexes[role]:02d}"
            filename = f"{stem}__{role_suffix}{extension}"
            proposed_relative = (Path("original") / filename).as_posix() if role == "original" else filename
            source = bundle / current_relative
            destination = bundle / proposed_relative
            if source != destination:
                if destination.exists():
                    raise FileExistsError(destination)
                renames.append((source, destination, record, proposed_relative))

        final_bundle = root / proposed_folder
        if final_bundle != bundle and final_bundle.exists():
            raise FileExistsError(final_bundle)
        applied: list[tuple[Path, Path]] = []
        try:
            for source, destination, record, proposed_relative in renames:
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.rename(destination)
                applied.append((destination, source))
                record["path"] = proposed_relative
            _atomic_metadata(metadata_path, metadata)
            if final_bundle != bundle:
                bundle.rename(final_bundle)
            results.append({
                "source_id": source_id,
                "folder": final_bundle.name,
                "file_changes": len(renames),
                "rule": rule,
            })
        except BaseException:
            for destination, source in reversed(applied):
                if destination.exists() and not source.exists():
                    destination.rename(source)
            raise
    return {
        "schema_version": 1,
        "summary": {
            "bundles": len(results),
            "file_changes": sum(result["file_changes"] for result in results),
        },
        "bundles": results,
    }


def _atomic_metadata(destination: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".metadata-migration-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _structured_caption(caption: str) -> tuple[str, str | None, str] | None:
    lines = [_clean(line) for line in caption.splitlines() if _clean(line)]
    if not lines:
        return None

    for index, line in enumerate(lines):
        credit = re.match(r"^🎬\s*([^,]+),\s*((?:19|20)\d{2})\b", line)
        if credit and index > 0:
            work = lines[index - 1]
            if len(work) <= 60 and len(work.split()) <= 8:
                return work, f"{credit.group(1)} {credit.group(2)}", "work-credit"

    for line in lines[1:4]:
        detail = re.match(r"^(?:footwork\s+name|move\s+name|name)\s*:?\s*-?\s*(.+)$", line, re.IGNORECASE)
        if detail:
            base = lines[0]
            return f"{base} {detail.group(1)}", None, "labeled-detail"
    return None


def _caption_title(caption: str) -> tuple[str, str]:
    lines = [line.strip() for line in caption.splitlines() if line.strip()]
    if not lines:
        return "", "caption-empty"
    first = _clean(lines[0])
    if first and len(first) <= 80 and len(first.split()) <= 12:
        return first, "short-first-line"
    for line in lines[1:]:
        candidate = _clean(line)
        lower = candidate.lower()
        if (
            candidate
            and len(candidate) <= 60
            and 1 <= len(candidate.split()) <= 8
            and not lower.startswith(EXCLUDED_PREFIXES)
            and not candidate.endswith(("?", "!"))
        ):
            return candidate, "short-standalone-line"
    words = first.split()
    return " ".join(words[:8]).rstrip(".,;:!?—–-"), "bounded-first-phrase"


def _clean(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()
