from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .model import HarvestItem


class Archive:
    """Deterministic filesystem archive for harvester items."""

    def __init__(self, root: Path, directory_name: str | None = None) -> None:
        self.root = root
        if directory_name is not None and (
            not directory_name or Path(directory_name).name != directory_name
        ):
            raise ValueError("archive directory name must be one safe path component")
        self.directory_name = directory_name

    def item_directory(self, item: HarvestItem) -> Path:
        preferred = self.root / (self.directory_name or item.directory_name)
        if preferred.exists():
            return preferred
        legacy = self.root / item.key
        if legacy.exists() and preferred != legacy:
            legacy.rename(preferred)
        return preferred

    def asset_stem(self, item: HarvestItem) -> str:
        if self.directory_name:
            return self.directory_name
        suffix = f"_{item.source_id}"
        directory_name = item.directory_name
        return directory_name[:-len(suffix)] if directory_name.endswith(suffix) else directory_name

    def asset_relative_path(
        self,
        item: HarvestItem,
        role: str,
        extension: str,
        index: int = 1,
        total: int = 1,
    ) -> Path:
        numbered_role = role if total == 1 else f"{role}-{index:02d}"
        filename = f"{self.asset_stem(item)}__{numbered_role}{extension.lower()}"
        return Path("original") / filename if role == "original" else Path(filename)

    def preserve_original(
        self,
        item: HarvestItem,
        source: Path,
        index: int,
        total: int = 1,
    ) -> dict[str, Any]:
        if not source.is_file():
            raise FileNotFoundError(source)
        original_dir = self.item_directory(item) / "original"
        original_dir.mkdir(parents=True, exist_ok=True)
        destination = self.item_directory(item) / self.asset_relative_path(
            item, "original", source.suffix, index, total
        )
        if destination.exists() and _sha256(destination) != _sha256(source):
            raise FileExistsError(f"refusing to replace different original: {destination}")
        if not destination.exists():
            shutil.copy2(source, destination)
        return {
            "path": destination.relative_to(self.item_directory(item)).as_posix(),
            "role": "original",
            "bytes": destination.stat().st_size,
            "sha256": _sha256(destination),
        }

    def copy_derivative(self, item: HarvestItem, source: Path, name: str, role: str) -> dict[str, Any]:
        destination = self.item_directory(item) / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and _sha256(destination) != _sha256(source):
            raise FileExistsError(f"refusing to replace different derivative: {destination}")
        if not destination.exists():
            shutil.copy2(source, destination)
        return {
            "path": destination.relative_to(self.item_directory(item)).as_posix(),
            "role": role,
            "bytes": destination.stat().st_size,
            "sha256": _sha256(destination),
        }

    def write_metadata(self, item: HarvestItem, files: list[dict[str, Any]], tools: dict[str, str]) -> Path:
        item_dir = self.item_directory(item)
        item_dir.mkdir(parents=True, exist_ok=True)
        preserved: dict[str, Any] = {}
        existing_path = item_dir / "metadata.json"
        if existing_path.is_file():
            try:
                existing_item = json.loads(existing_path.read_text(encoding="utf-8")).get("item", {})
                preserved = {
                    key: existing_item[key]
                    for key in ("manual_stem", "manual_title", "manual_creator")
                    if existing_item.get(key)
                }
            except (OSError, json.JSONDecodeError):
                preserved = {}
        payload = {
            "schema_version": 1,
            "harvest_version": __version__,
            "item": {**_json_ready(asdict(item)), **preserved},
            "files": files,
            "tools": tools,
        }
        destination = item_dir / "metadata.json"
        _atomic_json(destination, payload)
        return destination


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _atomic_json(destination: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".metadata-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, destination)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
