"""Development interface for the v2 queue; deliberately separate from v1."""

import argparse
import json
import signal
import sys
from pathlib import Path

from .audio import AUDIO_PRESETS, DEFAULT_AUDIO_PRESET
from .job_queue import JobQueue
from .video import VIDEO_PRESETS, DEFAULT_VIDEO_PRESET


def main():
    parser = argparse.ArgumentParser(description="Harvester v2 development queue")
    parser.add_argument("--queue-root", type=Path, default=Path("state/v2-queue"))
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add")
    add.add_argument("inputs", nargs="*")
    add.add_argument("--stdin", action="store_true", help="one URL or local file path per line")
    add.add_argument("--name")
    add.add_argument("--start")
    add.add_argument("--end")
    add.add_argument("--video-preset", choices=VIDEO_PRESETS)
    add.add_argument("--audio-preset", choices=AUDIO_PRESETS)
    commands.add_parser("status")
    for action in ("cancel", "retry", "rename"):
        command = commands.add_parser(action)
        command.add_argument("job_id")
        if action == "rename":
            command.add_argument("name")
    resume = commands.add_parser("resume-source")
    resume.add_argument("source")
    run = commands.add_parser("run")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--firefox-profile", type=Path)
    run.add_argument("--audio-preset", choices=AUDIO_PRESETS, default=DEFAULT_AUDIO_PRESET)
    run.add_argument("--video-preset", choices=VIDEO_PRESETS, default=DEFAULT_VIDEO_PRESET)
    run.add_argument("--max-duration-seconds", type=int, default=3600)
    run.add_argument("--max-source-mb", type=int, default=500)
    run.add_argument("--watch", action="store_true")
    run.add_argument("--workers", type=int, default=3)
    arguments = parser.parse_args()
    try:
        queue = JobQueue(arguments.queue_root)
        if arguments.command == "add":
            values = arguments.inputs
            if arguments.stdin:
                text = sys.stdin.read(1024 * 1024 + 1)
                if len(text) > 1024 * 1024:
                    raise ValueError("Pasted input is too large")
                values += [line.strip() for line in text.splitlines() if line.strip()]
            if not values:
                raise ValueError("Paste at least one link or file path")
            options = {key: getattr(arguments, key) for key in ("start", "end", "video_preset", "audio_preset")
                       if getattr(arguments, key) is not None}
            result = queue.add(values, arguments.name, options)
        elif arguments.command == "status":
            result = {**queue.snapshot(), "runner_active": queue.runner_active()}
        elif arguments.command == "resume-source":
            queue.resume_source(arguments.source)
            result = {"resumed": arguments.source}
        elif arguments.command == "run":
            from .queue_runner import run_queue
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
            settings = {
                "max_duration_seconds": arguments.max_duration_seconds,
                "max_source_bytes": arguments.max_source_mb * 1024 ** 2,
                "archive_root": str(arguments.output.expanduser().resolve()),
                "firefox_profile": str(arguments.firefox_profile.expanduser().resolve()) if arguments.firefox_profile else None,
                "audio_preset": arguments.audio_preset, "video_preset": arguments.video_preset,
            }
            run_queue(arguments.queue_root, settings, watch=arguments.watch, workers=arguments.workers)
            result = queue.snapshot()
        else:
            result = queue.edit(arguments.job_id, arguments.command, getattr(arguments, "name", None))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError):
        # Do not leak source URLs, authentication material, or raw tool failures.
        print(json.dumps({"error": "Queue operation failed. Check the selected item, job state, output folder, or whether another runner is active."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
