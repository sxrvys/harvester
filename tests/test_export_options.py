import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.export_options import normalize
from harvester.job_queue import JobQueue
from harvester.media import probe
from harvester.queue_runner import run_queue
from harvester.processing import progress_sink
from harvester.progress import download
from harvester.native_host import handle_message, ProtocolError


class ExportTests(unittest.TestCase):
    def test_invalid_ranges_are_rejected_without_queue_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = JobQueue(Path(directory))
            for options in ({"start": "nan"}, {"start": True}, {"end": -1}, {"end": "inf"},
                            {"start": 20, "end": 10}, {"end": 21601}, {"start": "1:99"},
                            {"video_preset": "shell"}, {"unknown": 0}):
                with self.assertRaises(ValueError):
                    queue.add(["https://youtu.be/abcdefghijk"], options=options)
            self.assertEqual(queue.snapshot()["jobs"], [])

    def test_options_define_variants_and_old_defaults_still_deduplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = JobQueue(Path(directory))
            url = "https://youtu.be/abcdefghijk"
            first = queue.add([url])[0]
            self.assertEqual(queue.add([url], options={"start": 0, "video_preset": "h264_all_keyframes"})[0]["job_id"], first["job_id"])
            clip = queue.add([url], options={"start": "0:01", "end": "0:02"})[0]
            self.assertNotEqual(clip["job_id"], first["job_id"])
            self.assertEqual(queue.add([url], options={"start": 1, "end": 2})[0]["job_id"], clip["job_id"])

    def test_real_trimmed_worker_outputs_matching_separate_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=24:duration=3",
                            "-f", "lavfi", "-i", "sine=duration=3", "-c:v", "libx264", "-c:a", "aac", str(source)], check=True)
            queue = JobQueue(root / "queue")
            queue.add([str(source)], options={"start": 0.5, "end": 1.5, "video_preset": "h264_small", "audio_preset": "flac_48k_24"})
            queue.add([str(source)], options={"start": 4, "end": 5})
            run_queue(queue.root, {"archive_root": str(root / "out"), "audio_preset": "wav_48k_24", "video_preset": "h264_all_keyframes"})
            complete, failed = queue.snapshot()["jobs"]
            self.assertEqual(complete["state"], "complete")
            files = list(Path(complete["output_path"]).iterdir())
            self.assertEqual({file.suffix for file in files}, {".mp4", ".flac"})
            for file in files:
                facts = probe(file)
                self.assertEqual(len(facts["streams"]), 1)
                self.assertAlmostEqual(float(facts["format"]["duration"]), 1, delta=0.05)
            self.assertEqual(complete["output_bytes"], sum(file.stat().st_size for file in files))
            self.assertEqual(failed["state"], "failed")
            self.assertIn("outside", failed["error"])
            self.assertTrue(source.exists())

    def test_progress_only_emits_numbers_and_safe_stage(self):
        records = []
        token = progress_sink.set(lambda stage, fraction: records.append((stage, fraction)))
        try:
            def fake_stream(command, consume):
                consume('harvester:{"downloaded_bytes": 25, "total_bytes":100,"filename":"secret"}')
                consume('harvester:{"downloaded_bytes": "NaN", "total_bytes":100}')
                return subprocess.CompletedProcess(command, 0, "", "")
            with patch("harvester.progress.stream", side_effect=fake_stream):
                download(["yt-dlp", "--no-progress", "https://example.test"])
        finally:
            progress_sink.reset(token)
        self.assertEqual(records, [("Downloading stream", 0.25)])

    def test_new_native_submission_validates_and_passes_queue_only(self):
        payload = {"url": "https://youtu.be/abcdefghijk", "name": "Night", "start": False, "options": {"start": 1, "end": 2}}
        with patch.dict("os.environ", {"HARVESTER_V2_APP": "/test.app"}):
            with patch("harvester.browser_bridge.submit", return_value={"state": "queued"}) as send:
                result = handle_message({"version": 1, "request_id": "test", "command": "enqueue_v2", "payload": payload})
                self.assertTrue(result["ok"])
                self.assertEqual(send.call_args.kwargs, {"name": "Night", "start": False, "options": {"start": 1, "end": 2}})
            with self.assertRaises(ProtocolError):
                handle_message({"version": 1, "request_id": "test", "command": "enqueue_v2", "payload": {**payload, "start": "false"}})
