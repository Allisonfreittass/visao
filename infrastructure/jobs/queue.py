"""Persistent job queue on the main database (no Redis): idempotent enqueue, optimistic claim
with a lease, bounded retries with exponential backoff, dead-letter, crash recovery."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from infrastructure.database.models import ScheduledJob

PENDING = "PENDING"
RUNNING = "RUNNING"
DONE = "DONE"
DEAD = "DEAD"
CANCELLED = "CANCELLED"

BASE_BACKOFF_SECONDS = 30
LEASE_SECONDS = 300


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(
    session: Session,
    *,
    kind: str,
    payload: dict[str, Any],
    idempotency_key: str,
    reason: str,
    owner_user_id: uuid.UUID | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> ScheduledJob:
    """Returns the existing job when the key was already used: enqueueing is idempotent."""
    existing = session.scalar(
        select(ScheduledJob).where(ScheduledJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    job = ScheduledJob(
        kind=kind,
        payload=payload,
        idempotency_key=idempotency_key,
        reason=reason,
        owner_user_id=owner_user_id,
        status=PENDING,
        run_after=run_after or _now(),
        attempts=0,
        max_attempts=max_attempts,
    )
    session.add(job)
    session.flush()
    return job


def claim_next(
    session: Session, worker_id: str, now: datetime | None = None
) -> ScheduledJob | None:
    """Claims one due job. A RUNNING job whose lease expired (its worker died) is claimable
    again; the attempt counter still bounds how often it can be retried."""
    now = now or _now()
    claimable = or_(
        and_(ScheduledJob.status == PENDING, ScheduledJob.run_after <= now),
        and_(ScheduledJob.status == RUNNING, ScheduledJob.locked_until < now),
    )
    candidates = session.scalars(
        select(ScheduledJob.id).where(claimable).order_by(ScheduledJob.run_after).limit(5)
    ).all()
    for job_id in candidates:
        claimed = session.execute(
            update(ScheduledJob)
            .where(ScheduledJob.id == job_id, claimable)
            .values(
                status=RUNNING,
                locked_by=worker_id,
                locked_until=now + timedelta(seconds=LEASE_SECONDS),
                attempts=ScheduledJob.attempts + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount == 1:
            session.commit()
            job = session.get(ScheduledJob, job_id)
            session.refresh(job)
            return job
        session.rollback()  # another worker won this one; try the next
    return None


def complete(session: Session, job: ScheduledJob, result: dict[str, Any]) -> None:
    job.status = DONE
    job.result = result
    job.locked_by = None
    job.locked_until = None
    job.finished_at = _now()
    session.commit()


def fail(session: Session, job: ScheduledJob, error: str, now: datetime | None = None) -> None:
    """Schedules a retry with exponential backoff, or dead-letters after max_attempts."""
    now = now or _now()
    job.last_error = error[:2000]
    job.locked_by = None
    job.locked_until = None
    if job.attempts >= job.max_attempts:
        job.status = DEAD
        job.finished_at = now
    else:
        job.status = PENDING
        job.run_after = now + timedelta(seconds=BASE_BACKOFF_SECONDS * 2 ** (job.attempts - 1))
    session.commit()


def cancel(session: Session, job: ScheduledJob, reason: str) -> bool:
    if job.status not in (PENDING, RUNNING):
        return False
    job.status = CANCELLED
    job.last_error = reason[:2000]
    job.finished_at = _now()
    session.commit()
    return True


def defer(session: Session, job: ScheduledJob, until: datetime, reason: str) -> None:
    """Puts a claimed job back without counting it as a failed attempt (e.g. budget, pause)."""
    job.status = PENDING
    job.attempts = max(job.attempts - 1, 0)
    job.run_after = until
    job.last_error = reason[:2000]
    job.locked_by = None
    job.locked_until = None
    session.commit()
