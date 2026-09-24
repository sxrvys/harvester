"""A single queue supervisor, with bounded independent worker processes."""

from __future__ import annotations

import fcntl
import json
import os
import random
import signal
import subprocess
import sys
import time
from pathlib import Path

from .archive import _atomic_json
from .job_queue import ACTIVE, JobQueue


def stop_process(process):
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run_queue(root: Path, settings: dict, *, watch=False, workers=3):
    if not 1 <= workers <= 4:
        raise ValueError("Use between one and four workers")
    from .limits import Limits
    Limits.from_settings(settings)
    queue = JobQueue(root)
    with (queue.root / "runner.lock").open("a") as runner_lock:
        try:
            fcntl.flock(runner_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A queue runner is already active") from None
        queue.recover()
        settings_path = queue.root / "runner-settings.json"
        _atomic_json(settings_path, settings)
        active = {}
        try:
            while True:
                snapshot = queue.snapshot()
                by_id = {job["id"]: job for job in snapshot["jobs"]}
                for job_id, process in list(active.items()):
                    job = by_id[job_id]
                    if job.get("cancel_requested") and job["state"] != "complete":
                        stop_process(process)
                    if process.poll() is not None:
                        current = queue.get(job_id)
                        if current["state"] in ACTIVE:
                            queue.update(job_id, current["token"],
                                         state="cancelled" if current["cancel_requested"] else "interrupted")
                        if job["source"] == "instagram":
                            with queue.transaction() as state:
                                state["source_ready_at"]["instagram"] = time.time() + random.uniform(10, 15)
                        del active[job_id]
                while len(active) < workers:
                    job = queue.claim()
                    if job is None:
                        break
                    try:
                        # Inherit the supervisor lock so a killed supervisor cannot
                        # leave workers running alongside a replacement supervisor.
                        process = subprocess.Popen(
                            [sys.executable, "-m", "harvester.queue_worker", str(queue.root),
                             job["id"], job["token"], str(settings_path)],
                            start_new_session=True, pass_fds=(runner_lock.fileno(),),
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]) + os.pathsep + os.environ.get("PYTHONPATH", "")},
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                        active[job["id"]] = process
                    except OSError:
                        queue.update(job["id"], job["token"], state="failed", error="Could not start the media worker")
                if not watch and not active:
                    state = queue.snapshot()
                    pending = any(job["state"] == "queued" and job["source"] not in state["paused_sources"]
                                  for job in state["jobs"])
                    if not pending:
                        return
                time.sleep(0.25)
        finally:
            for job_id, process in active.items():
                stop_process(process)
                current = queue.get(job_id)
                if current["state"] in ACTIVE:
                    queue.update(job_id, current["token"], state="interrupted")
