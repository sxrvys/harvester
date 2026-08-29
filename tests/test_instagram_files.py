from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvest.instagram import _media_files


class InstagramFileTests(unittest.TestCase):
    def test_info_json_is_not_treated_as_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "01_item.info.json").write_text("{}", encoding="utf-8")
            image = root / "01_item.jpg"
            image.write_bytes(b"image")
            self.assertEqual(_media_files(root), [image])

