from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from apps.worker.runner import HandlerResult, run_once
from infrastructure.database.models import ScheduledJob
from infrastructure.jobs import queue
from integrations.llm.base import LLMError


def enqueue(db, now, attempts=3):
    job = queue.enqueue(
        db,
        kind="k",
        payload={},
        idempotency_key="j",
        reason="test",
        run_after=now,
        max_attempts=attempts,
    )
    db.commit()
    return job.id


def test_expired_last_attempt_is_dead_lettered(db: Session):
    now = datetime.now(UTC)
    job_id = enqueue(db, now, attempts=1)
    assert queue.claim_next(db, "A", now).attempts == 1
    for n in (1, 2, 3):
        assert queue.claim_next(db, "B", now + timedelta(seconds=301 * n)) is None
    db.expire_all()
    job = db.get(ScheduledJob, job_id)
    assert (job.status, job.attempts, job.locked_by) == (queue.DEAD, 1, None)


@pytest.mark.parametrize("operation", ["complete", "fail", "defer", "renew"])
def test_old_worker_cannot_change_reclaimed_job(engine, operation):
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as a, factory() as b:
        job_id = enqueue(a, now)
        old = queue.claim_next(a, "same-worker-name", now)
        lease = queue.lease_for(old)
        later = now + timedelta(seconds=301)
        current = queue.claim_next(b, "same-worker-name", later)
        current_lease = queue.lease_for(current)
        assert current_lease != lease
        # Simulate ORM expiration/rollback after the new owner has taken over.
        a.rollback()
        a.refresh(old)
        if operation == "complete":
            accepted = queue.complete(a, old, {"writer": "old"}, lease=lease, now=later)
        elif operation == "fail":
            accepted = queue.fail(a, old, "old error", lease=lease, now=later)
        elif operation == "defer":
            accepted = queue.defer(a, old, later, "old defer", lease=lease, now=later)
        else:
            accepted = queue.renew(a, old, lease=lease, now=later)
        assert not accepted
        b.refresh(current)
        assert current.status == queue.RUNNING and current.locked_by == current_lease.token
        assert current.attempts == 2 and current.result is None and current.last_error is None
        assert queue.complete(b, current, {"writer": "new"}, lease=current_lease, now=later)
        a.expire_all()
        assert a.get(ScheduledJob, job_id).result == {"writer": "new"}


def test_defer_reclaim_does_not_reuse_token_when_attempt_and_clock_match(db):
    now = datetime.now(UTC)
    enqueue(db, now)
    job = queue.claim_next(db, "w", now)
    old_lease = queue.lease_for(job)
    assert queue.defer(db, job, now, "budget", lease=old_lease, now=now)
    job = queue.claim_next(db, "w", now)
    new_lease = queue.lease_for(job)
    assert job.attempts == 1 and old_lease != new_lease
    assert not queue.complete(db, job, {"old": True}, lease=old_lease, now=now)
    assert queue.complete(db, job, {"new": True}, lease=new_lease, now=now)


def test_expired_lease_cannot_renew_and_cancel_fences_completion(db):
    now = datetime.now(UTC)
    enqueue(db, now)
    job = queue.claim_next(db, "w", now)
    lease = queue.lease_for(job)
    assert not queue.renew(db, job, lease=lease, now=now + timedelta(seconds=300))
    job = queue.claim_next(db, "w", now + timedelta(seconds=300))
    lease = queue.lease_for(job)
    assert queue.cancel(db, job, "cancelled")
    assert not queue.complete(db, job, {}, lease=lease, now=now + timedelta(seconds=301))
    db.refresh(job)
    assert job.status == queue.CANCELLED and job.locked_by is None


@pytest.mark.parametrize("fails", [False, True])
def test_runner_preserves_claim_snapshot_after_handler_refresh(engine, monkeypatch, fails):
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as db:
        enqueue(db, now)
    clock = [now]
    monkeypatch.setattr(queue, "_now", lambda: clock[0])
    new_token = []

    def handler(db, job):
        clock[0] += timedelta(seconds=301)
        with factory() as other:
            new_token.append(queue.lease_for(queue.claim_next(other, "B", clock[0])).token)
        db.rollback()
        db.refresh(job)
        if fails:
            raise RuntimeError("old handler failed")
        return HandlerResult("done", {"old": True})

    assert run_once(factory, {"k": handler}, "A") == "lease_lost"
    with factory() as db:
        job = db.get(ScheduledJob, db.query(ScheduledJob.id).scalar())
        assert job.status == queue.RUNNING and job.locked_by == new_token[0]


def test_renew_keeps_same_owner_and_extends_live_lease(db):
    now = datetime.now(UTC)
    enqueue(db, now)
    job = queue.claim_next(db, "w", now)
    lease = queue.lease_for(job)
    assert queue.renew(db, job, lease=lease, now=now + timedelta(seconds=100))
    assert queue.claim_next(db, "B", now + timedelta(seconds=301)) is None
    assert queue.complete(db, job, {}, lease=lease, now=now + timedelta(seconds=301))


def test_worker_defers_admission_denial_without_spending_attempt(engine):
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as db:
        job_id = enqueue(db, now)

    def denied(db, job):
        raise LLMError("budget_denied", "no current free-price evidence")

    assert run_once(factory, {"k": denied}, "A") == "deferred"
    with factory() as db:
        job = db.get(ScheduledJob, job_id)
        assert (job.status, job.attempts, job.locked_by) == (queue.PENDING, 0, None)
        assert job.last_error == "budget_denied"
        assert job.run_after.replace(tzinfo=UTC) >= now + timedelta(minutes=15)
