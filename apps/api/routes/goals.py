"""Goals, approvals, initiatives, notifications and the global autonomy switch."""

import re
import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from apps.api.deps import CurrentUser, DbSession
from core.goals import lifecycle
from core.mind import initiative
from core.policies.autonomy import is_paused, set_paused
from infrastructure.database.models import Conversation, Goal, Notification, ScheduledJob

router = APIRouter(tags=["goals"])

LIMIT = 50
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class GoalEventOut(BaseModel):
    from_status: str | None
    to_status: str
    actor: str
    reason: str
    created_at: datetime


class GoalOut(BaseModel):
    id: uuid.UUID
    origin: str
    kind: str
    title: str
    rationale: str
    success_criteria: str
    required_permissions: list[str]
    budget: dict[str, Any]
    status: str
    evidence: dict[str, Any] | None
    created_at: datetime
    history: list[GoalEventOut]


class ReasonIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    goal_id: uuid.UUID | None
    created_at: datetime
    deliver_after: datetime
    read_at: datetime | None


class NotificationReplyIn(BaseModel):
    conversation_id: uuid.UUID | None = None


class NotificationReplyOut(BaseModel):
    conversation_id: uuid.UUID


class InitiativeOut(BaseModel):
    id: uuid.UUID
    kind: str
    reason: str
    status: str
    attempts: int
    max_attempts: int
    run_after: datetime
    last_error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    finished_at: datetime | None


class QuietHours(BaseModel):
    quiet_start: str
    quiet_end: str
    timezone: str

    @field_validator("quiet_start", "quiet_end")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        if not _HHMM.match(value):
            raise ValueError("use HH:MM")
        return value

    @field_validator("timezone")
    @classmethod
    def _zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown timezone") from exc
        return value


class AutonomyIn(BaseModel):
    paused: bool
    reason: str = Field(default="", max_length=500)


def _goal_out(db: DbSession, goal: Goal) -> GoalOut:
    return GoalOut(
        id=goal.id,
        origin=goal.origin,
        kind=goal.kind,
        title=goal.title,
        rationale=goal.rationale,
        success_criteria=goal.success_criteria,
        required_permissions=goal.required_permissions,
        budget=goal.budget,
        status=goal.status,
        evidence=goal.evidence,
        created_at=goal.created_at,
        history=[
            GoalEventOut(
                from_status=e.from_status,
                to_status=e.to_status,
                actor=e.actor,
                reason=e.reason,
                created_at=e.created_at,
            )
            for e in lifecycle.history(db, goal)
        ],
    )


def _own_goal(db: DbSession, user: CurrentUser, goal_id: uuid.UUID) -> Goal:
    goal = db.get(Goal, goal_id)
    if goal is None or goal.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meta não encontrada")
    return goal


def _transition(action) -> None:
    try:
        action()
    except lifecycle.TransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/goals")
def list_goals(db: DbSession, user: CurrentUser) -> list[GoalOut]:
    goals = db.scalars(
        select(Goal)
        .where(Goal.owner_user_id == user.id)
        .order_by(Goal.created_at.desc())
        .limit(LIMIT)
    )
    return [_goal_out(db, g) for g in goals]


@router.get("/approvals")
def pending_approvals(db: DbSession, user: CurrentUser) -> list[GoalOut]:
    """Goals the agent proposed that passed evaluation and wait for the owner's decision."""
    goals = db.scalars(
        select(Goal)
        .where(Goal.owner_user_id == user.id, Goal.status == lifecycle.EVALUATED)
        .order_by(Goal.created_at.desc())
    )
    return [_goal_out(db, g) for g in goals]


@router.post("/goals/{goal_id}/approve")
def approve_goal(goal_id: uuid.UUID, db: DbSession, user: CurrentUser) -> GoalOut:
    goal = _own_goal(db, user, goal_id)
    _transition(lambda: lifecycle.approve(db, goal, user, payload={}))
    return _goal_out(db, goal)


@router.post("/goals/{goal_id}/reject")
def reject_goal(goal_id: uuid.UUID, body: ReasonIn, db: DbSession, user: CurrentUser) -> GoalOut:
    goal = _own_goal(db, user, goal_id)
    _transition(lambda: lifecycle.reject(db, goal, user, body.reason))
    return _goal_out(db, goal)


