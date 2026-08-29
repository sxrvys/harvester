from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvest.archive import Archive
from harvest.model import HarvestItem


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = HarvestItem(
            source="instagram",
            source_id="ABC_123-x",
            source_url="https://www.instagram.com/p/ABC_123-x/",
            retrieved_at=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
        )

    def test_item_directory_is_stable(self) -> None:
        archive = Archive(Path("archive"))
        self.assertEqual(archive.item_directory(self.item), Path("archive/instagram_ABC_123-x"))

    def test_asset_names_are_readable_and_do_not_include_source_id(self) -> None:
        item = HarvestItem(
            source="instagram",
            source_id="ABC_123-x",
            source_url="https://www.instagram.com/p/ABC_123-x/",
            title="Shame (1968)",
            creator="Ingmar Bergman",
        )
        archive = Archive(Path("archive"))
        self.assertEqual(archive.item_directory(item).name, "shame-1968_ingmar-bergman_ABC_123-x")
        self.assertEqual(archive.asset_relative_path(item, "audio", ".wav"), Path("shame-1968_ingmar-bergman__audio.wav"))
        self.assertEqual(
            archive.asset_relative_path(item, "original", ".mp4", 2, 3),
            Path("original/shame-1968_ingmar-bergman__original-02.mp4"),
        )

    def test_preserve_original_is_idempotent_and_metadata_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "clip.mp4"
            incoming.write_bytes(b"media bytes")
            archive = Archive(root / "archive")

            first = archive.preserve_original(self.item, incoming, 1)
            second = archive.preserve_original(self.item, incoming, 1)
            self.assertEqual(first, second)

            metadata_path = archive.write_metadata(self.item, [first], {"ffmpeg": "test"})
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema_version"], 1)
            self.assertEqual(metadata["item"]["source_id"], "ABC_123-x")
            self.assertEqual(len(metadata["files"][0]["sha256"]), 64)

    def test_refuses_to_overwrite_a_different_original(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "clip.mp4"
            incoming.write_bytes(b"first")
            archive = Archive(root / "archive")
            archive.preserve_original(self.item, incoming, 1)
            incoming.write_bytes(b"different")
            with self.assertRaises(FileExistsError):
                archive.preserve_original(self.item, incoming, 1)


if __name__ == "__main__":
    unittest.main()
