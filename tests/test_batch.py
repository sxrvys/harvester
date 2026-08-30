from __future__ import annotations

import sys
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.batch import _select_oldest_unprocessed, harvest_oldest, new_batch_path


class BatchTests(unittest.TestCase):
    def test_generates_unique_timestamped_batch_path(self) -> None:
        now = datetime(2026, 8, 30, 1, 2, 3, 456789, tzinfo=timezone.utc)
        self.assertEqual(
            new_batch_path(Path("state/batches"), 10, now),
            Path("state/batches/20260830T010203456789Z-oldest-10.json"),
        )

    def test_rejects_delay_below_ten_seconds(self) -> None:
        with self.assertRaises(ValueError):
            harvest_oldest(Path("missing"), Path("state"), Path("profile"), Path("archive"), min_delay=9)

    def test_selects_oldest_unprocessed_and_skips_all_terminal_states(self) -> None:
        index = {
            "items": [
                {"source": "instagram", "source_id": source_id}
                for source_id in ("complete", "deferred", "deleted", "new-1", "new-2")
            ]
        }
        ledger = {
            "items": {
                "instagram:complete": {"status": "complete"},
                "instagram:deferred": {"status": "deferred"},
                "instagram:deleted": {"status": "retired-deleted"},
                "instagram:new-1": {"status": "discovered"},
                "instagram:new-2": {"status": "discovered"},
            }
        }
        with tempfile.TemporaryDirectory() as temporary:
            ledger_path = Path(temporary) / "ledger.json"
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            selected = _select_oldest_unprocessed(index, ledger_path, 2)
        self.assertEqual([item["source_id"] for item in selected], ["new-1", "new-2"])