@router.post("/goals/{goal_id}/cancel")
def cancel_goal(goal_id: uuid.UUID, body: ReasonIn, db: DbSession, user: CurrentUser) -> GoalOut:
    goal = _own_goal(db, user, goal_id)
    _transition(lambda: lifecycle.cancel(db, goal, user, body.reason))
    return _goal_out(db, goal)


@router.get("/initiatives")
def list_initiatives(db: DbSession, user: CurrentUser) -> list[InitiativeOut]:
    """Everything queued on the agent's initiative for this owner, with why it exists."""
    jobs = db.scalars(
        select(ScheduledJob)
        .where(ScheduledJob.owner_user_id == user.id)
        .order_by(ScheduledJob.created_at.desc())
        .limit(LIMIT)
    )
    return [
        InitiativeOut(
            id=j.id,
            kind=j.kind,
            reason=j.reason,
            status=j.status,
            attempts=j.attempts,
            max_attempts=j.max_attempts,
            run_after=j.run_after,
            last_error=j.last_error.splitlines()[0] if j.last_error else None,
            result=j.result,
            created_at=j.created_at,
            finished_at=j.finished_at,
        )
        for j in jobs
    ]


@router.get("/notifications")
def list_notifications(db: DbSession, user: CurrentUser) -> list[NotificationOut]:
    """Delivered notifications only: those held by quiet hours appear when the window ends."""
    now = datetime.now(UTC)
    rows = db.scalars(
        select(Notification)
        .where(Notification.owner_user_id == user.id, Notification.deliver_after <= now)
        .order_by(Notification.created_at.desc())
        .limit(LIMIT)
    )
    return [
        NotificationOut(
            id=n.id,
            kind=n.kind,
            title=n.title,
            body=n.body,
            goal_id=n.goal_id,
            created_at=n.created_at,
            deliver_after=n.deliver_after,
            read_at=n.read_at,
        )
        for n in rows
    ]


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificação não encontrada")
    notification.read_at = notification.read_at or datetime.now(UTC)
    db.commit()


@router.post("/notifications/{notification_id}/reply")
def reply_to_notification(
    notification_id: uuid.UUID, body: NotificationReplyIn, db: DbSession, user: CurrentUser
) -> NotificationReplyOut:
    """A notice is one-way; answering it moves it into a conversation, where it has a reply box
    and the agent has the context. Initiative messages are already there."""
    notification = db.get(Notification, notification_id)
    if notification is None or notification.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificação não encontrada")
    conversation = db.get(Conversation, body.conversation_id) if body.conversation_id else None
    if conversation is None or conversation.user_id != user.id:
        conversation = initiative.conversation_for(db, user)
    if conversation is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Execute o genesis primeiro")
    now = datetime.now(UTC)
    if notification.read_at is None:
        if notification.kind != "initiative":
            initiative.open_in_chat(db, conversation, notification.body, now)
        notification.read_at = now
    db.commit()
    return NotificationReplyOut(conversation_id=conversation.id)


@router.get("/notifications/settings")
def get_quiet_hours(user: CurrentUser) -> QuietHours:
    return QuietHours(
        quiet_start=user.quiet_start, quiet_end=user.quiet_end, timezone=user.timezone
    )


@router.put("/notifications/settings")
def put_quiet_hours(body: QuietHours, db: DbSession, user: CurrentUser) -> QuietHours:
    user.quiet_start, user.quiet_end, user.timezone = (
        body.quiet_start,
        body.quiet_end,
        body.timezone,
    )
    db.commit()
    return body


@router.get("/system/autonomy")
def get_autonomy(db: DbSession, _user: CurrentUser) -> dict[str, bool]:
    return {"paused": is_paused(db)}


@router.put("/system/autonomy")
def put_autonomy(body: AutonomyIn, db: DbSession, user: CurrentUser) -> dict[str, bool]:
    """Emergency switch for everything the agent does on its own initiative."""
    set_paused(db, body.paused, actor_user_id=user.id, reason=body.reason)
    return {"paused": is_paused(db)}
