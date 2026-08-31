from __future__ import annotations

import sys
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.local_file import LocalFileError, harvest_local_file
from harvester.instagram import _metadata_probe


class LocalFileTests(unittest.TestCase):
    def test_metadata_probe_removes_local_filename(self) -> None:
        private_path = "/Users/someone/Downloads/private-video.mp4"
        facts = {
            "format": {"filename": private_path, "duration": "12.5"},
            "streams": [{"codec_type": "video"}],
        }

        sanitized = _metadata_probe(facts)

        self.assertNotIn(private_path, json.dumps(sanitized))
        self.assertEqual(sanitized["format"]["duration"], "12.5")
        self.assertEqual(facts["format"]["filename"], private_path)

    def test_one_file_builds_content_identified_item_without_original_path(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / "private" / "personal" / "DuckandC1951.mp4"
            private.parent.mkdir(parents=True)
            private.write_bytes(b"local media bytes")
            archive = root / "archive"
            archive.mkdir()
            destination = archive / "duckandc1951_abc"
            facts = {
                "format": {"duration": "555.0"},
                "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
            }
            with patch("harvester.local_file.probe", return_value=facts), patch(
                "harvester.local_file._build_bundle", return_value=destination
            ) as build:
                result = harvest_local_file(private, archive, "mp3_320")
        self.assertEqual(result, destination)
        item, media_files, passed_archive, preset = build.call_args.args
        self.assertEqual(item.source, "local")
        self.assertIsNone(item.source_url)
        self.assertEqual(item.source_metadata["original_filename"], "DuckandC1951.mp4")
        self.assertNotIn("private", str(item.source_metadata))
        self.assertNotIn(str(root), str(item.source_metadata))
        self.assertEqual(media_files, [private.resolve()])
        self.assertEqual(passed_archive, archive)
        self.assertEqual(preset, "mp3_320")

    def test_rejects_directory_and_over_limit_file_before_probe(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(LocalFileError) as directory_error:
                harvest_local_file(root, root)
            self.assertEqual(directory_error.exception.code, "invalid_file")
            source = root / "large.mp4"
            source.write_bytes(b"12345")
            with patch("harvester.local_file.probe") as probe, self.assertRaises(LocalFileError) as size_error:
                harvest_local_file(source, root, max_source_bytes=4)
            self.assertEqual(size_error.exception.code, "size_limit")
            probe.assert_not_called()

    def test_rejects_unsupported_or_over_duration_media(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "clip.bin"
            source.write_bytes(b"content")
            with patch("harvester.local_file.probe", return_value={"format": {"duration": "1"}, "streams": []}), self.assertRaises(LocalFileError) as unsupported:
                harvest_local_file(source, root)
            self.assertEqual(unsupported.exception.code, "unsupported_media")
            facts = {"format": {"duration": "601"}, "streams": [{"codec_type": "video"}]}
            with patch("harvester.local_file.probe", return_value=facts), self.assertRaises(LocalFileError) as duration:
                harvest_local_file(source, root)
            self.assertEqual(duration.exception.code, "duration_limit")


if __name__ == "__main__":
    unittest.main()
