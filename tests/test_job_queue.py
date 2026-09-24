import json
import fcntl
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.job_queue import JobQueue, identify
from harvester.queue_runner import run_queue


class JobQueueTests(unittest.TestCase):
    def test_runner_status_detects_a_supervisor_in_another_process_or_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = JobQueue(Path(temporary))
            self.assertFalse(queue.runner_active())
            with (queue.root / "runner.lock").open("a") as supervisor:
                fcntl.flock(supervisor, fcntl.LOCK_EX)
                self.assertTrue(JobQueue(queue.root).runner_active())
            self.assertFalse(queue.runner_active())

    def test_inline_names_are_per_line_and_do_not_change_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = JobQueue(Path(temporary))
            result = queue.add([
                "https://www.youtube.com/watch?v=NCxkLReX_YQ:Jim Jones Preaching In Los Angeles",
                "https://youtu.be/AAAAAAAAAAA : Empty shopping mall:Night",
                "https://www.youtube.com:443/watch?v=BBBBBBBBBBB:Metallic scraping",
                "https://instagram.com/p/Example/:Dance reference",
                "https://reddit.com/r/test/comments/abcdef/clip/:Street scene",
                "https://youtube.com/watch?v=CCCCCCCCCCC&tracking=https%3A%2F%2Fexample.com",
                "https://youtu.be/DDDDDDDDDDD:",
                "https://youtu.be/NCxkLReX_YQ:Different name",
            ])
            self.assertEqual([r["status"] for r in result], ["added"] * 7 + ["duplicate"])
            jobs = queue.snapshot()["jobs"]
            self.assertEqual([j["name"] for j in jobs], [
                "Jim Jones Preaching In Los Angeles", "Empty shopping mall-Night",
                "Metallic scraping", "Dance reference", "Street scene", None, None,
            ])
            self.assertEqual(jobs[0]["input"], "https://www.youtube.com/watch?v=NCxkLReX_YQ")

    def test_inline_parser_preserves_local_colons_and_cli_fallback_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "clip:night.mp4"
            source.touch()
            queue = JobQueue(root / "queue")
            result = queue.add([str(source), "https://youtu.be/AAAAAAAAAAA:Own name",
                                "https://youtu.be/BBBBBBBBBBB",
                                "https://user:secret@youtube.com/watch?v=CCCCCCCCCCC:Bad"], name="Fallback")
            self.assertEqual([r["status"] for r in result], ["added"] * 3 + ["rejected"])
            jobs = queue.snapshot()["jobs"]
            self.assertEqual(jobs[0]["input"], str(source.resolve()))
            self.assertEqual([j["name"] for j in jobs], ["Fallback", "Own name", "Fallback"])

    def test_downloads_overlap_across_sources_with_one_converter_and_live_enqueue(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.webm"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=96x64:rate=12:duration=1", "-c:v", "libvpx-vp9", str(source)], check=True)
            tools = root / "tools"
            tools.mkdir()
            downloader = tools / "yt-dlp"
            downloader.write_text('''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys, time
if '--version' in sys.argv:
    print('test-downloader')
    raise SystemExit(0)
with open(os.environ['QUEUE_TEST_LOG'], 'a') as log:
    log.write(json.dumps({'url': sys.argv[-1], 'started': time.time()}) + '\\n')
time.sleep(0.4)
target = pathlib.Path(sys.argv[sys.argv.index('--output') + 1]).parent
shutil.copyfile(os.environ['QUEUE_TEST_MEDIA'], target / 'fixture.webm')
(target / 'fixture.info.json').write_text(json.dumps({'duration': 1, 'title': 'Test clip'}))
''')
            downloader.chmod(0o755)
            queue = JobQueue(root / "state")
            queue.add(["https://youtube.com/watch?v=AAAAAAAAAAA", "https://youtube.com/watch?v=BBBBBBBBBBB"])
            errors = []
            def supervise():
                try:
                    run_queue(queue.root, {"archive_root": str(root / "output"),
                        "audio_preset": "wav_48k_24", "video_preset": "h264_all_keyframes"})
                except BaseException as error:
                    errors.append(error)
            with patch.dict(os.environ, {"PATH": str(tools) + os.pathsep + os.environ["PATH"],
                                         "QUEUE_TEST_LOG": str(root / "downloads.jsonl"), "QUEUE_TEST_MEDIA": str(source)}):
                thread = threading.Thread(target=supervise)
                thread.start()
                deadline = time.monotonic() + 15
                while not (root / "downloads.jsonl").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                # Submit while a different job is already in progress.
                queue.add(["https://www.reddit.com/r/test/comments/abcdef/clip/"])
                while thread.is_alive() and time.monotonic() < deadline:
                    self.assertLessEqual(sum(j["state"] == "converting" for j in queue.snapshot()["jobs"]), 1)
                    time.sleep(0.02)
                thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertFalse(errors)
            self.assertEqual([j["state"] for j in queue.snapshot()["jobs"]], ["complete"] * 3)
            events = [json.loads(line) for line in (root / "downloads.jsonl").read_text().splitlines()]
            self.assertIn('AAAAAAAAAAA', events[0]['url'])
            self.assertIn('reddit.com', events[1]['url'])
            self.assertLess(events[1]['started'] - events[0]['started'], 0.4)
            self.assertIn('BBBBBBBBBBB', events[2]['url'])

    def test_canonical_duplicates_and_partial_batch_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = JobQueue(Path(temporary))
            results = queue.add([
                "https://youtu.be/NCxkLReX_YQ?si=private-tracking",
                "https://www.youtube.com/watch?v=NCxkLReX_YQ&t=10",
                "https://youtube.com/playlist?list=abc", "not a link",
                "https://www.instagram.com/reel/Example/?igsh=secret",
            ])
            self.assertEqual([item["status"] for item in results],
                             ["added", "duplicate", "rejected", "rejected", "added"])
            journal = queue.path.read_text()
            self.assertNotIn("private-tracking", journal)
            self.assertNotIn("secret", journal)
            self.assertEqual(len(JobQueue(Path(temporary)).snapshot()["jobs"]), 2)
            self.assertEqual(queue.path.stat().st_mode & 0o777, 0o600)

    def test_concurrent_submissions_do_not_lose_jobs(self):
        with tempfile.TemporaryDirectory() as temporary:
            def add(index):
                return JobQueue(Path(temporary)).add([f"https://instagram.com/p/Post{index}/"])
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(add, range(40)))
            self.assertEqual(len(JobQueue(Path(temporary)).snapshot()["jobs"]), 40)

    def test_scheduler_source_isolation_recovery_cancel_and_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = JobQueue(Path(temporary))
            queue.add(["https://instagram.com/p/First/", "https://instagram.com/p/Second/",
                       "https://youtube.com/watch?v=NCxkLReX_YQ"])
            first, second = queue.claim(), queue.claim()
            self.assertEqual((first["source"], second["source"]), ("instagram", "youtube"))
            self.assertIsNone(queue.claim())
            queue.update(first["id"], first["token"], state="failed", pause_source=True)
            queue.recover()
            self.assertEqual(queue.get(second["id"])["state"], "interrupted")
            self.assertIsNone(queue.claim())
            queue.edit(second["id"], "retry")
            queue.edit(second["id"], "rename", "../A / new name")
            self.assertNotIn("/", queue.get(second["id"])["name"])
            queue.edit(second["id"], "cancel")
            self.assertEqual(queue.get(second["id"])["state"], "cancelled")
            queue.edit(second["id"], "retry")
            replacement = queue.claim()
            with self.assertRaises(ValueError):
                queue.update(second["id"], second["token"], state="complete")
            self.assertEqual(replacement["attempts"], 2)

    def test_credentials_and_playlists_rejected(self):
        for url in ["https://user:password@youtube.com/watch?v=NCxkLReX_YQ",
                    "https://youtube.com/watch?v=NCxkLReX_YQ&list=PLexample",
                    "https://youtube.com:9999/watch?v=NCxkLReX_YQ"]:
            with self.assertRaises(ValueError):
                identify(url)

    def test_real_workers_publish_named_video_and_audio_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.webm"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                "testsrc2=size=96x64:rate=12:duration=0.5", "-f", "lavfi", "-i", "sine=duration=0.5",
                "-c:v", "libvpx-vp9", "-c:a", "libopus", str(source)], check=True)
            second = root / "second.webm"
            second.write_bytes(source.read_bytes())
            queue = JobQueue(root / "state")
            queue.add([str(source), str(second)], name="Preacher gestures")
            run_queue(queue.root, {"archive_root": str(root / "output"),
                                  "audio_preset": "wav_48k_24", "video_preset": "h264_all_keyframes"})
            jobs = queue.snapshot()["jobs"]
            self.assertEqual([job["state"] for job in jobs], ["complete", "complete"])
            self.assertEqual({Path(job["output_path"]).name for job in jobs},
                             {"Preacher gestures", "Preacher gestures (2)"})
            for job in jobs:
                bundle = Path(job["output_path"])
                metadata = json.loads((queue.root / "receipts" / f"{job['id']}.json").read_text())
                self.assertFalse((bundle / "metadata.json").exists())
                self.assertEqual(metadata["harvester_job_id"], job["id"])
                self.assertEqual(sorted(f["role"] for f in metadata["files"]), ["audio", "video"])
                for file in metadata["files"]:
                    self.assertEqual(Path(file["path"]).name, file["path"])
                    self.assertTrue((bundle / file["path"]).is_file())
            self.assertTrue(source.exists())
            self.assertFalse(any(path.name.startswith(".harvester-") for path in (root / "output").iterdir()))

    def test_cancelled_job_stays_cancelled_and_retry_is_explicit(self):
        # No network access: use an empty source that fails before acquisition.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "empty.mp4"
            source.touch()
            queue = JobQueue(root / "state")
            added = queue.add([str(source)])[0]["job_id"]
            queue.edit(added, "cancel")
            run_queue(queue.root, {"archive_root": str(root / "output"),
                                  "audio_preset": "wav_48k_24", "video_preset": "h264_all_keyframes"})
            self.assertEqual(queue.get(added)["state"], "cancelled")
            queue.edit(added, "retry")
            run_queue(queue.root, {"archive_root": str(root / "output"),
                                  "audio_preset": "wav_48k_24", "video_preset": "h264_all_keyframes"})
            self.assertEqual(queue.get(added)["state"], "failed")
            self.assertNotIn(str(root), queue.get(added)["error"])
