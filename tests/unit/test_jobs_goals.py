from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from apps.worker.runner import HandlerResult, run_once
from core.goals import lifecycle
from core.initiatives.notify import MAX_PER_DAY, deliver_after, notify
from core.policies.autonomy import is_paused, set_paused
from infrastructure.database.models import Goal, GoalEvent, ScheduledJob, User
from infrastructure.jobs import queue


def _user(db: Session, **fields: object) -> User:
    user = User(email="a@exemplo.com", password_hash="!", **fields)
    db.add(user)
    db.commit()
    return user


def _goal(db: Session, owner: User, **overrides: object) -> Goal | None:
    fields: dict[str, object] = {
        "owner": owner,
        "kind": "research_followup",
        "title": "Pesquisar de novo: X",
        "rationale": "sem resposta",
        "success_criteria": "achar fonte",
        "required_permissions": ["llm", "web_research", "notify"],
        "budget": {"searches": 2, "llm_calls": 1},
    }
    fields.update(overrides)
    goal = lifecycle.propose(db, **fields)  # type: ignore[arg-type]
    db.commit()
    return goal


# --- queue ------------------------------------------------------------------------------------


def test_enqueue_is_idempotent(db: Session) -> None:
    first = queue.enqueue(db, kind="k", payload={}, idempotency_key="same", reason="r")
    second = queue.enqueue(db, kind="k", payload={"x": 1}, idempotency_key="same", reason="r")
    assert first.id == second.id
    assert len(db.scalars(select(ScheduledJob)).all()) == 1


def test_claim_respects_run_after_and_marks_running(db: Session) -> None:
    now = datetime.now(UTC)
    queue.enqueue(
        db,
        kind="k",
        payload={},
        idempotency_key="later",
        reason="r",
        run_after=now + timedelta(hours=1),
    )
    assert queue.claim_next(db, "w1", now) is None
    queue.enqueue(db, kind="k", payload={}, idempotency_key="now", reason="r", run_after=now)
    db.commit()
    job = queue.claim_next(db, "w1", now)
    assert job is not None and job.idempotency_key == "now"
    assert (job.status, job.attempts, job.locked_by) == ("RUNNING", 1, "w1")
    assert queue.claim_next(db, "w2", now) is None  # nothing else due


def test_expired_lease_is_reclaimed_after_a_crash(db: Session) -> None:
    now = datetime.now(UTC)
    queue.enqueue(db, kind="k", payload={}, idempotency_key="j", reason="r", run_after=now)
    db.commit()
    queue.claim_next(db, "dead-worker", now)
    later = now + timedelta(seconds=queue.LEASE_SECONDS + 1)
    job = queue.claim_next(db, "w2", later)
    assert job is not None and (job.locked_by, job.attempts) == ("w2", 2)


def test_backoff_then_dead_letter(db: Session) -> None:
    now = datetime.now(UTC)
    queue.enqueue(
        db, kind="k", payload={}, idempotency_key="j", reason="r", run_after=now, max_attempts=2
    )
    db.commit()
    job = queue.claim_next(db, "w", now)
    queue.fail(db, job, "boom", now)
    assert job.status == "PENDING"
    assert job.run_after.replace(tzinfo=UTC) == now + timedelta(seconds=queue.BASE_BACKOFF_SECONDS)

    job = queue.claim_next(db, "w", now + timedelta(minutes=5))
    queue.fail(db, job, "boom again", now)
    assert (job.status, job.last_error) == ("DEAD", "boom again")


def test_defer_does_not_spend_an_attempt(db: Session) -> None:
    now = datetime.now(UTC)
    queue.enqueue(db, kind="k", payload={}, idempotency_key="j", reason="r", run_after=now)
    db.commit()
    job = queue.claim_next(db, "w", now)
    queue.defer(db, job, now + timedelta(days=1), "sem orçamento")
    assert (job.status, job.attempts) == ("PENDING", 0)


# --- runner -----------------------------------------------------------------------------------


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_runner_idles_pauses_and_runs(db: Session, factory) -> None:
    calls: list[str] = []

    def handler(session: Session, job: ScheduledJob) -> HandlerResult:
        calls.append(job.idempotency_key)
        return HandlerResult("done", {"ok": True})

    assert run_once(factory, {"k": handler}, "w") == "idle"
    queue.enqueue(db, kind="k", payload={}, idempotency_key="j", reason="r")
    db.commit()

    set_paused(db, True, actor_user_id=None, reason="teste")
    assert run_once(factory, {"k": handler}, "w") == "paused"
    assert calls == []

    set_paused(db, False, actor_user_id=None, reason="teste")
    assert run_once(factory, {"k": handler}, "w") == "done"
    assert calls == ["j"]
    assert db.scalar(select(ScheduledJob.status)) == "DONE"


