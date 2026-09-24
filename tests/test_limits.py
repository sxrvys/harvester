import unittest
from harvester.limits import Limits, acquisition_limits
from harvester.web_source import validate_info, WebSourceError
from harvester.export_options import normalize

class LimitTests(unittest.TestCase):
    def test_defaults_and_ceiling(self):
        self.assertEqual(Limits.from_settings({}), Limits(3600, 500 * 1024**2))
        Limits(21600, 5 * 1024**3)
        for duration, size in [(21601, 1), (0, 1), (True, 1), (60, 5 * 1024**3 + 1), (60, -1)]:
            with self.assertRaises(ValueError):
                Limits(duration, size)

    def test_source_limits_are_scoped_and_trim_does_not_bypass(self):
        with self.assertRaises(WebSourceError):
            validate_info({'duration': 3601})
        token = acquisition_limits.set(Limits(7200, 1024**3))
        try:
            validate_info({'duration': 7200, 'filesize': 1024**3})
            with self.assertRaises(WebSourceError):
                validate_info({'duration': 7201})
            with self.assertRaises(WebSourceError):
                validate_info({'filesize': 1024**3 + 1})
            self.assertEqual(normalize({'start': '1:30:00', 'end': '2:00:00'})['end'], 7200)
        finally:
            acquisition_limits.reset(token)
        with self.assertRaises(WebSourceError):
            validate_info({'duration': 3601})
