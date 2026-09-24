"""One isolated v2 harvest. Never persists raw downloader errors or credentials."""

from __future__ import annotations

import fcntl
import json
import os
import signal
import random
import time
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .archive import _atomic_json, _sha256
from .job_queue import JobQueue, clean_name
from .processing import processing_scope, export_options, progress_sink


def publish_bundle(queue, job, staging, bundle, output_root):
    """Publish a complete, self-contained bundle atomically on the output volume."""
    metadata = json.loads((bundle / "metadata.json").read_text())
    name = clean_name(job.get("name") or metadata["item"].get("title") or "Untitled harvest")
    output_root.mkdir(parents=True, exist_ok=True)
    with (queue.root / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # An interrupted journal update after a successful publish can be retried
        # without creating another copy of this exact job's result.
        receipt_path = queue.root / "receipts" / f"{job['id']}.json"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            existing = Path(receipt["output_path"])
            if existing.is_dir() and all(
                (existing / record["path"]).is_file()
                and _sha256(existing / record["path"]) == record["sha256"]
                for record in receipt["files"]
            ):
                queue.update(job["id"], job["token"], state="complete", output_path=str(existing),
                             name=receipt["name"], video_path=receipt.get("video_path"))
                return existing
        destination = output_root / name
        number = 2
        while destination.exists():
            destination = output_root / f"{name} ({number})"
            number += 1
        with tempfile.TemporaryDirectory(dir=output_root, prefix=".harvester-publish-") as temporary:
            prepared = Path(temporary) / "bundle"
            prepared.mkdir()
            counts = {}
            for record in metadata["files"]:
                source = (bundle / record["path"]).resolve()
                if staging.resolve() not in source.parents or not source.is_file():
                    raise ValueError("Generated bundle has an invalid media path")
                role = record["role"]
                counts[role] = counts.get(role, 0) + 1
                count = sum(item["role"] == role for item in metadata["files"])
                suffix = f" {counts[role]:02}" if count > 1 else ""
                filename = f"{name} — {role}{suffix}{source.suffix}"
                # Staging is also created on the output volume; moving avoids a
                # second full copy of long all-keyframe video and WAV files.
                source.rename(prepared / filename)
                record["path"] = filename
            video_record = next((record for record in metadata["files"] if record["role"] == "video"), None)
            video_path = str(destination / video_record["path"]) if video_record else None
            receipt_path.parent.mkdir(exist_ok=True, mode=0o700)
            # Bookkeeping belongs to the app's private queue, not the user's media folder.
            _atomic_json(receipt_path, {**metadata, "harvester_job_id": job["id"],
                                       "name": name, "output_path": str(destination), "video_path": video_path})
            # Coordinate with cancel requests: cancel cannot win after publishing
            # and misleadingly mark an existing completed bundle as cancelled.
            with queue.transaction() as state:
                current = queue._find(state, job["id"])
                if current.get("token") != job["token"] or current.get("cancel_requested"):
                    raise InterruptedError("Job cancelled")
                prepared.rename(destination)
                current.update(state="complete", output_path=str(destination), video_path=video_path, name=name, updated_at=time.time())
                current["output_bytes"] = sum((destination / record["path"]).stat().st_size for record in metadata["files"])
                current.pop("progress", None)
                current.pop("progress_label", None)
                if current["source"] == "instagram":
                    state["source_ready_at"]["instagram"] = time.time() + random.uniform(10, 15)
            return destination


def work(root: Path, job_id: str, token: str, settings_path: Path):
    queue = JobQueue(root)
    job = queue.get(job_id)
    if job.get("token") != token or job["state"] != "downloading":
        raise ValueError("Job is no longer assigned to this worker")
    settings = json.loads(settings_path.read_text())

    @contextmanager
    def conversion_slot():
        queue.update(job_id, token, state="waiting_to_convert", progress=None, progress_label=None)
        with (queue.root / "conversion.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            queue.update(job_id, token, state="converting")
            yield
        queue.update(job_id, token, state="saving", progress=None, progress_label=None)

    from .limits import Limits, acquisition_limits
    limits = Limits.from_settings(settings)
    limit_token = acquisition_limits.set(limits)
    context_token = processing_scope.set(conversion_slot)
    option_token = export_options.set(job.get("options", {}))
    last_progress = [0.0, ""]
    def progress(stage, fraction):
        now = time.monotonic()
        if now - last_progress[0] >= 0.5 or stage != last_progress[1] or fraction == 1:
            queue.update(job_id, token, progress=fraction, progress_label=stage)
            last_progress[:] = [now, stage]
    progress_token = progress_sink.set(progress)
    try:
        output = Path(settings["archive_root"])
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output, prefix=".harvester-job-") as temporary:
            staging = Path(temporary)
            audio = job.get("options", {}).get("audio_preset", settings["audio_preset"])
            video = job.get("options", {}).get("video_preset", settings["video_preset"])
            profile = Path(settings.get("firefox_profile") or "/nonexistent")
            if job["source"] == "local":
                from .local_file import harvest_local_file
                bundle = harvest_local_file(Path(job["input"]), staging, audio, video_preset=video,
                                            max_duration_seconds=limits.duration, max_source_bytes=limits.size)
            elif job["source"] == "youtube":
                from .youtube import harvest_youtube_url
                bundle = harvest_youtube_url(job["input"], profile, staging, audio, video)
            elif job["source"] == "reddit":
                from .reddit import harvest_reddit_url
                bundle = harvest_reddit_url(job["input"], profile, staging, audio, video)
            elif job["source"].startswith("web:"):
                from .web_source import harvest_web_url
                bundle = harvest_web_url(job["input"], staging, audio, video)
            else:
                if not settings.get("firefox_profile"):
                    raise ValueError("Firefox profile is required for Instagram")
                from .instagram import harvest_instagram_url
                bundle = harvest_instagram_url(job["input"], profile, staging,
                                               audio_preset=audio, video_preset=video)
            publish_bundle(queue, job, staging, bundle, output)
        # Terminal bookkeeping, including Instagram pacing, is performed by runner.
    except (KeyboardInterrupt, SystemExit, InterruptedError):
        current = queue.get(job_id)
        if current["state"] != "complete":
            queue.update(job_id, token, state="cancelled" if current["cancel_requested"] else "interrupted")
    except Exception as error:
        # Inspect known failure categories only; never retain exception text.
        message = str(error).lower()
        blocked = any(marker in message for marker in
                      ("authentication", "rate-limit", "authorization", "access control", "profile", "429"))
        safe = ("Source needs attention: check login or Firefox profile permissions, then resume this source"
                if blocked else "Harvest failed; check the source, size/duration limits, or local media tools")
        if "clip range" in message:
            safe = "The requested clip is outside this video's duration. Submit a shorter range."
        elif "duration limit" in message:
            safe = "Source exceeds the duration limit configured in Settings. Trimming currently still downloads the full source."
        elif "size limit" in message:
            safe = "Source exceeds the download size limit configured in Settings."
        elif isinstance(error, FileNotFoundError):
            safe = "A media tool or source file is missing. Check the file and installed media tools."
        elif isinstance(error, OSError) and error.errno == 28:
            safe = "The output disk is full. Free space and retry."
        from .web_source import WebSourceError
        if isinstance(error, WebSourceError):
            safe = str(error)  # These errors contain only fixed, user-facing messages.
        if queue.get(job_id)["state"] != "complete":
            queue.update(job_id, token, state="failed", error=safe, pause_source=blocked)
    finally:
        acquisition_limits.reset(limit_token)
        processing_scope.reset(context_token)
        export_options.reset(option_token)
        progress_sink.reset(progress_token)


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    work(Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4]))


if __name__ == "__main__":
    main()
