from __future__ import annotations

import io
import json
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harvester.native_host import (
    MAX_MESSAGE_BYTES, ProtocolError, _detect_firefox_profile,
    handle_message, read_message, write_message,
)


def framed(value: object) -> bytes:
    body = json.dumps(value).encode("utf-8")
    return struct.pack("<I", len(body)) + body


class NativeHostTests(unittest.TestCase):
    def test_detects_firefox_declared_default_profile(self) -> None:
        with TemporaryDirectory() as temporary:
            home = Path(temporary)
            firefox = home / "Library" / "Application Support" / "Firefox"
            preferred = firefox / "Profiles" / "chosen.default-release"
            other = firefox / "Profiles" / "other.default"
            preferred.mkdir(parents=True)
            other.mkdir(parents=True)
            (preferred / "cookies.sqlite").touch()
            (other / "cookies.sqlite").touch()
            (firefox / "profiles.ini").write_text(
                "[InstallABC]\nDefault=Profiles/chosen.default-release\nLocked=1\n\n"
                "[Profile0]\nName=other\nIsRelative=1\nPath=Profiles/other.default\n\n"
                "[Profile1]\nName=chosen\nIsRelative=1\nPath=Profiles/chosen.default-release\nDefault=1\n",
                encoding="utf-8",
            )
            with patch("harvester.native_host.Path.home", return_value=home):
                detected = _detect_firefox_profile()
        self.assertEqual(detected, preferred.resolve())

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
            set(response["result"]), {"archive_root", "firefox_profile", "audio_preset", "configured"}
        )
        self.assertEqual(response["result"]["audio_preset"], "wav_48k_24")
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
        self.assertEqual(persisted["audio_preset"], "wav_48k_24")
        self.assertEqual(mode, 0o600)

    def test_update_settings_accepts_only_named_audio_preset(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            profile = root / "profile"
            archive.mkdir()
            profile.mkdir()
            (profile / "cookies.sqlite").touch()
            path = root / "settings.json"
            response = handle_message(
                {
                    "version": 1,
                    "command": "update_settings",
                    "request_id": "abc",
                    "payload": {
                        "archive_root": str(archive),
                        "firefox_profile": str(profile),
                        "audio_preset": "mp3_320",
                    },
                },
                settings_path=path,
            )
            persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(response["result"]["audio_preset"], "mp3_320")
        self.assertEqual(persisted["audio_preset"], "mp3_320")

        with self.assertRaises(ProtocolError) as raised:
            handle_message(
                {
                    "version": 1,
                    "command": "update_settings",
                    "request_id": "def",
                    "payload": {
                        "archive_root": str(archive),
                        "firefox_profile": str(profile),
                        "audio_preset": "-ar 999999 arbitrary arguments",
                    },
                },
                settings_path=path,
            )
        self.assertEqual(raised.exception.code, "invalid_request")

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

    def test_choose_output_folder_returns_only_selected_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            selected = Path(temporary)
            completed = subprocess.CompletedProcess([], 0, f"{selected}\n", "")
            with patch("harvester.native_host.subprocess.run", return_value=completed) as picker:
                response = handle_message(
                    {
                        "version": 1,
                        "command": "choose_output_folder",
                        "request_id": "abc",
                        "payload": {},
                    }
                )
        self.assertTrue(response["result"]["selected"])
        self.assertEqual(response["result"]["path"], str(selected.resolve()))
        self.assertEqual(picker.call_args.args[0][:2], ["osascript", "-e"])

    def test_local_file_picker_keeps_selected_path_inside_native_companion(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            selected = root / "private" / "clip.mp4"
            destination = archive / "clip_hash"
            archive.mkdir()
            selected.parent.mkdir()
            selected.touch()
            settings = root / "settings.json"
            settings.write_text(json.dumps({
                "archive_root": str(archive), "audio_preset": "flac_48k_24",
            }), encoding="utf-8")
            picker = subprocess.CompletedProcess([], 0, f"{selected}\n", "")
            with patch("harvester.native_host.subprocess.run", return_value=picker), patch(
                "harvester.local_file.harvest_local_file", return_value=destination
            ) as harvest:
                response = handle_message(
                    {"version": 1, "command": "harvest_local_file", "request_id": "abc", "payload": {}},
                    settings_path=settings,
                )
        self.assertEqual(response["result"], {
            "state": "complete", "source": "local", "output_path": str(destination),
        })
        self.assertNotIn(str(selected), json.dumps(response))
        harvest.assert_called_once_with(selected, archive, "flac_48k_24")

    def test_local_file_picker_cancellation_is_clean(self) -> None:
        cancelled = subprocess.CompletedProcess([], 1, "", "User canceled")
        with patch("harvester.native_host.subprocess.run", return_value=cancelled):
            response = handle_message(
                {"version": 1, "command": "harvest_local_file", "request_id": "abc", "payload": {}}
            )
        self.assertEqual(response["result"], {"state": "cancelled"})

    def test_archival_status_reads_private_index_and_ledger(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "saved-index.json").write_text(json.dumps({
                "complete": True, "count": 12, "last_incremental_sync_at": "now",
                "last_incremental_sync": {"new_count": 2, "boundary": "known-streak"},
            }), encoding="utf-8")
            (root / "item-ledger.json").write_text(json.dumps({
                "summary": {"total": 12, "discovered": 7, "complete": 5},
            }), encoding="utf-8")
            with patch.dict("os.environ", {"HARVESTER_STATE_ROOT": str(root)}):
                response = handle_message(
                    {"version": 1, "command": "get_archival_status", "request_id": "abc", "payload": {}},
                    settings_path=root / "missing-settings.json",
                )
        self.assertEqual(response["result"]["indexed"], 12)
        self.assertEqual(response["result"]["summary"]["discovered"], 7)
        self.assertEqual(response["result"]["last_scan"]["new_count"], 2)

    def test_archival_batch_rejects_unsafe_controls_before_configuration(self) -> None:
        invalid_payloads = (
            {"count": 0, "min_delay": 10, "max_delay": 15},
            {"count": 26, "min_delay": 10, "max_delay": 15},
            {"count": 10, "min_delay": 9, "max_delay": 15},
            {"count": 10, "min_delay": 20, "max_delay": 15},
            {"count": 10, "min_delay": 10, "max_delay": 301},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ProtocolError) as raised:
                handle_message({
                    "version": 1, "command": "harvest_archival_batch",
                    "request_id": "abc", "payload": payload,
                })
            self.assertEqual(raised.exception.code, "invalid_request")

    def test_saved_scan_command_dispatches_only_after_explicit_message(self) -> None:
        expected = {"state": "complete", "scan": {"new_count": 1}, "summary": {"total": 2}}
        with patch("harvester.native_host._scan_saved", return_value=expected) as scan:
            response = handle_message(
                {"version": 1, "command": "scan_saved_posts", "request_id": "abc", "payload": {}}
            )
        self.assertEqual(response["result"], expected)
        scan.assert_called_once()

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
            "https://cdn.example.com/video.mp4", "https://example.com/demo", archive,
            audio_preset="wav_48k_24",
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
            "https://www.instagram.com/p/Example/", profile, archive,
            audio_preset="wav_48k_24",
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
            "https://www.youtube.com/watch?v=URwmZq70_DU", profile, archive, "wav_48k_24"
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

    def test_harvest_url_dispatches_one_reddit_post(self) -> None:
        url = "https://www.reddit.com/r/HolyShitHistory/comments/1uh1oty/in_1955_iranian_doctors_documented_the_days_of_a/"
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            profile = root / "profile"
            destination = archive / "historic-film_1uh1oty"
            archive.mkdir()
            profile.mkdir()
            (profile / "cookies.sqlite").touch()
            settings = root / "settings.json"
            settings.write_text(
                json.dumps({"archive_root": str(archive), "firefox_profile": str(profile)}),
                encoding="utf-8",
            )
            with patch("harvester.reddit.harvest_reddit_url", return_value=destination) as harvest:
                response = handle_message(
                    {"version": 1, "command": "harvest_url", "request_id": "abc", "payload": {"url": url}},
                    settings_path=settings,
                )
        self.assertEqual(response["result"]["source"], "reddit")
        harvest.assert_called_once_with(url, profile, archive, "wav_48k_24")

    def test_harvest_url_rejects_reddit_feed(self) -> None:
        with TemporaryDirectory() as temporary, self.assertRaises(ProtocolError) as raised:
            handle_message(
                {
                    "version": 1,
                    "command": "harvest_url",
                    "request_id": "abc",
                    "payload": {"url": "https://www.reddit.com/r/HolyShitHistory/"},
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
