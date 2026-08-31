from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.reddit import POST_URL, RedditAcquisitionError, harvest_reddit_url


URL = "https://www.reddit.com/r/HolyShitHistory/comments/1uh1oty/in_1955_iranian_doctors_documented_the_days_of_a/"


class RedditTests(unittest.TestCase):
    def test_accepts_one_canonical_post_only(self) -> None:
        self.assertEqual(POST_URL.fullmatch(URL).group(1), "1uh1oty")
        self.assertIsNone(POST_URL.fullmatch("https://www.reddit.com/r/videos/"))
        self.assertIsNone(POST_URL.fullmatch("https://www.reddit.com/user/example/saved/"))
        self.assertIsNone(POST_URL.fullmatch(URL + "bjj4u9wxjt9h1/"))

    def test_download_is_bounded_and_uses_post_identity(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile"
            archive = root / "archive"
            profile.mkdir()
            archive.mkdir()
            (profile / "cookies.sqlite").touch()

            def download(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                staging = Path(command[command.index("--output") + 1]).parent
                (staging / "bjj4u9wxjt9h1.mp4").write_bytes(b"media")
                (staging / "bjj4u9wxjt9h1.info.json").write_text(json.dumps({
                    "id": "bjj4u9wxjt9h1", "duration": 156, "title": "Historic film",
                    "uploader": "example", "extractor": "Reddit",
                }), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            destination = archive / "historic-film_1uh1oty"
            with patch("harvester.reddit.subprocess.run", side_effect=download) as invoked, patch(
                "harvester.reddit._build_bundle", return_value=destination
            ) as build:
                result = harvest_reddit_url(URL, profile, archive)

        self.assertEqual(result, destination)
        command = invoked.call_args.args[0]
        self.assertIn("--no-playlist", command)
        self.assertEqual(command[command.index("--retries") + 1], "0")
        self.assertEqual(command[command.index("--fragment-retries") + 1], "0")
        item = build.call_args.args[0]
        self.assertEqual(item.source, "reddit")
        self.assertEqual(item.source_id, "1uh1oty")
        self.assertEqual(item.source_metadata["media_id"], "bjj4u9wxjt9h1")

    def test_rejects_multiple_downloaded_media_files(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile"
            archive = root / "archive"
            profile.mkdir()
            archive.mkdir()
            (profile / "cookies.sqlite").touch()

            def download(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                staging = Path(command[command.index("--output") + 1]).parent
                (staging / "one.mp4").write_bytes(b"one")
                (staging / "two.mp4").write_bytes(b"two")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("harvester.reddit.subprocess.run", side_effect=download), self.assertRaises(
                RedditAcquisitionError
            ):
                harvest_reddit_url(URL, profile, archive)


if __name__ == "__main__":
    unittest.main()
