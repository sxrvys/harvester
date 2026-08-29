from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvest.instagram import POST_URL


class InstagramAdapterTests(unittest.TestCase):
    def test_accepts_post_and_reel_urls(self) -> None:
        self.assertEqual(POST_URL.fullmatch("https://www.instagram.com/p/DcSvEX4IWu7/").group(1), "DcSvEX4IWu7")
        self.assertEqual(POST_URL.fullmatch("https://instagram.com/reel/ABC_123-x/").group(1), "ABC_123-x")

    def test_rejects_collection_and_unrelated_urls(self) -> None:
        self.assertIsNone(POST_URL.fullmatch("https://www.instagram.com/saved/all-posts/"))
        self.assertIsNone(POST_URL.fullmatch("https://example.com/p/DcSvEX4IWu7/"))

