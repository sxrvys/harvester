from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .archive import _sha256
from .media import probe


def audit_archive(root: Path) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    bundles = sorted(path for path in root.iterdir() if path.is_dir()) if root.is_dir() else []
    identities: dict[tuple[str, str], Path] = {}
    audited_files = 0

    for bundle in bundles:
        metadata_path = bundle / "metadata.json"
        if not metadata_path.is_file():
            _issue(issues, "error", bundle, "missing_metadata", "metadata.json is missing")
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            _issue(issues, "error", bundle, "invalid_metadata", str(error))
            continue

        if metadata.get("schema_version") != 1:
            _issue(issues, "error", bundle, "unsupported_schema", "schema_version must be 1")
        item = metadata.get("item")
        if not isinstance(item, dict):
            _issue(issues, "error", bundle, "missing_item", "metadata item object is missing")
            continue
        source, source_id = item.get("source"), item.get("source_id")
        if not isinstance(source, str) or not isinstance(source_id, str):
            _issue(issues, "error", bundle, "missing_identity", "source/source_id is missing")
        else:
            identity = (source, source_id)
            if identity in identities:
                _issue(issues, "error", bundle, "duplicate_identity", f"also present in {identities[identity].name}")
            else:
                identities[identity] = bundle
            ordered_archival_name = re.fullmatch(r"\d{4,}__[a-z0-9]+(?:-[a-z0-9]+)*", bundle.name)
            if not ordered_archival_name and not bundle.name.endswith(f"_{source_id}"):
                _issue(issues, "warning", bundle, "id_not_in_folder", "folder does not end with stable source ID")

        file_records = metadata.get("files")
        if not isinstance(file_records, list):
            _issue(issues, "error", bundle, "missing_files", "files must be an array")
            continue
        recorded_paths: set[str] = set()
        original_count = 0
        for record in file_records:
            if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                _issue(issues, "error", bundle, "invalid_file_record", "file record lacks a path")
                continue
            relative = record["path"]
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts:
                _issue(issues, "error", bundle, "unsafe_path", relative)
                continue
            if relative in recorded_paths:
                _issue(issues, "error", bundle, "duplicate_file_record", relative)
                continue
            recorded_paths.add(relative)
            path = bundle / relative
            if not path.is_file():
                _issue(issues, "error", bundle, "missing_file", relative)
                continue
            audited_files += 1
            if record.get("role") == "original":
                original_count += 1
            if path.stat().st_size != record.get("bytes"):
                _issue(issues, "error", bundle, "size_mismatch", relative)
            if _sha256(path) != record.get("sha256"):
                _issue(issues, "error", bundle, "hash_mismatch", relative)
            try:
                facts = probe(path)
            except Exception as error:
                _issue(issues, "error", bundle, "unreadable_media", f"{relative}: {type(error).__name__}")
                continue
            if record.get("role") == "audio":
                streams = [stream for stream in facts.get("streams", []) if stream.get("codec_type") == "audio"]
                if not streams:
                    _issue(issues, "error", bundle, "audio_missing_stream", relative)
                else:
                    stream = streams[0]
                    encoding = record.get("encoding")
                    preset = encoding.get("preset") if isinstance(encoding, dict) else None
                    expected = {
                        "wav_48k_24": ("pcm_s24le", "48000", 2),
                        "wav_44k_16": ("pcm_s16le", "44100", 2),
                        "flac_48k_24": ("flac", "48000", 2),
                        "mp3_320": ("mp3", "48000", 2),
                        "mp3_192": ("mp3", "48000", 2),
                    }
                    if preset is None and path.suffix.lower() == ".wav":
                        preset = "wav_48k_24"
                    actual = (stream.get("codec_name"), stream.get("sample_rate"), stream.get("channels"))
                    if preset not in expected:
                        _issue(issues, "error", bundle, "audio_preset", f"{relative}: missing or unknown preset")
                    elif actual != expected[preset]:
                        _issue(issues, "error", bundle, "audio_contract", f"{relative}: {actual}")
        if original_count == 0:
            _issue(issues, "error", bundle, "missing_original", "no original file record")

        actual_paths = {
            path.relative_to(bundle).as_posix()
            for path in bundle.rglob("*")
            if path.is_file() and path.name not in {"metadata.json", ".DS_Store"}
        }
        for unexpected in sorted(actual_paths - recorded_paths):
            _issue(issues, "warning", bundle, "unrecorded_file", unexpected)

    return {
        "schema_version": 1,
        "archive": str(root),
        "summary": {
            "bundles": len(bundles),
            "files": audited_files,
            "errors": sum(issue["severity"] == "error" for issue in issues),
            "warnings": sum(issue["severity"] == "warning" for issue in issues),
        },
        "issues": issues,
    }


def _issue(issues: list[dict[str, str]], severity: str, bundle: Path, code: str, detail: str) -> None:
    issues.append({"severity": severity, "bundle": bundle.name, "code": code, "detail": detail})
