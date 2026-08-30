"""Small, defensive Native Messaging boundary for the browser extension."""

from __future__ import annotations

import json
import struct
import sys
from dataclasses import dataclass
from typing import BinaryIO

from . import __version__

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1024 * 1024


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


def handle_message(message: dict[str, object]) -> dict[str, object]:
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
        return {
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "ok": True,
            "result": {
                "state": "ready",
                "application": "harvester",
                "application_version": __version__,
            },
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