def test_runner_turns_exceptions_into_retries(db: Session, factory) -> None:
    def broken(session: Session, job: ScheduledJob) -> HandlerResult:
        raise RuntimeError("falhou")

    queue.enqueue(db, kind="k", payload={}, idempotency_key="j", reason="r")
    db.commit()
    assert run_once(factory, {"k": broken}, "w") == "failed"
    job = db.scalar(select(ScheduledJob))
    db.refresh(job)
    assert job.status == "PENDING" and "RuntimeError: falhou" in job.last_error


def test_unknown_kind_is_not_silently_dropped(db: Session, factory) -> None:
    queue.enqueue(db, kind="misterioso", payload={}, idempotency_key="j", reason="r")
    db.commit()
    assert run_once(factory, {}, "w") == "unknown_kind"


# --- goals ------------------------------------------------------------------------------------


def test_proposal_is_evaluated_and_recorded(db: Session) -> None:
    goal = _goal(db, _user(db))
    assert goal.status == "EVALUATED"
    assert [e.to_status for e in lifecycle.history(db, goal)] == ["PROPOSED", "EVALUATED"]


@pytest.mark.parametrize(
    ("overrides", "reason_part"),
    [
        ({"required_permissions": ["llm", "send_email"]}, "permissões"),
        ({"budget": {"searches": 50}}, "orçamento"),
        ({"success_criteria": " "}, "critério"),
        ({"kind": "desconhecido"}, "executor"),
    ],
)
def test_policy_rejects_unsafe_or_vague_goals(db: Session, overrides, reason_part) -> None:
    goal = _goal(db, _user(db), **overrides)
    assert goal.status == "REJECTED"
    assert reason_part in lifecycle.history(db, goal)[-1].reason


def test_invalid_transitions_are_refused(db: Session) -> None:
    goal = _goal(db, _user(db))
    with pytest.raises(lifecycle.TransitionError):
        lifecycle.transition(db, goal, "COMPLETED", actor="agent", reason="pulando etapas")


def test_only_the_owner_approves_and_approval_queues_one_job(db: Session) -> None:
    owner = _user(db)
    stranger = User(email="b@exemplo.com", password_hash="!")
    db.add(stranger)
    db.commit()
    goal = _goal(db, owner)

    with pytest.raises(lifecycle.TransitionError):
        lifecycle.approve(db, goal, stranger, payload={})
    job = lifecycle.approve(db, goal, owner, payload={})
    assert goal.status == "APPROVED"
    assert job.kind == "research_followup" and job.payload["goal_id"] == str(goal.id)


def test_cancel_also_cancels_the_queued_job(db: Session) -> None:
    owner = _user(db)
    goal = _goal(db, owner)
    job = lifecycle.approve(db, goal, owner, payload={})
    lifecycle.cancel(db, goal, owner, "mudei de ideia")
    assert (goal.status, job.status) == ("CANCELLED", "CANCELLED")


def test_no_agent_proposals_while_paused(db: Session) -> None:
    owner = _user(db)
    set_paused(db, True, actor_user_id=owner.id, reason="teste")
    assert is_paused(db)
    assert _goal(db, owner) is None


def test_goal_events_are_append_only_in_code(db: Session) -> None:
    goal = _goal(db, _user(db))
    assert db.scalars(select(GoalEvent).where(GoalEvent.goal_id == goal.id)).all()


# --- notifications ----------------------------------------------------------------------------


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _local(day: int, hour: int) -> datetime:
    """A São Paulo wall-clock time, expressed in UTC."""
    return datetime(2026, 10, day, hour, tzinfo=SAO_PAULO).astimezone(UTC)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (_local(30, 12), _local(30, 12)),  # midday: delivered now
        (_local(30, 23), _local(31, 8)),  # late night: held to next morning
        (_local(31, 3), _local(31, 8)),  # small hours: held to the same morning
        (_local(31, 7), _local(31, 8)),
        (_local(31, 8), _local(31, 8)),  # window over: delivered now
    ],
)
def test_quiet_hours_cross_midnight(now: datetime, expected: datetime) -> None:
    user = User(quiet_start="22:00", quiet_end="08:00", timezone="America/Sao_Paulo")
    assert deliver_after(user, now) == expected


def test_equal_quiet_bounds_disable_quiet_hours() -> None:
    user = User(quiet_start="00:00", quiet_end="00:00", timezone="America/Sao_Paulo")
    now = _local(31, 3)
    assert deliver_after(user, now) == now


def test_notifications_are_rate_limited_and_paused(db: Session) -> None:
    owner = _user(db, quiet_start="00:00", quiet_end="00:00")
    for i in range(MAX_PER_DAY):
        assert notify(db, owner=owner, kind="k", title=f"t{i}", body="b") is not None
    assert notify(db, owner=owner, kind="k", title="extra", body="b") is None

    other = User(email="c@exemplo.com", password_hash="!")
    db.add(other)
    db.commit()
    set_paused(db, True, actor_user_id=None, reason="teste")
    assert notify(db, owner=other, kind="k", title="t", body="b") is None
