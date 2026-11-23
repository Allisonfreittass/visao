"""Optional proofs on a disposable LOCAL PostgreSQL schema, never the production database."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from infrastructure.database.base import Base
from infrastructure.database.models import ScheduledJob, SystemFlag
from infrastructure.jobs import queue
from integrations.llm.base import ChatMessage, LLMError
from integrations.llm.budget import LEDGER, BudgetLimits
from tests.unit.test_budget_guard import ENDPOINT, fake, make_guard

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg_factory():
    value = os.environ.get("VISION_TEST_DATABASE_URL")
    if not value:
        pytest.skip("local VISION_TEST_DATABASE_URL not set")
    url = make_url(value)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or "test" not in (url.database or ""):
        pytest.fail("hardening tests require a loopback PostgreSQL test database")
    schema = "phase10_test_" + uuid.uuid4().hex
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))  # noqa: S608
        isolated = engine.execution_options(schema_translate_map={None: schema})
        Base.metadata.create_all(isolated)
        yield sessionmaker(isolated, expire_on_commit=False)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))  # noqa: S608
        engine.dispose()


def test_postgres_claim_is_exclusive_and_attempts_are_bounded(pg_factory):
    now = datetime.now(UTC)
    with pg_factory() as db:
        job = queue.enqueue(
            db,
            kind="test",
            payload={},
            idempotency_key="j",
            reason="test",
            run_after=now,
            max_attempts=1,
        )
        db.commit()
        job_id = job.id

    def claim(n):
        with pg_factory() as db:
            job = queue.claim_next(db, f"worker-{n}", now)
            return queue.lease_for(job) if job else None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))
    assert sum(lease is not None for lease in results) == 1
    with pg_factory() as db:
        assert queue.claim_next(db, "recovery", now + timedelta(seconds=301)) is None
        db.expire_all()
        job = db.get(ScheduledJob, job_id)
        assert job.status == queue.DEAD and job.attempts == 1


@pytest.mark.parametrize("operation", ["complete", "fail", "defer", "renew"])
def test_postgres_stale_owner_is_fenced(pg_factory, operation):
    now = datetime.now(UTC)
    later = now + timedelta(seconds=301)
    with pg_factory() as a, pg_factory() as b:
        queue.enqueue(a, kind="test", payload={}, idempotency_key="j", reason="test", run_after=now)
        a.commit()
        old = queue.claim_next(a, "A", now)
        lease = queue.lease_for(old)
        current = queue.claim_next(b, "B", later)
        new_lease = queue.lease_for(current)
        a.rollback()
        a.refresh(old)
        if operation == "complete":
            accepted = queue.complete(a, old, {}, lease=lease, now=later)
        elif operation == "fail":
            accepted = queue.fail(a, old, "stale", lease=lease, now=later)
        elif operation == "defer":
            accepted = queue.defer(a, old, later, "stale", lease=lease, now=later)
        else:
            accepted = queue.renew(a, old, lease=lease, now=later)
        assert not accepted
        b.refresh(current)
        assert current.status == queue.RUNNING and queue.lease_for(current) == new_lease


def test_postgres_reservation_race_respects_shared_limit(pg_factory):
    limits = BudgetLimits(calls_per_day=5, concurrency=32)

    def reserve(_):
        try:
            make_guard(pg_factory, limits=limits).reserve(
                fake(), ENDPOINT, [ChatMessage("user", "test")], 512
            )
            return True
        except LLMError as exc:
            assert exc.kind == "budget_denied"
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(100)))
    with pg_factory() as db:
        state = db.get(SystemFlag, LEDGER).value
        assert sum(results) == state["calls"] == len(state["active"]) == 5


def test_postgres_turn_lock_holds_across_commits_and_sessions(pg_factory):
    # The advisory lock lives on a connection of its own: the turn's commits do not release it,
    # and a turn in another process (another session here) waits for it.
    from core.conversation import turn_lock

    conversation = uuid.uuid4()
    with pg_factory() as first, pg_factory() as second:
        with turn_lock._database(first, conversation, deadline=0):
            first.execute(text("SELECT 1"))
            first.commit()
            with pytest.raises(turn_lock.Busy):
                with turn_lock._database(second, conversation, deadline=0):
                    pass
        with turn_lock._database(second, conversation, deadline=0):
            pass


def test_postgres_two_approvals_at_once_send_one_email(pg_factory, monkeypatch):
    import threading
    import time

    from core.google import account as accounts
    from core.google import actions
    from tests.integration.test_google import KEY, FakeGoogle, connected
    from tests.integration.test_mind import setup

    google = FakeGoogle()
    slow_send = google.send

    def send(**kwargs):
        time.sleep(0.3)  # the other approval arrives while this one is sending
        return slow_send(**kwargs)

    google.send = send
    monkeypatch.setattr(accounts, "client_for", lambda account, key: google)
    with pg_factory() as db:
        owner = setup(db)
        connected(db, owner)
        action = actions.propose_email(db, owner.id, to="a@b.com", subject="Oi", body="x")
        db.commit()
        owner_id, action_id = owner.id, action.id
    start = threading.Barrier(2)

    def approve(_):
        with pg_factory() as db:
            from infrastructure.database.models import User

            start.wait(5)
            done = actions.approve(db, db.get(User, owner_id), action_id, KEY)
            db.commit()
            return done.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(approve, range(2)))
    assert len(google.sent) == 1
    assert statuses == ["done", "sending"]
