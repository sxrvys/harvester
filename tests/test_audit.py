from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvest.audit import audit_archive


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_bundle(root: Path, name: str, source_id: str, data: bytes = b"media") -> Path:
    bundle = root / name
    original = bundle / "original" / "01_clip.mp4"
    original.parent.mkdir(parents=True)
    original.write_bytes(data)
    metadata = {
        "schema_version": 1,
        "item": {"source": "instagram", "source_id": source_id},
        "files": [{
            "path": "original/01_clip.mp4",
            "role": "original",
            "bytes": len(data),
            "sha256": sha256(data),
        }],
    }
    (bundle / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return bundle


class AuditTests(unittest.TestCase):
    @patch("harvest.audit.probe", return_value={"streams": [{"codec_type": "video"}]})
    def test_valid_bundle_passes(self, _probe: object) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_bundle(root, "useful_ABC", "ABC")
            report = audit_archive(root)
            self.assertEqual(report["summary"]["errors"], 0)
            self.assertEqual(report["summary"]["warnings"], 0)

    @patch("harvest.audit.probe", return_value={"streams": [{"codec_type": "video"}]})
    def test_detects_hash_size_unrecorded_and_duplicate_identity(self, _probe: object) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = make_bundle(root, "first_ABC", "ABC")
            second = make_bundle(root, "second_ABC", "ABC")
            (first / "extra.txt").write_text("extra", encoding="utf-8")
            metadata_path = first / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["files"][0]["bytes"] = 999
            metadata["files"][0]["sha256"] = "0" * 64
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            codes = {issue["code"] for issue in audit_archive(root)["issues"]}
            self.assertTrue({"size_mismatch", "hash_mismatch", "unrecorded_file", "duplicate_identity"} <= codes)

    def test_reports_invalid_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "broken_ABC"
            bundle.mkdir()
            (bundle / "metadata.json").write_text("not json", encoding="utf-8")
            report = audit_archive(Path(temporary))
            self.assertEqual(report["issues"][0]["code"], "invalid_metadata")

