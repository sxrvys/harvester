from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvest.deletion import ArchiveDeletionError, delete_archive_item


class DeletionTests(unittest.TestCase):
    def test_moves_verified_bundle_and_durably_retires_item(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            bundle = archive / "title_ABC"
            bundle.mkdir(parents=True)
            (bundle / "metadata.json").write_text(json.dumps({
                "item": {"source": "instagram", "source_id": "ABC"}
            }), encoding="utf-8")
            ledger = root / "ledger.json"
            ledger.write_text(json.dumps({"items": {"instagram:ABC": {
                "source": "instagram",
                "source_id": "ABC",
                "status": "complete",
                "archive_directory": str(bundle),
            }}}), encoding="utf-8")

            result = delete_archive_item(ledger, archive, root / "trash", "ABC")

            self.assertFalse(bundle.exists())
            self.assertTrue((root / "trash" / "title_ABC" / "metadata.json").is_file())
            record = json.loads(ledger.read_text(encoding="utf-8"))["items"]["instagram:ABC"]
            self.assertEqual(result["status"], "retired-deleted")
            self.assertEqual(record["last_archive_directory"], str(bundle))
            self.assertEqual(record["reason"], "User removed from archive")

    def test_refuses_metadata_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            bundle = archive / "title_ABC"
            bundle.mkdir(parents=True)
            (bundle / "metadata.json").write_text(json.dumps({
                "item": {"source": "instagram", "source_id": "OTHER"}
            }), encoding="utf-8")
            ledger = root / "ledger.json"
            ledger.write_text(json.dumps({"items": {"instagram:ABC": {
                "source": "instagram", "source_id": "ABC", "status": "complete",
                "archive_directory": str(bundle),
            }}}), encoding="utf-8")
            with self.assertRaises(ArchiveDeletionError):
                delete_archive_item(ledger, archive, root / "trash", "ABC")
            self.assertTrue(bundle.exists())
