from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.ledger import record_completed_item, set_item_status, sync_item_ledger


class LedgerTests(unittest.TestCase):
    def test_records_explicit_harvest_not_present_in_saved_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = root / "ledger.json"
            destination = root / "archive" / "title_XYZ"
            record = record_completed_item(
                ledger,
                "instagram",
                "XYZ",
                "https://www.instagram.com/p/XYZ/",
                destination,
            )
            payload = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "complete")
        self.assertEqual(payload["summary"]["complete"], 1)
        self.assertEqual(payload["items"]["instagram:XYZ"]["archive_directory"], str(destination))

    def test_explicit_harvest_does_not_revive_retired_item(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = root / "ledger.json"
            ledger.write_text(json.dumps({"items": {"instagram:XYZ": {
                "source": "instagram", "source_id": "XYZ", "status": "retired-deleted"
            }}}), encoding="utf-8")
            record = record_completed_item(
                ledger, "instagram", "XYZ", "https://www.instagram.com/p/XYZ/", root / "bundle"
            )
        self.assertEqual(record["status"], "retired-deleted")

    def test_deleted_complete_item_stays_terminal_when_archive_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = root / "saved.json"
            ledger = root / "ledger.json"
            archive = root / "archive"
            archive.mkdir()
            saved.write_text(json.dumps({
                "complete": True,
                "items": [{
                    "source": "instagram",
                    "source_id": "ABC",
                    "source_url": "https://www.instagram.com/p/ABC/",
                }],
            }), encoding="utf-8")
            first = sync_item_ledger(saved, ledger, archive)
            self.assertEqual(first["items"]["instagram:ABC"]["status"], "discovered")
            set_item_status(ledger, "instagram", "ABC", "complete")

            rebuilt = sync_item_ledger(saved, ledger, archive)
            self.assertEqual(rebuilt["items"]["instagram:ABC"]["status"], "complete")

    def test_retired_deleted_preserves_old_path_as_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = root / "ledger.json"
            saved = root / "saved.json"
            archive = root / "archive"
            archive.mkdir()
            saved.write_text(json.dumps({
                "complete": True,
                "items": [{
                    "source": "instagram",
                    "source_id": "ABC",
                    "source_url": "https://www.instagram.com/p/ABC/",
                }],
            }), encoding="utf-8")
            ledger.write_text(json.dumps({
                "items": {
                    "instagram:ABC": {
                        "source": "instagram",
                        "source_id": "ABC",
                        "status": "complete",
                        "archive_directory": "archive/title_ABC",
                    }
                }
            }), encoding="utf-8")
            record = set_item_status(ledger, "instagram", "ABC", "retired-deleted", "user deleted")
            self.assertNotIn("archive_directory", record)
            self.assertEqual(record["last_archive_directory"], "archive/title_ABC")
            self.assertEqual(record["status"], "retired-deleted")
            rebuilt = sync_item_ledger(saved, ledger, archive)
            rebuilt_record = rebuilt["items"]["instagram:ABC"]
            self.assertEqual(rebuilt_record["last_archive_directory"], "archive/title_ABC")
            self.assertEqual(rebuilt_record["reason"], "user deleted")

    def test_archive_and_manual_review_set_terminal_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = root / "saved.json"
            ledger = root / "ledger.json"
            archive = root / "archive"
            review = root / "review.json"
            saved.write_text(json.dumps({
                "complete": True,
                "items": [
                    {"source": "instagram", "source_id": "A", "source_url": "https://instagram.com/p/A/"},
                    {"source": "instagram", "source_id": "B", "source_url": "https://instagram.com/p/B/"},
                ],
            }), encoding="utf-8")
            bundle = archive / "title_A"
            bundle.mkdir(parents=True)
            (bundle / "metadata.json").write_text(json.dumps({"item": {"source": "instagram", "source_id": "A"}}), encoding="utf-8")
            review.write_text(json.dumps({"items": [{
                "source": "instagram", "source_id": "B", "recorded_at": "now", "reason": "skip",
            }]}), encoding="utf-8")

            result = sync_item_ledger(saved, ledger, archive, review)
            self.assertEqual(result["items"]["instagram:A"]["status"], "complete")
            self.assertEqual(result["items"]["instagram:B"]["status"], "deferred")
            self.assertEqual(result["summary"]["total"], 2)
