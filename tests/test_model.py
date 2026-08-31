from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.model import HarvestItem, title_from_caption


class HarvestItemTests(unittest.TestCase):
    def test_rejects_path_characters_in_source_id(self) -> None:
        with self.assertRaises(ValueError):
            HarvestItem("instagram", "../escape", "https://www.instagram.com/p/x/")

    def test_rejects_non_http_source_url(self) -> None:
        with self.assertRaises(ValueError):
            HarvestItem("instagram", "abc", "file:///tmp/post")

    def test_local_item_may_omit_source_url_without_storing_a_path(self) -> None:
        item = HarvestItem("local", "abc123", None, title="clip")
        self.assertIsNone(item.source_url)
        with self.assertRaises(ValueError):
            HarvestItem("instagram", "abc123", None)

    def test_caption_produces_readable_directory_with_stable_id(self) -> None:
        item = HarvestItem(
            "instagram",
            "DcSvEX4IWu7",
            "https://www.instagram.com/p/DcSvEX4IWu7/",
            caption="Shame (1968) - Ingmar Bergman\n\nDescription",
        )
        self.assertEqual(item.directory_name, "shame-1968_ingmar-bergman_DcSvEX4IWu7")
        self.assertEqual(title_from_caption(item.caption), ("Shame (1968)", "Ingmar Bergman"))


if __name__ == "__main__":
    unittest.main()
