"""Consume numeric tool progress without persisting raw output or URLs."""
import json
import math
import subprocess

from .processing import progress_sink


def report(stage, completed, total):
    try:
        completed, total = float(completed), float(total)
        if math.isfinite(completed) and math.isfinite(total) and total > 0:
            progress_sink.get()(stage, min(1.0, max(0.0, completed / total)))
    except (ValueError, TypeError):
        pass


def stream(command, consume):
    # Merge pipes to avoid deadlock. Keep only bounded transient diagnostics.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    tail = ""
    try:
        for line in process.stdout:
            consume(line.strip())
            tail = (tail + line)[-32768:]
        return subprocess.CompletedProcess(command, process.wait(), tail, "")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdout.close()


def download(command):
    if progress_sink.get() is None:
        return subprocess.run(command, capture_output=True, text=True)
    command = [part for part in command if part != "--no-progress"]
    command[1:1] = ["--progress", "--progress-delta", "0.5", "--progress-template", "download:harvester:%(progress)j"]
    def consume(line):
        if line.startswith("harvester:"):
            try:
                data = json.loads(line.removeprefix("harvester:"))
                report("Downloading stream", data.get("downloaded_bytes"), data.get("total_bytes") or data.get("total_bytes_estimate"))
            except (ValueError, AttributeError):
                pass
    return stream(command, consume)


def encode(command, source, stage, duration=None):
    if progress_sink.get() is None:
        subprocess.run(command, check=True, capture_output=True)
        return
    if duration is None:
        from .media import probe
        duration = float(probe(source).get("format", {}).get("duration", 0))
    progress_sink.get()(stage, 0)
    command = [command[0], "-progress", "pipe:1", "-nostats", *command[1:]]
    def consume(line):
        if line.startswith("out_time_us="):
            try:
                report(stage, float(line.split("=", 1)[1]) / 1_000_000, duration)
            except ValueError:
                pass
    result = stream(command, consume)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, "ffmpeg")
    progress_sink.get()(stage, 1)
