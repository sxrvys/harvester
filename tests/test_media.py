from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.media import extract_wav, has_audio, probe


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools required")
class MediaTests(unittest.TestCase):
    def test_wav_derivative_matches_v0_audio_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.wav"
            destination = root / "audio.wav"
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=0.05", str(source),
                ],
                check=True,
            )

            extract_wav(source, destination)
            result = probe(destination)
            audio = next(stream for stream in result["streams"] if stream["codec_type"] == "audio")
            self.assertTrue(has_audio(result))
            self.assertEqual(audio["codec_name"], "pcm_s24le")
            self.assertEqual(audio["sample_rate"], "48000")
            self.assertEqual(audio["channels"], 2)

