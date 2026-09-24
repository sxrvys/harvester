"""Local v2 queue journal. Enqueueing never starts network or account access."""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ACTIVE = {"downloading", "waiting_to_convert", "converting", "saving"}
RETRYABLE = {"failed", "cancelled", "interrupted"}


def identify(value: str) -> tuple[str, str, str]:
    """Normalize only explicitly supported single items; discard tracking data."""
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        path = Path(value).expanduser().resolve()
        if path.is_file():
            return "local", str(path), str(path)
        raise ValueError("Use a supported single-post URL or an existing local file")
    if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
        raise ValueError("URLs with credentials or custom ports are not accepted")
    host = (parsed.hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        query = parse_qs(parsed.query)
        if "list" in query:
            raise ValueError("Use an individual video URL without a playlist")
        if host == "youtu.be":
            identity = parsed.path.strip("/")
        elif parsed.path == "/watch":
            values = query.get("v", [])
            identity = values[0] if len(values) == 1 else ""
        elif parsed.path.startswith("/shorts/"):
            identity = parsed.path.removeprefix("/shorts/").strip("/")
        else:
            identity = ""
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", identity):
            return "youtube", identity, f"https://www.youtube.com/watch?v={identity}"
    elif host in {"instagram.com", "www.instagram.com"}:
        match = re.fullmatch(r"/(?:p|reel|reels)/([A-Za-z0-9_-]+)/?", parsed.path)
        if match:
            identity = match[1]
            return "instagram", identity, f"https://www.instagram.com/p/{identity}/"
    elif host in {"reddit.com", "www.reddit.com", "old.reddit.com"}:
        match = re.fullmatch(r"/r/([^/]+)/comments/([A-Za-z0-9]+)/([^/]+)/?", parsed.path)
        if match:
            return "reddit", match[2].lower(), f"https://www.reddit.com{parsed.path.rstrip('/')}/"
    else:
        from .web_source import public_page
        import hashlib
        canonical = public_page(value)
        return "web:" + (urlsplit(canonical).hostname or ""), hashlib.sha256(canonical.encode()).hexdigest()[:16], canonical
    raise ValueError("Supported: one YouTube video, Instagram post, Reddit post, or local file")


def clean_name(value: str) -> str:
    value = re.sub(r'[\x00-\x1f\x7f/:\\]', "-", str(value))
    return " ".join(value.split()).strip(" .")[:100] or "Untitled harvest"


def parse_submission(value: str):
    """URL:Name, preserving scheme/port colons and existing local filenames.

    A literal colon following a valid supported URL begins the optional name.
    Colons that belong in a URL parameter should be percent-encoded as %3A.
    """
    value = value.strip()
    scheme = re.match(r"https?://", value)
    if scheme:
        # Never interpret the scheme, credentials, or port as a naming delimiter.
        authority_end = re.search(r"[/?#]", value[scheme.end():])
        if authority_end:
            start = scheme.end() + authority_end.start()
            for delimiter in re.finditer(":", value[start:]):
                position = start + delimiter.start()
                try:
                    identified = identify(value[:position].strip())
                except (ValueError, OSError):
                    continue
                title = value[position + 1:].strip()
                return identified, title or None
    return identify(value), None


class JobQueue:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "queue.json"

    @contextmanager
    def transaction(self, write=True):
        with (self.root / "queue.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.path.read_text()) if self.path.exists() else {
                "schema_version": 1, "jobs": [], "paused_sources": [], "source_ready_at": {},
            }
            if state.get("schema_version") != 1:
                raise ValueError("Unsupported queue version")
            yield state
            if not write:
                return
            fd, name = tempfile.mkstemp(dir=self.root, prefix=".queue-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as handle:
                    json.dump(state, handle, indent=2, ensure_ascii=False)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(name, self.path)
            finally:
                Path(name).unlink(missing_ok=True)

    def snapshot(self):
        with self.transaction(write=False) as state:
            return state

    def runner_active(self):
        with (self.root / "runner.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return False
            except BlockingIOError:
                return True

    def add(self, values: list[str], name: str | None = None, options=None):
        from .export_options import normalize
        options = normalize(options)
        if len(values) > 1000:
            raise ValueError("Paste at most 1,000 items at a time")
        results = []
        with self.transaction() as state:
            for value in values:
                try:
                    (source, identity, canonical), inline_name = parse_submission(value)
                except (ValueError, OSError):
                    results.append({"status": "rejected", "message": "Use an individual public media page or local file; remove temporary tokens and playlist parameters"})
                    continue
                duplicate = next((job for job in state["jobs"]
                                  if job["source"] == source and job["identity"] == identity
                                  and job.get("options", {}) == options), None)
                if duplicate:
                    results.append({"status": "duplicate", "job_id": duplicate["id"]})
                    continue
                job = {
                    "id": str(uuid.uuid4()), "source": source, "identity": identity,
                    "input": canonical, "name": clean_name(inline_name or name) if inline_name or name else None,
                    "state": "queued", "created_at": time.time(), "updated_at": time.time(),
                    "attempts": 0, "cancel_requested": False,
                    "options": options,
                }
                state["jobs"].append(job)
                results.append({"status": "added", "job_id": job["id"]})
        return results

    def get(self, job_id):
        return self._find(self.snapshot(), job_id)

    @staticmethod
    def _find(state, job_id):
        for job in state["jobs"]:
            if job["id"] == job_id:
                return job
        raise ValueError("Job was not found")

    def edit(self, job_id, action, name=None):
        with self.transaction() as state:
            job = self._find(state, job_id)
            if action == "cancel" and job["state"] in ACTIVE | {"queued"}:
                job["cancel_requested"] = True
                if job["state"] == "queued":
                    job["state"] = "cancelled"
            elif action == "retry" and job["state"] in RETRYABLE:
                job.update(state="queued", cancel_requested=False)
                job.pop("progress", None)
                job.pop("progress_label", None)
                job.pop("error", None)
            elif action == "rename" and job["state"] in RETRYABLE | {"queued"}:
                job["name"] = clean_name(name)
            else:
                raise ValueError("That action is not available for this job's current state")
            job["updated_at"] = time.time()
            return job

    def resume_source(self, source):
        with self.transaction() as state:
            state["paused_sources"] = [item for item in state["paused_sources"] if item != source]

    def claim(self):
        with self.transaction() as state:
            busy = {job["source"] for job in state["jobs"] if job["state"] in ACTIVE}
            for job in state["jobs"]:
                if (job["state"] != "queued" or job["source"] in busy
                        or job["source"] in state["paused_sources"]
                        or time.time() < state["source_ready_at"].get(job["source"], 0)):
                    continue
                job.update(state="downloading", updated_at=time.time(), token=str(uuid.uuid4()))
                job["attempts"] += 1
                return dict(job)
        return None

    def update(self, job_id, token, **values):
        with self.transaction() as state:
            job = self._find(state, job_id)
            if job.get("token") != token or job["state"] not in ACTIVE:
                raise ValueError("Job is no longer owned by this worker")
            job.update(values, updated_at=time.time())
            if values.get("pause_source"):
                if job["source"] not in state["paused_sources"]:
                    state["paused_sources"].append(job["source"])
            if values.get("state") not in ACTIVE and values.get("state") is not None:
                if job["source"] == "instagram":
                    import random
                    state["source_ready_at"]["instagram"] = time.time() + random.uniform(10, 15)

    def recover(self):
        """Only called while holding the exclusive runner lock, with no live workers."""
        with self.transaction() as state:
            for job in state["jobs"]:
                if job["state"] in ACTIVE:
                    job.update(state="interrupted", updated_at=time.time(),
                               error="Interrupted before completion; retry when ready")
