"""Persistent worker process. Usage: python -m apps.worker.main

Runs alongside the API (docker compose service `worker`). Polls the job table; sleeps when idle
or paused; exits cleanly on SIGTERM/SIGINT after the current job.
"""

import logging
import signal
import socket
import time
import uuid
from datetime import UTC, datetime

from apps.api.settings import get_settings
from apps.worker.handlers import build_handlers
from apps.worker.health import beat
from apps.worker.runner import run_once
from core.autonomy.cycle import schedule
from infrastructure.database.session import get_sessionmaker
from infrastructure.observability.logging import configure_logging

logger = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 5.0


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    factory = get_sessionmaker()
    handlers = build_handlers(settings)
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info("worker started", extra={"event": "worker_started"})
    while not stopping:
        # Schedule-driven trigger: at most one cycle job per window (idempotent).
        with factory() as session:
            schedule(session, datetime.now(UTC), settings.autonomy_cycle_minutes)
        outcome = run_once(factory, handlers, worker_id)
        beat()
        if outcome in ("idle", "paused"):
            time.sleep(IDLE_SLEEP_SECONDS)
    logger.info("worker stopped", extra={"event": "worker_stopped"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
