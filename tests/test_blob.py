import base64
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.blob import BlobSession
from harvester.generic import GenericMediaError, DEFAULT_MAX_SOURCE_BYTES
from harvester.native_host import handle_message, ProtocolError
from harvester.media import probe


class BlobTests(unittest.TestCase):
    def begin(self, session, size):
        with patch("harvester.blob.stable_page_url", return_value="https://example.com/clip"):
            return session.begin({"page_url": "https://example.com/clip?secret=omit", "size": size})

    def test_blob_transfer_produces_separated_media_and_cleans_source(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.webm"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                "testsrc2=size=96x64:rate=12:duration=0.5", "-f", "lavfi", "-i", "sine=duration=0.5",
                "-c:v", "libvpx-vp9", "-c:a", "libopus", str(source)], check=True)
            data = source.read_bytes()
            session = BlobSession()
            self.begin(session, len(data))
            staging = session.path.parent
            try:
                for offset in range(0, len(data), 1024):
                    session.append({"offset": offset, "data": base64.b64encode(data[offset:offset+1024]).decode()})
                result = session.finish(root / "archive", "wav_48k_24", "h264_all_keyframes")
                bundle = Path(result["output_path"])
                metadata = json.loads((bundle / "metadata.json").read_text())
                self.assertEqual(metadata["item"]["source_url"], "https://example.com/clip")
                self.assertNotIn("secret", json.dumps(metadata))
                self.assertEqual(sorted(f["role"] for f in metadata["files"]), ["audio", "video"])
                for record in metadata["files"]:
                    streams = probe(bundle / record["path"])["streams"]
                    self.assertEqual(len(streams), 1)
                    self.assertEqual(streams[0]["codec_type"], record["role"])
                self.assertFalse(staging.exists())
            finally:
                session.close()

    def test_limits_sequence_and_incomplete_transfer(self):
        session = BlobSession()
        for size in [0, -1, True, DEFAULT_MAX_SOURCE_BYTES + 1]:
            with self.assertRaises(GenericMediaError):
                self.begin(session, size)
        self.begin(session, 3)
        path = session.path
        try:
            for payload in [{"offset": 1, "data": "YQ=="}, {"offset": 0, "data": "??"},
                            {"offset": 0, "data": "YWJjZA=="}]:
                with self.assertRaises(GenericMediaError):
                    session.append(payload)
            self.assertEqual(path.stat().st_size, 0)
            session.append({"offset": 0, "data": "YQ=="})
            with self.assertRaises(GenericMediaError):
                session.finish(Path("unused"), "wav_48k_24", "h264_all_keyframes")
            self.assertFalse(path.exists())
        finally:
            session.close()

    def test_native_error_closes_transfer(self):
        session = BlobSession()
        self.begin(session, 4)
        path = session.path
        with self.assertRaises(ProtocolError):
            handle_message({"version": 1, "request_id": "test", "command": "blob_chunk",
                            "payload": {"offset": 99, "data": "YQ=="}}, blob_session=session)
        self.assertFalse(path.exists())

    def test_youtube_streaming_blob_uses_single_page_adapter(self):
        from harvester.native_host import _harvest_media_url
        url = "https://www.youtube.com/watch?v=NCxkLReX_YQ"
        with patch("harvester.native_host._harvest_url", return_value={"state": "complete"}) as harvest:
            result = _harvest_media_url({"media_url": "blob:https://www.youtube.com/example", "page_url": url},
                                        "test", Path("unused"))
        self.assertEqual(result["state"], "complete")
        harvest.assert_called_once_with({"url": url}, "test", Path("unused"))
