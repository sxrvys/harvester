from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.audio import AUDIO_PRESETS, extract_audio, get_audio_preset
from harvester.media import probe


class AudioPresetTests(unittest.TestCase):
    def test_five_fixed_presets(self) -> None:
        self.assertEqual(
            set(AUDIO_PRESETS),
            {"wav_48k_24", "wav_44k_16", "flac_48k_24", "mp3_320", "mp3_192"},
        )
        with self.assertRaises(ValueError):
            get_audio_preset("custom ffmpeg arguments")

    def test_each_preset_produces_expected_audio_contract(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.wav"
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=0.1",
                    "-ar", "48000", str(source),
                ],
                check=True,
            )
            expected = {
                "wav_48k_24": ("pcm_s24le", "48000", 24),
                "wav_44k_16": ("pcm_s16le", "44100", 16),
                "flac_48k_24": ("flac", "48000", 24),
                "mp3_320": ("mp3", "48000", None),
                "mp3_192": ("mp3", "48000", None),
            }
            for key, (codec, sample_rate, bit_depth) in expected.items():
                preset = get_audio_preset(key)
                destination = root / f"result-{key}{preset.extension}"
                extract_audio(source, destination, key)
                facts = probe(destination)
                stream = next(item for item in facts["streams"] if item["codec_type"] == "audio")
                self.assertEqual(stream["codec_name"], codec)
                self.assertEqual(stream["sample_rate"], sample_rate)
                self.assertEqual(stream["channels"], 2)
                if bit_depth is not None:
                    actual = stream.get("bits_per_raw_sample") or stream.get("bits_per_sample")
                    self.assertEqual(int(actual), bit_depth)


if __name__ == "__main__":
    unittest.main()
