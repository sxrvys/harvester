from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.local_file import harvest_local_file
from harvester.audit import audit_archive
from harvester.media import probe
from harvester.native_host import handle_message, ProtocolError
from harvester.video import VIDEO_PRESETS, transcode_video


class VideoTests(unittest.TestCase):
    def make_source(self, root, audio=True):
        source = root / ("audio.webm" if audio else "silent.webm")
        command = ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                   "testsrc2=size=96x64:rate=12:duration=1"]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=duration=1", "-c:a", "libopus"]
        subprocess.run([*command, "-c:v", "libvpx-vp9", str(source)], check=True, capture_output=True)
        return source

    def test_vp9_bundle_splits_streams_without_retaining_source(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.make_source(root)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            for preset in VIDEO_PRESETS:
                archive = root / preset
                archive.mkdir()
                bundle = harvest_local_file(source, archive, video_preset=preset)
                metadata = json.loads((bundle / "metadata.json").read_text())
                self.assertFalse((bundle / "original").exists())
                self.assertFalse(any(f["role"] == "original" for f in metadata["files"]))
                self.assertEqual(metadata["source_retention"], "derivatives_only")
                video = next(f for f in metadata["files"] if f["role"] == "video")
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)
                path = bundle / video["path"]
                self.assertEqual(path.suffix, ".mp4")
                facts = probe(path)
                streams = {s["codec_type"]: s for s in facts["streams"]}
                self.assertEqual(streams["video"]["codec_name"], "h264")
                self.assertEqual(streams["video"]["pix_fmt"], "yuv420p")
                self.assertNotIn("audio", streams)
                audio = next(f for f in metadata["files"] if f["role"] == "audio")
                audio_streams = probe(bundle / audio["path"])["streams"]
                self.assertEqual(len(audio_streams), 1)
                self.assertEqual(audio_streams[0]["codec_type"], "audio")
                self.assertEqual(audio_streams[0]["codec_name"], "pcm_s24le")
                self.assertEqual(len(metadata["files"]), 2)
                self.assertEqual(audit_archive(archive)["summary"]["errors"], 0)
                self.assertEqual(video["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(video["encoding"]["preset"], preset)
                self.assertNotIn(str(root), json.dumps(video))
                self.assertAlmostEqual(float(facts["format"]["duration"]), 1, delta=0.1)
                frames = json.loads(subprocess.check_output([
                    "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
                    "-show_entries", "frame=key_frame", "-of", "json", str(path),
                ]))["frames"]
                self.assertEqual(len(frames), 12)
                self.assertEqual(all(f["key_frame"] == 1 for f in frames), preset.endswith("all_keyframes"))
                # Repeating the same operation must not produce extra video copies.
                harvest_local_file(source, archive, video_preset=preset)
                self.assertEqual(len(list((archive / "video").glob("*.mp4"))), 1)

    def test_silent_video_stays_silent(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "result.mp4"
            transcode_video(self.make_source(root, audio=False), destination)
            self.assertEqual([s["codec_type"] for s in probe(destination)["streams"]], ["video"])

    def test_failure_cleans_partial_output_and_existing_media_is_protected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, destination = root / "source.mp4", root / "output.mp4"
            source.write_bytes(b"original")
            destination.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                transcode_video(source, destination)
            self.assertEqual(destination.read_bytes(), b"keep")
            destination.unlink()
            def fail(*args, **kwargs):
                destination.write_bytes(b"partial")
                raise subprocess.CalledProcessError(1, "ffmpeg")
            with patch("harvester.video.subprocess.run", side_effect=fail), self.assertRaises(subprocess.CalledProcessError):
                transcode_video(source, destination)
            self.assertFalse(destination.exists())
            self.assertEqual(source.read_bytes(), b"original")

    def test_video_settings_round_trip_legacy_client_and_validation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile"
            profile.mkdir()
            (profile / "cookies.sqlite").touch()
            settings = root / "settings.json"
            payload = {"archive_root": str(root), "firefox_profile": str(profile),
                       "video_preset": "h264_all_keyframes"}
            def send(command, data):
                return handle_message({"version": 1, "request_id": "test", "command": command,
                                       "payload": data}, settings_path=settings)["result"]
            self.assertEqual(send("update_settings", payload)["video_preset"], payload["video_preset"])
            self.assertEqual(send("get_settings", {})["video_preset"], payload["video_preset"])
            payload.pop("video_preset")
            self.assertEqual(send("update_settings", payload)["video_preset"], "h264_all_keyframes")
            before = settings.read_bytes()
            for invalid in (False, {}, "custom"):
                with self.assertRaises(ProtocolError):
                    send("update_settings", {**payload, "video_preset": invalid})
                self.assertEqual(settings.read_bytes(), before)
