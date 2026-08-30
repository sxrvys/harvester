from __future__ import annotations

import io
import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.native_host import MAX_MESSAGE_BYTES, ProtocolError, handle_message, read_message, write_message


def framed(value: object) -> bytes:
    body = json.dumps(value).encode("utf-8")
    return struct.pack("<I", len(body)) + body


class NativeHostTests(unittest.TestCase):
    def test_get_status(self) -> None:
        response = handle_message(
            {"version": 1, "command": "get_status", "request_id": "abc", "payload": {}}
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "abc")
        self.assertEqual(response["result"]["state"], "ready")

    def test_unknown_command_is_sanitized(self) -> None:
        with self.assertRaises(ProtocolError) as raised:
            handle_message(
                {"version": 1, "command": "read_cookies", "request_id": "abc", "payload": {}}
            )
        self.assertEqual(raised.exception.code, "unsupported_command")
        self.assertNotIn("cookie", raised.exception.message.lower())

    def test_rejects_unbounded_frame_before_reading_body(self) -> None:
        stream = io.BytesIO(struct.pack("<I", MAX_MESSAGE_BYTES + 1))
        with self.assertRaises(ProtocolError):
            read_message(stream)

    def test_rejects_non_object_json(self) -> None:
        with self.assertRaises(ProtocolError):
            read_message(io.BytesIO(framed(["not", "an", "object"])))

    def test_round_trip_frame(self) -> None:
        stream = io.BytesIO()
        message = {"version": 1, "request_id": "abc", "ok": True, "result": {}}
        write_message(stream, message)
        stream.seek(0)
        self.assertEqual(read_message(stream), message)


if __name__ == "__main__":
    unittest.main()
