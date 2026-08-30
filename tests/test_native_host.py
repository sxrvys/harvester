from __future__ import annotations

import io
import json
import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.native_host import MAX_MESSAGE_BYTES, ProtocolError, handle_message, read_message, write_message


def framed(value: object) -> bytes:
    body = json.dumps(value).encode("utf-8")
    return struct.pack("<I", len(body)) + body


class NativeHostTests(unittest.TestCase):
    def test_get_status(self) -> None:
        with TemporaryDirectory() as temporary:
            response = handle_message(
                {"version": 1, "command": "get_status", "request_id": "abc", "payload": {}},
                settings_path=Path(temporary) / "missing.json",
            )
        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "abc")
        self.assertEqual(response["result"]["state"], "ready")
        self.assertFalse(response["result"]["configured"])

    def test_harvest_url_requires_configuration(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaises(ProtocolError) as raised:
                handle_message(
                    {
                        "version": 1,
                        "command": "harvest_url",
                        "request_id": "abc",
                        "payload": {"url": "https://www.instagram.com/p/Example/"},
                    },
                    settings_path=Path(temporary) / "missing.json",
                )
        self.assertEqual(raised.exception.code, "output_unavailable")

    def test_get_settings_returns_only_public_configuration(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "archive_root": "/output",
                    "firefox_profile": "/profile",
                    "cookie": "must-not-leak",
                }),
                encoding="utf-8",
            )
            response = handle_message(
                {"version": 1, "command": "get_settings", "request_id": "abc", "payload": {}},
                settings_path=path,
            )
        self.assertEqual(
            set(response["result"]), {"archive_root", "firefox_profile", "configured"}
        )
        self.assertNotIn("cookie", json.dumps(response).lower())

    def test_update_settings_validates_and_persists_private_file(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            profile = root / "profile"
            archive.mkdir()
            profile.mkdir()
            (profile / "cookies.sqlite").touch()
            path = root / "config" / "settings.json"
            response = handle_message(
                {
                    "version": 1,
                    "command": "update_settings",
                    "request_id": "abc",
                    "payload": {
                        "archive_root": str(archive),
                        "firefox_profile": str(profile),
                    },
                },
                settings_path=path,
            )
            persisted = json.loads(path.read_text(encoding="utf-8"))
            mode = path.stat().st_mode & 0o777
        self.assertTrue(response["result"]["configured"])
        self.assertEqual(persisted["archive_root"], str(archive.resolve()))
        self.assertEqual(mode, 0o600)

    def test_update_settings_rejects_unknown_fields(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaises(ProtocolError) as raised:
                handle_message(
                    {
                        "version": 1,
                        "command": "update_settings",
                        "request_id": "abc",
                        "payload": {
                            "archive_root": "/output",
                            "firefox_profile": "/profile",
                            "cookies": "secret",
                        },
                    },
                    settings_path=Path(temporary) / "settings.json",
                )
        self.assertEqual(raised.exception.code, "invalid_request")
        self.assertNotIn("secret", raised.exception.message)

    def test_open_output_folder_uses_configured_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            archive.mkdir()
            settings = root / "settings.json"
            settings.write_text(json.dumps({"archive_root": str(archive)}), encoding="utf-8")
            with patch("harvester.native_host.subprocess.run") as opened:
                response = handle_message(
                    {
                        "version": 1,
                        "command": "open_output_folder",
                        "request_id": "abc",
                        "payload": {},
                    },
                    settings_path=settings,
                )
        self.assertTrue(response["ok"])
        opened.assert_called_once_with(["open", str(archive)], check=True, capture_output=True)

    def test_selected_blob_media_fails_cleanly_without_configuration(self) -> None:
        with TemporaryDirectory() as temporary, self.assertRaises(ProtocolError) as raised:
            handle_message(
                {
                    "version": 1,
                    "command": "harvest_media_url",
                    "request_id": "abc",
                    "payload": {"media_url": "blob:https://example.com/id", "page_url": "https://example.com/"},
                },
                settings_path=Path(temporary) / "missing.json",
            )
        self.assertEqual(raised.exception.code, "unsupported_media")

    def test_harvest_media_url_dispatches_one_selection(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            archive.mkdir()
            settings = root / "settings.json"
            settings.write_text(json.dumps({"archive_root": str(archive)}), encoding="utf-8")
            destination = archive / "selected"
            with patch("harvester.generic.harvest_selected_media", return_value=destination) as harvest:
                response = handle_message(
                    {
                        "version": 1,
                        "command": "harvest_media_url",
                        "request_id": "abc",
                        "payload": {
                            "media_url": "https://cdn.example.com/video.mp4",
                            "page_url": "https://example.com/demo",
                        },
                    },
                    settings_path=settings,
                )
        self.assertTrue(response["ok"])
        harvest.assert_called_once_with(
            "https://cdn.example.com/video.mp4", "https://example.com/demo", archive
        )

    def test_harvest_url_rejects_unsupported_source_before_configuration(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaises(ProtocolError) as raised:
                handle_message(
                    {
                        "version": 1,
                        "command": "harvest_url",
                        "request_id": "abc",
                        "payload": {"url": "https://example.com/video"},
                    },
                    settings_path=Path(temporary) / "missing.json",
                )
        self.assertEqual(raised.exception.code, "unsupported_source")

    def test_harvest_url_rejects_instagram_collection_before_configuration(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaises(ProtocolError) as raised:
                handle_message(
                    {
                        "version": 1,
                        "command": "harvest_url",
                        "request_id": "abc",
                        "payload": {"url": "https://www.instagram.com/saved/"},
                    },
                    settings_path=Path(temporary) / "missing.json",
                )
        self.assertEqual(raised.exception.code, "invalid_url")

    def test_harvest_url_rejects_extra_payload_fields(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaises(ProtocolError) as raised:
                handle_message(
                    {
                        "version": 1,
                        "command": "harvest_url",
                        "request_id": "abc",
                        "payload": {"url": "https://www.instagram.com/p/Example/", "cookies": "secret"},
                    },
                    settings_path=Path(temporary) / "missing.json",
                )
        self.assertEqual(raised.exception.code, "invalid_request")
        self.assertNotIn("secret", raised.exception.message)

    def test_harvest_url_dispatches_configured_instagram_item(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            profile = root / "profile"
            destination = archive / "instagram_Example"
            archive.mkdir()
            profile.mkdir()
            (profile / "cookies.sqlite").touch()
            settings = root / "settings.json"
            settings.write_text(
                json.dumps({"archive_root": str(archive), "firefox_profile": str(profile)}),
                encoding="utf-8",
            )
            with patch("harvester.instagram.harvest_instagram_url", return_value=destination) as harvest:
                response = handle_message(
                    {
                        "version": 1,
                        "command": "harvest_url",
                        "request_id": "abc",
                        "payload": {"url": "https://www.instagram.com/p/Example/"},
                    },
                    settings_path=settings,
                )
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["output_path"], str(destination))
        harvest.assert_called_once_with(
            "https://www.instagram.com/p/Example/", profile, archive
        )

    def test_harvest_url_dispatches_one_youtube_watch_video(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            profile = root / "profile"
            destination = archive / "youtube_URwmZq70_DU"
            archive.mkdir()
            profile.mkdir()
            (profile / "cookies.sqlite").touch()
            settings = root / "settings.json"
            settings.write_text(
                json.dumps({"archive_root": str(archive), "firefox_profile": str(profile)}),
                encoding="utf-8",
            )
            with patch("harvester.youtube.harvest_youtube_url", return_value=destination) as harvest:
                response = handle_message(
                    {
                        "version": 1,
                        "command": "harvest_url",
                        "request_id": "abc",
                        "payload": {"url": "https://www.youtube.com/watch?v=URwmZq70_DU"},
                    },
                    settings_path=settings,
                )
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["source"], "youtube")
        harvest.assert_called_once_with(
            "https://www.youtube.com/watch?v=URwmZq70_DU", profile, archive
        )

    def test_harvest_url_rejects_youtube_playlist(self) -> None:
        with TemporaryDirectory() as temporary, self.assertRaises(ProtocolError) as raised:
            handle_message(
                {
                    "version": 1,
                    "command": "harvest_url",
                    "request_id": "abc",
                    "payload": {"url": "https://www.youtube.com/playlist?list=PL_example"},
                },
                settings_path=Path(temporary) / "missing.json",
            )
        self.assertEqual(raised.exception.code, "invalid_url")

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
