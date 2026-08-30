from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvest.instagram import POST_URL, audio_metadata_from_info


class InstagramAdapterTests(unittest.TestCase):
    def test_accepts_post_and_reel_urls(self) -> None:
        self.assertEqual(POST_URL.fullmatch("https://www.instagram.com/p/DcSvEX4IWu7/").group(1), "DcSvEX4IWu7")
        self.assertEqual(POST_URL.fullmatch("https://instagram.com/reel/ABC_123-x/").group(1), "ABC_123-x")
        self.assertEqual(POST_URL.fullmatch("https://www.instagram.com/reels/ABC_123-x/").group(1), "ABC_123-x")

    def test_rejects_collection_and_unrelated_urls(self) -> None:
        self.assertIsNone(POST_URL.fullmatch("https://www.instagram.com/saved/all-posts/"))
        self.assertIsNone(POST_URL.fullmatch("https://example.com/p/DcSvEX4IWu7/"))

    def test_preserves_named_song_metadata(self) -> None:
        self.assertEqual(
            audio_metadata_from_info({"track": "Roads", "artist": "Portishead"}),
            {
                "label": "Roads",
                "title": "Roads",
                "artist": "Portishead",
                "is_original": False,
            },
        )

    def test_original_audio_is_a_label_not_an_invented_song(self) -> None:
        self.assertEqual(
            audio_metadata_from_info({"audio_label": "Original audio"}),
            {
                "label": "Original audio",
                "title": None,
                "artist": None,
                "is_original": True,
            },
        )

    def test_missing_audio_metadata_has_predictable_shape(self) -> None:
        self.assertEqual(
            audio_metadata_from_info({}),
            {"label": None, "title": None, "artist": None, "is_original": False},
        )
