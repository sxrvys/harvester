from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvest.review import build_batch_review, render_batch_review


class ReviewTests(unittest.TestCase):
    def test_reports_present_and_deleted_items_from_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            bundle = archive / "strange-sound_A"
            bundle.mkdir(parents=True)
            (bundle / "metadata.json").write_text(json.dumps({
                "item": {
                    "source": "instagram", "source_id": "A", "caption": "A strange sound\n#noise",
                    "source_metadata": {"audio": {
                        "label": "Don Quichotte", "title": "Don Quichotte",
                        "artist": "Magazine 60", "is_original": False,
                    }},
                },
                "files": [{
                    "role": "video", "path": "video.mp4",
                    "probe": {"format": {"duration": "12.5"}},
                }],
            }), encoding="utf-8")
            batch = root / "batch.json"
            batch.write_text(json.dumps({"items": [
                {"source": "instagram", "source_id": "A", "status": "complete"},
                {"source": "instagram", "source_id": "B", "status": "complete"},
            ]}), encoding="utf-8")
            ledger = root / "ledger.json"
            ledger.write_text(json.dumps({"items": {
                "instagram:A": {"status": "complete"},
                "instagram:B": {"status": "retired-deleted"},
            }}), encoding="utf-8")

            review = build_batch_review(batch, archive, ledger)
            text = render_batch_review(review)

            self.assertEqual(review["summary"], {"items": 2, "present": 1, "deleted": 1, "failed": 0})
            self.assertEqual(review["items"][0]["duration_seconds"], 12.5)
            self.assertIn("Magazine 60 — Don Quichotte", text)
            self.assertIn("B [retired-deleted]", text)
            self.assertIn("bundle: not present", text)
