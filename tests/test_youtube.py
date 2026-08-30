from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.youtube import WATCH_URL, YouTubeAcquisitionError, harvest_youtube_url


class YouTubeTests(unittest.TestCase):
    def test_accepts_one_watch_url_only(self) -> None:
        self.assertIsNotNone(WATCH_URL.fullmatch("https://www.youtube.com/watch?v=URwmZq70_DU"))
        self.assertIsNone(WATCH_URL.fullmatch("https://www.youtube.com/playlist?list=PL_example"))
        self.assertIsNone(WATCH_URL.fullmatch("https://www.youtube.com/@example/videos"))
        self.assertIsNone(WATCH_URL.fullmatch("https://youtu.be/URwmZq70_DU"))

    def test_download_is_bounded_to_one_video(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile"
            archive = root / "archive"
            profile.mkdir()
            archive.mkdir()
            (profile / "cookies.sqlite").touch()

            def download(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                staging = Path(command[command.index("--output") + 1]).parent
                (staging / "URwmZq70_DU.mp4").write_bytes(b"media")
                (staging / "URwmZq70_DU.info.json").write_text(json.dumps({
                    "id": "URwmZq70_DU", "duration": 487, "title": "Training Film",
                    "uploader": "US National Archives", "extractor": "youtube",
                }), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            destination = archive / "youtube_URwmZq70_DU"
            with patch("harvester.youtube.subprocess.run", side_effect=download) as invoked, patch(
                "harvester.youtube._build_bundle", return_value=destination
            ) as build:
                result = harvest_youtube_url(
                    "https://www.youtube.com/watch?v=URwmZq70_DU", profile, archive
                )

        self.assertEqual(result, destination)
        command = invoked.call_args.args[0]
        self.assertIn("--no-playlist", command)
        self.assertNotIn("--max-downloads", command)
        self.assertEqual(command[command.index("--fragment-retries") + 1], "0")
        item = build.call_args.args[0]
        self.assertEqual(item.source, "youtube")
        self.assertEqual(item.source_id, "URwmZq70_DU")

    def test_rejects_over_duration_before_archival(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile"
            archive = root / "archive"
            profile.mkdir()
            archive.mkdir()
            (profile / "cookies.sqlite").touch()

            def download(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                staging = Path(command[command.index("--output") + 1]).parent
                (staging / "URwmZq70_DU.mp4").write_bytes(b"media")
                (staging / "URwmZq70_DU.info.json").write_text(
                    json.dumps({"duration": 601}), encoding="utf-8"
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("harvester.youtube.subprocess.run", side_effect=download), self.assertRaises(
                YouTubeAcquisitionError
            ) as raised:
                harvest_youtube_url(
                    "https://www.youtube.com/watch?v=URwmZq70_DU", profile, archive
                )
        self.assertIn("duration", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
