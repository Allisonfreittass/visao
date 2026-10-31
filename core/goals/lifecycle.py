"""Goal lifecycle (master prompt §9): PROPOSED -> EVALUATED -> APPROVED -> ACTIVE -> COMPLETED,
plus REJECTED / PAUSED / FAILED / CANCELLED. Every transition is validated and recorded
append-only. A proposal grants nothing; approval grants only the permissions the goal declared.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.policies.autonomy import is_paused
from infrastructure.database.audit import record_audit
from infrastructure.database.models import Goal, GoalEvent, ScheduledJob, User
from infrastructure.jobs import queue

PROPOSED = "PROPOSED"
EVALUATED = "EVALUATED"
APPROVED = "APPROVED"
ACTIVE = "ACTIVE"
COMPLETED = "COMPLETED"
REJECTED = "REJECTED"
PAUSED = "PAUSED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

TRANSITIONS: dict[str, set[str]] = {
    PROPOSED: {EVALUATED, REJECTED, CANCELLED},
    EVALUATED: {APPROVED, REJECTED, CANCELLED},
    APPROVED: {ACTIVE, PAUSED, CANCELLED},
    ACTIVE: {COMPLETED, FAILED, PAUSED, CANCELLED},
    PAUSED: {ACTIVE, CANCELLED},
    COMPLETED: set(),
    REJECTED: set(),
    FAILED: set(),
    CANCELLED: set(),
}

# Capabilities a goal may ask for. Anything else (sending messages outside the app, spending
# money, touching infrastructure...) is refused at evaluation, whatever the goal says.
ALLOWED_PERMISSIONS = frozenset({"web_research", "llm", "notify"})
MAX_BUDGET = {"searches": 5, "llm_calls": 3}

JOB_KIND_BY_GOAL = {"research_followup": "research_followup"}


class TransitionError(ValueError):
    pass


@dataclass(frozen=True)
class Evaluation:
    ok: bool
    reason: str


def transition(session: Session, goal: Goal, to: str, *, actor: str, reason: str) -> GoalEvent:
    if to not in TRANSITIONS.get(goal.status, set()):
        raise TransitionError(f"{goal.status} -> {to} is not allowed")
    event = GoalEvent(
        goal_id=goal.id, from_status=goal.status, to_status=to, actor=actor, reason=reason[:2000]
    )
    session.add(event)
    goal.status = to
    goal.updated_at = datetime.now(UTC)
    session.flush()
    return event


def evaluate(goal: Goal) -> Evaluation:
    """Deterministic: same goal, same verdict."""
    if not goal.success_criteria.strip():
        return Evaluation(False, "sem critério de sucesso")
    extra = set(goal.required_permissions) - ALLOWED_PERMISSIONS
    if extra:
        return Evaluation(False, f"permissões não permitidas: {sorted(extra)}")
    for key, limit in MAX_BUDGET.items():
        if int(goal.budget.get(key, 0)) > limit:
            return Evaluation(False, f"orçamento acima do limite ({key} > {limit})")
    if goal.kind not in JOB_KIND_BY_GOAL:
        return Evaluation(False, f"tipo de meta sem executor: {goal.kind}")
    return Evaluation(True, "dentro das permissões e do orçamento")


def propose(
    session: Session,
    *,
    owner: User,
    kind: str,
    title: str,
    rationale: str,
    success_criteria: str,
    required_permissions: list[str],
    budget: dict[str, Any],
    origin: str = "agent",
    source_gap_id: uuid.UUID | None = None,
) -> Goal | None:
    """Creates and immediately evaluates a goal. Returns None while autonomy is paused (agent
    proposals only)."""
    if origin == "agent" and is_paused(session):
        return None
    goal = Goal(
        owner_user_id=owner.id,
        origin=origin,
        kind=kind,
        title=title[:500],
        rationale=rationale[:2000],
        success_criteria=success_criteria[:1000],
        required_permissions=sorted(set(required_permissions)),
        budget=budget,
        source_gap_id=source_gap_id,
        status=PROPOSED,
    )
    session.add(goal)
    session.flush()
    session.add(
        GoalEvent(
            goal_id=goal.id,
            from_status=None,
            to_status=PROPOSED,
            actor=origin,
            reason=rationale[:2000],
        )
    )
    verdict = evaluate(goal)
    transition(
        session, goal, EVALUATED if verdict.ok else REJECTED, actor="policy", reason=verdict.reason
    )
    return goal


def _job_key(goal: Goal) -> str:
    return f"goal:{goal.id}:run"


def approve(session: Session, goal: Goal, user: User, payload: dict[str, Any]) -> ScheduledJob:
    if goal.owner_user_id != user.id:
        raise TransitionError("only the owner can approve")
    transition(session, goal, APPROVED, actor="user", reason="aprovada pelo interlocutor")
    job = queue.enqueue(
        session,
        kind=JOB_KIND_BY_GOAL[goal.kind],
        payload={"goal_id": str(goal.id), **payload},
        idempotency_key=_job_key(goal),
        reason=f"Meta aprovada: {goal.title}",
        owner_user_id=user.id,
    )
    record_audit(
        session, "goal.approve", "success", actor_user_id=user.id, details={"goal_id": str(goal.id)}
    )
    session.commit()
    return job


def reject(session: Session, goal: Goal, user: User, reason: str) -> None:
    if goal.owner_user_id != user.id:
        raise TransitionError("only the owner can reject")
    transition(
        session, goal, REJECTED, actor="user", reason=reason or "rejeitada pelo interlocutor"
    )
    session.commit()


def cancel(session: Session, goal: Goal, user: User, reason: str) -> None:
    if goal.owner_user_id != user.id:
        raise TransitionError("only the owner can cancel")
    transition(
        session, goal, CANCELLED, actor="user", reason=reason or "cancelada pelo interlocutor"
    )
    job = session.scalar(select(ScheduledJob).where(ScheduledJob.idempotency_key == _job_key(goal)))
    if job is not None:
        queue.cancel(session, job, "meta cancelada")
    session.commit()


def history(session: Session, goal: Goal) -> list[GoalEvent]:
    return list(
        session.scalars(
            select(GoalEvent).where(GoalEvent.goal_id == goal.id).order_by(GoalEvent.created_at)
        )
    )
