"""The worker: the loop that keeps him thinking, studying and checking panels between turns.

Two ways to run it, the same loop:
- its own process, `python -m apps.worker.main` (the `worker` service on the server); it exits
  cleanly on SIGTERM/SIGINT after the current job;
- a thread inside the API, with `VISION_WORKER_IN_API=1` (apps/api/main.py): one Python process on
  the owner's machine instead of two (docs/research/execucao_local.md, etapa 2).

Polls the job table and sleeps when idle or paused. Jobs are leased (infrastructure/jobs/queue.py),
so one cut short by a restart goes back to the queue instead of running twice.
"""

import logging
import signal
import socket
import threading
import uuid
from datetime import UTC, datetime

from apps.api.push import configure_push
from apps.api.settings import Settings, get_settings
from apps.worker.handlers import build_handlers
from apps.worker.health import beat
from apps.worker.runner import run_once
from core.autonomy.cycle import schedule
from infrastructure.database.session import get_sessionmaker
from infrastructure.observability.logging import configure_logging

logger = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 5.0


def serve(stop: threading.Event, settings: Settings | None = None) -> None:
    """Runs jobs until `stop` is set. Never installs signal handlers, so it can run in a thread.

    A failed iteration (the database away for a moment, say) is logged and retried after the idle
    pause instead of ending the loop: in a thread, an exception would silently leave the API with
    no worker. The heartbeat only moves after an iteration that worked, so the health check still
    sees a worker that keeps failing."""
    settings = settings or get_settings()
    worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    factory = get_sessionmaker()
    handlers = build_handlers(settings)
    logger.info("worker started", extra={"event": "worker_started"})
    while not stop.is_set():
        try:
            # Schedule-driven trigger: at most one cycle job per window (idempotent).
            with factory() as session:
                schedule(session, datetime.now(UTC), settings.autonomy_cycle_minutes)
            outcome = run_once(factory, handlers, worker_id)
        except Exception:
            logger.exception("worker iteration failed", extra={"event": "worker_iteration_failed"})
            stop.wait(IDLE_SLEEP_SECONDS)
            continue
        beat()
        if outcome in ("idle", "paused"):
            stop.wait(IDLE_SLEEP_SECONDS)
    logger.info("worker stopped", extra={"event": "worker_stopped"})


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_push(settings)
    stop = threading.Event()

    def on_signal(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    serve(stop, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
