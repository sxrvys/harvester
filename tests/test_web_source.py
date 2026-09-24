import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harvester.job_queue import JobQueue, identify
from harvester.web_source import public_page, validate_info, WebSourceError, harvest_web_url
from harvester.media import probe


class PublicPageTests(unittest.TestCase):
    def test_queue_is_offline_normalizes_tracking_and_separates_hosts(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.getaddrinfo", side_effect=AssertionError("enqueue must be offline")):
            queue = JobQueue(Path(directory))
            results = queue.add(["https://archive.org/details/chi_000108?utm_source=test:Old footage",
                                 "https://archive.org/details/chi_000108",
                                 "https://vimeo.com/12345", "https://soundcloud.com/artist/track"])
            self.assertEqual([r["status"] for r in results], ["added", "duplicate", "added", "added"])
            self.assertEqual(queue.snapshot()["jobs"][0]["name"], "Old footage")
            self.assertEqual(queue.snapshot()["jobs"][0]["input"], "https://archive.org/details/chi_000108")
            claimed = [queue.claim() for _ in range(3)]
            self.assertEqual(len({j["source"] for j in claimed}), 3)

    def test_private_credentials_tokens_and_known_site_collections_rejected(self):
        for url in ["https://example.org/clip?token=secret", "https://example.org/file?X-Amz-Signature=secret",
                    "http://127.0.0.1/file.mp4", "http://localhost/file", "http://media.local/file",
                    "https://user:pass@example.org/file", "file:///tmp/video.mp4",
                    "https://example.org/clip?list=all"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_page(url)
        with self.assertRaises(ValueError):
            identify("https://youtube.com/playlist?list=all")

    def test_collection_live_and_drm_metadata_do_not_download(self):
        for info in [{"entries": []}, {"_type": "multi_video"}, {"is_live": True},
                     {"live_status": "is_upcoming"}, {"has_drm": True}, {"duration": 3601},
                     {"filesize": 600 * 1024 * 1024}]:
            with self.subTest(info=info), self.assertRaises(WebSourceError):
                validate_info(info)

    def test_real_media_conversion_after_mock_public_acquisition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "source.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=12:duration=1",
                            "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264", "-c:a", "aac", str(fixture)], check=True)
            real_run = subprocess.run
            def metadata(command, **kwargs):
                if "--dump-single-json" in command:
                    self.assertIn("--ignore-config", command)
                    return subprocess.CompletedProcess(command, 0, json.dumps({"title": "Public clip", "duration": 1}), "")
                return real_run(command, **kwargs)
            def download(command):
                destination = Path(command[command.index("--output") + 1].replace("%(ext)s", "mp4"))
                shutil.copy2(fixture, destination)
                return subprocess.CompletedProcess(command, 0, "", "")
            with patch("harvester.generic.safe_http_url", side_effect=lambda value: value), \
                 patch("harvester.web_source.subprocess.run", side_effect=metadata), \
                 patch("harvester.progress.download", side_effect=download):
                bundle = harvest_web_url("https://media.example.org/clip", root / "out")
            records = json.loads((bundle / "metadata.json").read_text())["files"]
            self.assertEqual({r["role"] for r in records}, {"video", "audio"})
            for record in records:
                self.assertEqual(len(probe(bundle / record["path"])["streams"]), 1)

    def test_preflight_collection_never_calls_downloader(self):
        with tempfile.TemporaryDirectory() as directory, patch("harvester.generic.safe_http_url", side_effect=lambda value: value), \
             patch("harvester.web_source.subprocess.run", return_value=subprocess.CompletedProcess([], 0, '{"_type":"playlist","entries":[]}', '')), \
             patch("harvester.progress.download") as download:
            with self.assertRaises(WebSourceError):
                harvest_web_url("https://example.org/collection", Path(directory))
            download.assert_not_called()
