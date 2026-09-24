"""Bounded browser-to-companion transfer of one selected, readable media Blob."""

from __future__ import annotations

import base64
import binascii
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .generic import DEFAULT_MAX_DURATION_SECONDS, DEFAULT_MAX_SOURCE_BYTES, GenericMediaError, _probe_duration, stable_page_url
from .instagram import _build_bundle
from .media import probe
from .model import HarvestItem

CHUNK_BYTES = 192 * 1024


class BlobSession:
    def __init__(self):
        self.temporary = None
        self.received = 0

    def close(self):
        if self.temporary:
            self.temporary.cleanup()
        self.temporary = None
        self.received = 0

    def begin(self, payload):
        if self.temporary:
            raise GenericMediaError("invalid_request", "A media transfer is already active")
        size = payload.get("size")
        if type(size) is not int or not 0 < size <= DEFAULT_MAX_SOURCE_BYTES:
            raise GenericMediaError("size_limit", "Selected blob exceeds 500 MB or has no known size")
        self.page_url = stable_page_url(payload.get("page_url"))
        self.expected = size
        self.temporary = tempfile.TemporaryDirectory(prefix="harvester-blob-")
        self.path = Path(self.temporary.name) / "selected.media"
        self.path.touch(mode=0o600)
        return {"state": "receiving"}

    def append(self, payload):
        if not self.temporary:
            raise GenericMediaError("invalid_request", "No media transfer is active")
        encoded = payload.get("data")
        if (type(payload.get("offset")) is not int or payload["offset"] != self.received
                or not isinstance(encoded, str) or not 0 < len(encoded) <= CHUNK_BYTES * 4 // 3):
            raise GenericMediaError("invalid_request", "Invalid or out-of-order media chunk")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise GenericMediaError("invalid_request", "Invalid media chunk") from None
        if not data or self.received + len(data) > self.expected:
            raise GenericMediaError("size_limit", "Media transfer exceeds its declared size")
        with self.path.open("ab") as handle:
            handle.write(data)
        self.received += len(data)
        return {"received": self.received}

    def finish(self, archive_root, audio_preset, video_preset):
        try:
            if not self.temporary or self.received != self.expected:
                raise GenericMediaError("invalid_request", "Media transfer is incomplete")
            facts = probe(self.path)
            duration = _probe_duration(facts)
            if duration is None or duration > DEFAULT_MAX_DURATION_SECONDS:
                raise GenericMediaError("duration_limit", "Selected blob must have a duration of at most 60 minutes")
            digest = hashlib.sha256(self.page_url.encode())
            with self.path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            item = HarvestItem(
                source="generic", source_id=digest.hexdigest()[:16],
                source_url=self.page_url, retrieved_at=datetime.now(timezone.utc),
                title="selected-media", source_metadata={"selection": "visible-media-blob"},
            )
            destination = _build_bundle(item, [self.path], archive_root, audio_preset, video_preset=video_preset)
            return {"state": "complete", "output_path": str(destination)}
        finally:
            self.close()
