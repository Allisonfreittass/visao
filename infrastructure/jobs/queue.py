"""Persistent job queue on the main database (no Redis): idempotent enqueue, optimistic claim
with a lease, bounded retries with exponential backoff, dead-letter, crash recovery."""

import logging
import uuid
from dataclasses import dataclass
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
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Lease:
    """Snapshot captured before a handler can commit, expire or refresh its ORM object."""

    job_id: uuid.UUID
    token: str


def lease_for(job: ScheduledJob) -> Lease:
    if job.status != RUNNING or not job.locked_by:
        raise ValueError("job has no running lease")
    return Lease(job.id, job.locked_by)


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
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
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
        and_(ScheduledJob.status == RUNNING, ScheduledJob.locked_until <= now),
    )
    session.execute(
        update(ScheduledJob)
        .where(claimable, ScheduledJob.attempts >= ScheduledJob.max_attempts)
        .values(
            status=DEAD,
            locked_by=None,
            locked_until=None,
            finished_at=now,
            last_error="attempt limit reached during lease recovery",
        )
        .execution_options(synchronize_session=False)
    )
    claimable = and_(claimable, ScheduledJob.attempts < ScheduledJob.max_attempts)
    candidates = session.scalars(
        select(ScheduledJob.id).where(claimable).order_by(ScheduledJob.run_after).limit(5)
    ).all()
    for job_id in candidates:
        claimed = session.execute(
            update(ScheduledJob)
            .where(ScheduledJob.id == job_id, claimable)
            .values(
                status=RUNNING,
                # A fresh token also fences defer/reclaim when attempts are refunded.
                locked_by=f"{worker_id[:60]}:{uuid.uuid4().hex}",
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
    session.commit()  # persist dead-letter cleanup even if no job was admitted
    return None


def _finish(session: Session, job: ScheduledJob, lease: Lease, now: datetime, **values) -> bool:
    if job.id != lease.job_id:
        raise ValueError("lease belongs to another job")
    changed = session.execute(
        update(ScheduledJob)
        .where(
            ScheduledJob.id == lease.job_id,
            ScheduledJob.status == RUNNING,
            ScheduledJob.locked_by == lease.token,
            ScheduledJob.locked_until > now,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        session.rollback()
        logger.warning("job lease lost; stale mutation refused", extra={"event": "job_lease_lost"})
        return False
    session.commit()
    session.refresh(job)
    return True


def complete(
    session: Session,
    job: ScheduledJob,
    result: dict[str, Any],
    *,
    lease: Lease,
    now: datetime | None = None,
) -> bool:
    now = now or _now()
    return _finish(
        session,
        job,
        lease,
        now,
        status=DONE,
        result=result,
        locked_by=None,
        locked_until=None,
        finished_at=now,
    )


def fail(
    session: Session,
    job: ScheduledJob,
    error: str,
    now: datetime | None = None,
    *,
    lease: Lease,
) -> bool:
    """Schedules a retry with exponential backoff, or dead-letters after max_attempts."""
    now = now or _now()
    # Read values fresh after a handler rollback, but never refresh the ownership token.
    attempts, maximum = session.execute(
        select(ScheduledJob.attempts, ScheduledJob.max_attempts).where(ScheduledJob.id == job.id)
    ).one()
    exhausted = attempts >= maximum
    return _finish(
        session,
        job,
        lease,
        now,
        last_error=error[:2000],
        locked_by=None,
        locked_until=None,
        status=DEAD if exhausted else PENDING,
        finished_at=now if exhausted else None,
        run_after=now + timedelta(seconds=BASE_BACKOFF_SECONDS * 2 ** max(attempts - 1, 0)),
    )


def cancel(session: Session, job: ScheduledJob, reason: str) -> bool:
    changed = session.execute(
        update(ScheduledJob)
        .where(ScheduledJob.id == job.id, ScheduledJob.status.in_((PENDING, RUNNING)))
        .values(
            status=CANCELLED,
            last_error=reason[:2000],
            finished_at=_now(),
            locked_by=None,
            locked_until=None,
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        session.rollback()
        return False
    session.commit()
    session.refresh(job)
    return True


def defer(
    session: Session,
    job: ScheduledJob,
    until: datetime,
    reason: str,
    *,
    lease: Lease,
    now: datetime | None = None,
) -> bool:
    """Puts a claimed job back without counting it as a failed attempt (e.g. budget, pause)."""
    return _finish(
        session,
        job,
        lease,
        now or _now(),
        status=PENDING,
        attempts=ScheduledJob.attempts - 1,
        run_after=until,
        last_error=reason[:2000],
        locked_by=None,
        locked_until=None,
    )


def renew(
    session: Session,
    job: ScheduledJob,
    *,
    lease: Lease,
    now: datetime | None = None,
) -> bool:
    now = now or _now()
    return _finish(session, job, lease, now, locked_until=now + timedelta(seconds=LEASE_SECONDS))
