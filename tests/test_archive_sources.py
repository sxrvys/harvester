from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.archive_sources import (
    ArchiveSourceError, normalize_instagram_saved_url, public_archives,
    remove_archive, rename_archive, save_archive, state_directory,
)


class ArchiveSourceTests(unittest.TestCase):
    def test_normalizes_only_instagram_saved_pages(self) -> None:
        self.assertEqual(
            normalize_instagram_saved_url("https://instagram.com/scott/saved/music/?token=no#part"),
            "https://www.instagram.com/scott/saved/music/",
        )
        for value in ("http://instagram.com/me/saved/", "https://example.com/me/saved/", "https://instagram.com/p/abc/"):
            with self.subTest(value=value), self.assertRaises(ArchiveSourceError):
                normalize_instagram_saved_url(value)

    def test_add_rename_remove_and_separate_state(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = save_archive(root, "Music", "https://www.instagram.com/me/saved/music/")
            self.assertEqual(public_archives(root)[0]["name"], "Music")
            self.assertEqual(rename_archive(root, archive["id"], "Samples")["name"], "Samples")
            self.assertEqual(state_directory(root, archive["id"]), root / "archives" / archive["id"])
            state_directory(root, archive["id"]).mkdir(parents=True)
            (state_directory(root, archive["id"]) / "saved-index.json").write_text("{}", encoding="utf-8")
            remove_archive(root, archive["id"])
            self.assertEqual(public_archives(root), [])
            self.assertFalse((root / "archives" / archive["id"]).exists())
