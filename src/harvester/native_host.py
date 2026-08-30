"""Small, defensive Native Messaging boundary for the browser extension."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from . import __version__

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024
SETTINGS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProtocolError(Exception):
    code: str
    message: str
    request_id: str | None = None


def read_message(stream: BinaryIO) -> dict[str, object] | None:
    """Read one Native Messaging frame, returning None on clean EOF."""
    header = stream.read(4)
    if header == b"":
        return None
    if len(header) != 4:
        raise ProtocolError("invalid_request", "Incomplete message header")
    length = struct.unpack("<I", header)[0]
    if length == 0 or length > MAX_MESSAGE_BYTES:
        raise ProtocolError("invalid_request", "Message size is outside the allowed range")
    body = stream.read(length)
    if len(body) != length:
        raise ProtocolError("invalid_request", "Incomplete message body")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProtocolError("invalid_request", "Message must be valid UTF-8 JSON") from None
    if not isinstance(value, dict):
        raise ProtocolError("invalid_request", "Message must be a JSON object")
    return value


def write_message(stream: BinaryIO, message: dict[str, object]) -> None:
    body = json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_MESSAGE_BYTES:
        raise ProtocolError("processing_failed", "Response exceeds the safe message size")
    stream.write(struct.pack("<I", len(body)))
    stream.write(body)
    stream.flush()


def _settings_path() -> Path:
    override = os.environ.get("HARVESTER_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "harvester" / "settings.json"


def _read_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "archive_root": None,
            "firefox_profile": None,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ProtocolError("output_unavailable", "Local settings could not be read") from None
    if not isinstance(value, dict):
        raise ProtocolError("output_unavailable", "Local settings are invalid")
    return value


def _public_settings(settings: dict[str, object]) -> dict[str, object]:
    return {
        "archive_root": settings.get("archive_root"),
        "firefox_profile": settings.get("firefox_profile"),
        "configured": _settings_configured(settings),
    }


def _update_settings(path: Path, payload: dict[str, object], request_id: str) -> dict[str, object]:
    if set(payload) != {"archive_root", "firefox_profile"}:
        raise ProtocolError(
            "invalid_request",
            "update_settings requires output and Firefox profile paths",
            request_id,
        )
    archive_value = payload.get("archive_root")
    profile_value = payload.get("firefox_profile")
    if not all(isinstance(value, str) and value.strip() and len(value) <= 4096 for value in (archive_value, profile_value)):
        raise ProtocolError("invalid_request", "Settings paths must be non-empty strings", request_id)
    archive_root = Path(archive_value).expanduser().resolve()
    firefox_profile = Path(profile_value).expanduser().resolve()
    if not archive_root.is_dir():
        raise ProtocolError("output_unavailable", "The output folder does not exist", request_id)
    if not (firefox_profile / "cookies.sqlite").is_file():
        raise ProtocolError("output_unavailable", "The folder is not a Firefox profile", request_id)
    settings = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "archive_root": str(archive_root),
        "firefox_profile": str(firefox_profile),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return _public_settings(settings)


def _configured_path(settings: dict[str, object], key: str, request_id: str) -> Path:
    value = settings.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("output_unavailable", "Configure the local companion before harvesting", request_id)
    return Path(value).expanduser()


def _settings_configured(settings: dict[str, object]) -> bool:
    archive_value = settings.get("archive_root")
    profile_value = settings.get("firefox_profile")
    if not isinstance(archive_value, str) or not isinstance(profile_value, str):
        return False
    return Path(archive_value).expanduser().is_dir() and (
        Path(profile_value).expanduser() / "cookies.sqlite"
    ).is_file()


def _harvest_url(payload: dict[str, object], request_id: str, settings_path: Path) -> dict[str, object]:
    if set(payload) != {"url"}:
        raise ProtocolError("invalid_request", "harvest_url requires only a URL", request_id)
    url = payload.get("url")
    if not isinstance(url, str) or len(url) > 4096:
        raise ProtocolError("invalid_url", "URL must be a short HTTP(S) string", request_id)
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise ProtocolError("invalid_url", "URL is invalid", request_id) from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProtocolError("invalid_url", "Only HTTP(S) URLs are accepted", request_id)
    if parsed.hostname.casefold() not in {"instagram.com", "www.instagram.com"}:
        raise ProtocolError("unsupported_source", "This source is not supported yet", request_id)

    from .instagram import POST_URL

    if not POST_URL.fullmatch(url):
        raise ProtocolError("invalid_url", "Use one canonical Instagram post or reel URL", request_id)

    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    firefox_profile = _configured_path(settings, "firefox_profile", request_id)
    if not archive_root.is_dir():
        raise ProtocolError("output_unavailable", "The configured output folder is unavailable", request_id)
    if not (firefox_profile / "cookies.sqlite").is_file():
        raise ProtocolError("output_unavailable", "The configured Firefox profile is unavailable", request_id)

    from .instagram import AcquisitionError, harvest_instagram_url

    try:
        destination = harvest_instagram_url(url, firefox_profile, archive_root)
    except ValueError:
        raise ProtocolError("invalid_url", "Use one Instagram post or reel URL", request_id) from None
    except AcquisitionError as error:
        message = str(error).casefold()
        code = "authentication_stop" if "authentication" in message or "rate-limit" in message else "acquisition_failed"
        safe_message = "Instagram authorization stopped the harvest" if code == "authentication_stop" else "Instagram acquisition failed"
        raise ProtocolError(code, safe_message, request_id) from None
    except Exception:
        raise ProtocolError("processing_failed", "Harvest processing failed safely", request_id) from None
    state_root = archive_root.parent / "state"
    ledger_path = state_root / "item-ledger.json"
    if ledger_path.exists():
        from .ledger import record_completed_item

        record_completed_item(ledger_path, "instagram", parsed.path.rstrip("/").split("/")[-1], url, destination)
    return {"state": "complete", "source": "instagram", "output_path": str(destination)}


def _open_output_folder(request_id: str, settings_path: Path) -> dict[str, object]:
    settings = _read_settings(settings_path)
    archive_root = _configured_path(settings, "archive_root", request_id)
    if not archive_root.is_dir():
        raise ProtocolError("output_unavailable", "The configured output folder is unavailable", request_id)
    try:
        subprocess.run(["open", str(archive_root)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        raise ProtocolError("output_unavailable", "The output folder could not be opened", request_id) from None
    return {"state": "opened"}


def handle_message(
    message: dict[str, object], *, settings_path: Path | None = None
) -> dict[str, object]:
    request_id = message.get("request_id")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ProtocolError("invalid_request", "request_id must be a short non-empty string")
    if message.get("version") != PROTOCOL_VERSION:
        raise ProtocolError("invalid_request", "Unsupported protocol version", request_id)
    command = message.get("command")
    if not isinstance(command, str):
        raise ProtocolError("invalid_request", "command must be a string", request_id)
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_request", "payload must be an object", request_id)

    if command == "get_status":
        if payload:
            raise ProtocolError("invalid_request", "get_status payload must be empty", request_id)
        settings = _read_settings(settings_path or _settings_path())
        configured = _settings_configured(settings)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": {
                "state": "ready",
                "application": "harvester",
                "application_version": __version__,
                "configured": configured,
            },
        }
    if command == "get_settings":
        if payload:
            raise ProtocolError("invalid_request", "get_settings payload must be empty", request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": _public_settings(_read_settings(settings_path or _settings_path())),
        }
    if command == "update_settings":
        result = _update_settings(settings_path or _settings_path(), payload, request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    if command == "open_output_folder":
        if payload:
            raise ProtocolError("invalid_request", "open_output_folder payload must be empty", request_id)
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": _open_output_folder(request_id, settings_path or _settings_path()),
        }
    if command == "harvest_url":
        result = _harvest_url(payload, request_id, settings_path or _settings_path())
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": result,
        }
    raise ProtocolError("unsupported_command", "Command is not implemented", request_id)


def error_response(error: ProtocolError) -> dict[str, object]:
    return {
        "version": PROTOCOL_VERSION,
        "request_id": error.request_id,
        "ok": False,
        "error": {"code": error.code, "message": error.message},
    }


def main() -> int:
    input_stream = sys.stdin.buffer
    output_stream = sys.stdout.buffer
    while True:
        try:
            message = read_message(input_stream)
            if message is None:
                return 0
            response = handle_message(message)
        except ProtocolError as error:
            response = error_response(error)
        except Exception:
            # Native stdout is protocol-only. Never expose paths, commands,
            # downloader output, or exception details to the extension.
            response = error_response(ProtocolError("processing_failed", "Native companion failed safely"))
        write_message(output_stream, response)


if __name__ == "__main__":
    raise SystemExit(main())
