"""One worker iteration: respect the global pause, claim a due job, run its handler, record the
outcome. No LLM runs unless a job (created by a real event) asks for it."""

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.orm import Session, sessionmaker

from core.policies.autonomy import is_paused
from infrastructure.database.models import ScheduledJob
from infrastructure.jobs import queue

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandlerResult:
    outcome: Literal["done", "defer"]
    result: dict[str, Any] = field(default_factory=dict)
    defer_until: datetime | None = None
    reason: str = ""


Handler = Callable[[Session, ScheduledJob], HandlerResult]

IterationOutcome = Literal["paused", "idle", "done", "deferred", "failed", "unknown_kind"]


def run_once(
    factory: sessionmaker[Session], handlers: dict[str, Handler], worker_id: str
) -> IterationOutcome:
    with factory() as session:
        if is_paused(session):
            return "paused"
        job = queue.claim_next(session, worker_id)
        if job is None:
            return "idle"
        handler = handlers.get(job.kind)
        if handler is None:
            queue.fail(session, job, f"no handler for kind {job.kind!r}")
            return "unknown_kind"
        try:
            outcome = handler(session, job)
        except Exception as exc:  # any handler failure becomes a retry or a dead letter
            session.rollback()
            job = session.get(ScheduledJob, job.id)
            queue.fail(session, job, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            logger.warning("job failed", extra={"event": "job_failed"})
            return "failed"
        if outcome.outcome == "defer" and outcome.defer_until is not None:
            queue.defer(session, job, outcome.defer_until, outcome.reason)
            return "deferred"
        queue.complete(session, job, outcome.result)
        return "done"
