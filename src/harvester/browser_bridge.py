"""Explicit Firefox submissions to the installed native app's queue."""

import subprocess
from pathlib import Path

from .job_queue import JobQueue, identify


def submit(url: str, app: Path, queue_root: Path, *, name=None, start=True, options=None):
    from .native_host import ProtocolError

    if not (app / "Contents/MacOS/Harvester").is_file():
        raise ProtocolError("app_unavailable", "Open or reinstall Harvester 2 before submitting links")
    # Normalize first: browser messages cannot submit local paths or inline names.
    try:
        source, _, canonical = identify(url)
        if source not in {"youtube", "reddit"} and not source.startswith("web:"):
            raise ValueError("Unsupported browser queue source")
        result = JobQueue(queue_root).add([canonical], name=name, options=options)[0]
    except (OSError, ValueError):
        raise ProtocolError("queue_unavailable", "Could not queue this item. Use an individual public media page and a valid clip range; remove playlist or temporary-link parameters") from None
    try:
        subprocess.run(
            ["/usr/bin/open", "-a", str(app), "harvester://queue/harvest" if start else "harvester://queue/show"],
            check=True, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        raise ProtocolError("app_unavailable", "Link saved in Harvester 2. Open the app and click Harvest") from None
    return {"state": "queued", "job_id": result["job_id"],
            "duplicate": result["status"] == "duplicate", "application": "Harvester 2"}
