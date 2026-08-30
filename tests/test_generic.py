from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.generic import GenericMediaError, harvest_selected_media, safe_http_url, stable_page_url


class GenericMediaTests(unittest.TestCase):
    def test_rejects_loopback_and_private_destinations(self) -> None:
        for url in ("http://127.0.0.1/video.mp4", "http://localhost/video.mp4", "http://10.0.0.2/a.mp3"):
            with self.subTest(url=url), self.assertRaises(GenericMediaError) as raised:
                safe_http_url(url)
            self.assertEqual(raised.exception.code, "unsafe_url")

    def test_stable_page_url_removes_query_and_fragment(self) -> None:
        with patch("harvester.generic.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
            result = stable_page_url("https://example.com/watch?id=sensitive#part")
        self.assertEqual(result, "https://example.com/watch")

    def test_rejects_unknown_duration_before_download(self) -> None:
        with patch("harvester.generic.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]), patch(
            "harvester.generic._preflight", return_value={"url": "https://example.com/video.mp4", "filesize": 10}
        ):
            with self.assertRaises(GenericMediaError) as raised:
                harvest_selected_media(
                    "https://example.com/video.mp4", "https://example.com/page", Path("archive")
                )
        self.assertEqual(raised.exception.code, "unsupported_media")

    def test_rejects_over_limit_size_before_download(self) -> None:
        with patch("harvester.generic.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]), patch(
            "harvester.generic._preflight",
            return_value={"url": "https://example.com/video.mp4", "duration": 10, "filesize": 501},
        ):
            with self.assertRaises(GenericMediaError) as raised:
                harvest_selected_media(
                    "https://example.com/video.mp4",
                    "https://example.com/page",
                    Path("archive"),
                    max_source_bytes=500,
                )
        self.assertEqual(raised.exception.code, "size_limit")

    def test_success_builds_one_generic_item_without_persisting_media_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "archive"

            def download(_: str, output: Path, __: int) -> None:
                output.write_bytes(b"media")

            with patch("harvester.generic.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]), patch(
                "harvester.generic._preflight",
                return_value={
                    "url": "https://cdn.example.com/video.mp4?token=secret",
                    "filesize": 5,
                    "title": "Example clip",
                    "direct": True,
                },
            ), patch("harvester.generic._download_direct", side_effect=download), patch(
                "harvester.generic.probe", return_value={"format": {"duration": "12.0"}}
            ), patch("harvester.generic._build_bundle", return_value=archive / "example") as build:
                result = harvest_selected_media(
                    "https://cdn.example.com/video.mp4?token=secret",
                    "https://example.com/page?tracking=yes",
                    archive,
                )
        self.assertEqual(result, archive / "example")
        item = build.call_args.args[0]
        self.assertEqual(item.source, "generic")
        self.assertEqual(item.source_url, "https://example.com/page")
        self.assertNotIn("secret", str(item.source_metadata))


if __name__ == "__main__":
    unittest.main()
