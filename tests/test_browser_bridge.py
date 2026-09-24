import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.browser_bridge import submit
from harvester.job_queue import JobQueue
from harvester.native_host import ProtocolError, handle_message


class BrowserBridgeTests(unittest.TestCase):
    def test_missing_app_does_not_enqueue(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ProtocolError):
                submit("https://youtu.be/NCxkLReX_YQ", root / "missing.app", root / "queue")
            self.assertFalse((root / "queue").exists())

    def test_handoff_is_durable_deduplicated_and_contains_no_url(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "App.app/Contents/MacOS/Harvester"
            binary.parent.mkdir(parents=True)
            binary.touch()
            with patch("harvester.browser_bridge.subprocess.run") as launch:
                first = submit("https://youtu.be/NCxkLReX_YQ", root / "App.app", root / "queue")
                second = submit("https://www.youtube.com/watch?v=NCxkLReX_YQ", root / "App.app", root / "queue")
                self.assertEqual(launch.call_args.args[0][-1], "harvester://queue/harvest")
            self.assertEqual(first["job_id"], second["job_id"])
            self.assertTrue(second["duplicate"])
            self.assertEqual(len(JobQueue(root / "queue").snapshot()["jobs"]), 1)
            with patch("harvester.browser_bridge.subprocess.run", side_effect=subprocess.TimeoutExpired("open", 15)):
                with self.assertRaises(ProtocolError):
                    submit("https://youtu.be/abcdefghijk", root / "App.app", root / "queue")
            self.assertEqual(len(JobQueue(root / "queue").snapshot()["jobs"]), 2)
            with self.assertRaises(ProtocolError):
                submit(str(binary), root / "App.app", root / "queue")

    def test_native_protocol_routes_without_reading_browser_profile(self):
        with patch.dict("os.environ", {"HARVESTER_V2_APP": "/Applications/Harvester.app"}):
            with patch("harvester.browser_bridge.submit", return_value={"state": "queued"}) as send:
                with patch("harvester.native_host._read_settings", side_effect=AssertionError("No cookie settings needed")):
                    result = handle_message({"version": 1, "request_id": "test", "command": "harvest_url",
                                             "payload": {"url": "https://youtu.be/NCxkLReX_YQ"}})
                self.assertTrue(result["ok"])
                send.assert_called_once()
