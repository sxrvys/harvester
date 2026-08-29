from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvest.batch import harvest_oldest


class BatchTests(unittest.TestCase):
    def test_rejects_delay_below_ten_seconds(self) -> None:
        with self.assertRaises(ValueError):
            harvest_oldest(Path("missing"), Path("state"), Path("profile"), Path("archive"), min_delay=9)

