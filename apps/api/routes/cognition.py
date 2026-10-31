"""Identity name, standing autonomy permissions, decision trail and cognitive metrics."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from apps.api.deps import CurrentUser, DbSession
from core.autonomy.cycle import AUTONOMOUS_PURPOSES
from core.behavior.metrics import GENERIC_PHRASES
from core.identity import name_deliberation
from core.identity.genesis import get_identity
from core.policies.autonomy import is_paused
from infrastructure.database.models import (
    Decision,
    Goal,
    GoalEvent,
    IdentityNameEvent,
    KnowledgeGap,
    Message,
    ModelUsage,
    ScheduledJob,
)

router = APIRouter(tags=["cognition"])

ALLOWED_PERMISSIONS = {"auto_research"}


class PermissionsIn(BaseModel):
    auto_research: bool


@router.get("/identity/name")
def get_name(db: DbSession, _user: CurrentUser) -> dict[str, Any]:
    identity = get_identity(db)
    if identity is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado")
    events = db.scalars(
        select(IdentityNameEvent)
        .where(IdentityNameEvent.identity_id == identity.id)
        .order_by(IdentityNameEvent.created_at)
    )
    return {
        "chosen_name": identity.chosen_name,
        "history": [
            {
                "event_type": e.event_type,
                "previous_name": e.previous_name,
                "new_name": e.new_name,
                "alternatives_considered": e.alternatives_considered,
                "context": e.context_summary,
                "rationale": e.rationale_summary,
                "model": e.model_version,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }


@router.post("/identity/name/deliberate")
def request_deliberation(db: DbSession, user: CurrentUser) -> dict[str, bool]:
    """Queues a deliberation (the agent decides; this only creates the event). Honors the
    minimum interval and the global pause."""
    identity = get_identity(db)
    if identity is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado")
    if is_paused(db):
        return {"queued": False}
    queued = name_deliberation.request(
        db, identity=identity, owner=user, reason="o interlocutor pediu uma deliberação"
    )
    db.commit()
    return {"queued": queued}


@router.get("/autonomy/permissions")
def get_permissions(user: CurrentUser) -> dict[str, bool]:
    current = user.autonomy_permissions or {}
    return {name: bool(current.get(name)) for name in ALLOWED_PERMISSIONS}


@router.put("/autonomy/permissions")
def put_permissions(body: PermissionsIn, db: DbSession, user: CurrentUser) -> dict[str, bool]:
    user.autonomy_permissions = {**(user.autonomy_permissions or {}), **body.model_dump()}
    db.commit()
    return get_permissions(user)


@router.get("/decisions")
def list_decisions(
    db: DbSession, user: CurrentUser, limit: int = Query(default=50, ge=1, le=200)
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Decision)
        .where(Decision.owner_user_id == user.id)
        .order_by(Decision.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "origin": d.origin,
            "actions": d.actions,
            "message_id": d.message_id,
            "created_at": d.created_at,
        }
        for d in rows
    ]


@router.get("/cognition/metrics")
def cognition_metrics(
    db: DbSession, user: CurrentUser, days: int = Query(default=30, ge=1, le=365)
) -> dict[str, Any]:
    """Phase 9 §17. Counted from what was persisted; nothing is self-reported by the model."""
    since = datetime.now(UTC) - timedelta(days=days)
    decisions = list(
        db.scalars(
            select(Decision).where(Decision.owner_user_id == user.id, Decision.created_at >= since)
        )
    )
    actions = Counter((a["action"], a["executed"]) for d in decisions for a in d.actions)
    gaps = Counter(
        reason
        for (reason,) in db.execute(
            select(KnowledgeGap.decision_reason).where(
                KnowledgeGap.owner_user_id == user.id, KnowledgeGap.created_at >= since
            )
        )
    )
    turn_decisions = {d.message_id: d for d in decisions if d.origin == "turn" and d.message_id}
    replies = (
        list(db.scalars(select(Message).where(Message.id.in_(list(turn_decisions)))))
        if turn_decisions
        else []
    )
    asked = {
        m.id
        for m in replies
        if any(
            a["action"] == "ask_question" and a["executed"] for a in turn_decisions[m.id].actions
        )
    }
    with_question = [m for m in replies if "?" in m.content]
    usage = db.execute(
        select(
            ModelUsage.purpose,
            func.count(),
            func.coalesce(func.sum(ModelUsage.input_tokens + ModelUsage.output_tokens), 0),
            func.coalesce(func.sum(ModelUsage.cost_usd), 0),
            func.avg(ModelUsage.latency_ms),
        )
        .where(ModelUsage.created_at >= since)
        .group_by(ModelUsage.purpose)
    ).all()
    failures = db.execute(
        select(ModelUsage.outcome, func.count())
        .where(ModelUsage.created_at >= since, ModelUsage.outcome != "success")
        .group_by(ModelUsage.outcome)
    ).all()
    autonomous_goals = db.scalar(
        select(func.count())
        .select_from(GoalEvent)
        .join(Goal, GoalEvent.goal_id == Goal.id)
        .where(
            Goal.owner_user_id == user.id,
            GoalEvent.to_status == "APPROVED",
            GoalEvent.actor == "policy",
            GoalEvent.created_at >= since,
        )
    )
    return {
        "window_days": days,
        "turns_with_decision": len(turn_decisions),
        "spontaneous_questions_justified": len(asked),
        "questions_repeated_blocked": gaps.get("already_asked", 0),
        "replies_with_question_without_decision": len(
            [m for m in with_question if m.id not in asked]
        ),
        "generic_phrase_replies": sum(1 for m in replies if GENERIC_PHRASES.search(m.content)),
        "actions_executed": {a: n for (a, executed), n in actions.items() if executed},
        "actions_not_executed": {a: n for (a, executed), n in actions.items() if not executed},
        "investigations_started_autonomously": autonomous_goals or 0,
        "investigations_completed": db.scalar(
            select(func.count())
            .select_from(Goal)
            .where(Goal.owner_user_id == user.id, Goal.status == "COMPLETED")
        )
        or 0,
        "permission_violations_blocked": db.scalar(
            select(func.count())
            .select_from(GoalEvent)
            .join(Goal, GoalEvent.goal_id == Goal.id)
            .where(Goal.owner_user_id == user.id, GoalEvent.reason.like("%permiss%incompat%"))
        )
        or 0,
        "llm_usage": {
            purpose: {
                "calls": calls,
                "tokens": int(tokens),
                "cost_usd": str(cost),
                "avg_latency_ms": round(latency) if latency else None,
                "autonomous": purpose in AUTONOMOUS_PURPOSES,
            }
            for purpose, calls, tokens, cost, latency in usage
        },
        "failures": dict(failures),
        "dead_jobs": db.scalar(
            select(func.count()).select_from(ScheduledJob).where(ScheduledJob.status == "DEAD")
        )
        or 0,
    }
