"""Worker liveness by heartbeat file. Usage (container healthcheck): python -m apps.worker.health

The worker touches the file after every loop iteration (one job at most); healthy means it did
so within MAX_AGE_SECONDS.
"""

import os
import sys
import time
from pathlib import Path

HEARTBEAT = Path(os.environ.get("VISION_WORKER_HEARTBEAT", "/tmp/vision-worker-heartbeat"))  # noqa: S108
MAX_AGE_SECONDS = 300.0  # above the longest job (cycle cap 120 s plus LLM latency)


def beat(path: Path = HEARTBEAT) -> None:
    path.touch()


def is_alive(path: Path = HEARTBEAT, now: float | None = None) -> bool:
    try:
        age = (now if now is not None else time.time()) - path.stat().st_mtime
    except FileNotFoundError:
        return False
    return age <= MAX_AGE_SECONDS


if __name__ == "__main__":
    sys.exit(0 if is_alive() else 1)
