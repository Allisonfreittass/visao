"""The owner's goals (docs/decisions/0025): read them and undo the last change. Writing one only
happens in the conversation, with the owner's yes (core/actions.py)."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.deps import CurrentUser, DbSession
from core import owner_goals
from infrastructure.database.audit import record_audit
from infrastructure.database.models import OwnerGoal

router = APIRouter(prefix="/owner-goals", tags=["owner-goals"])


class OwnerGoalOut(BaseModel):
    id: uuid.UUID
    content: str
    reason: str
    source_text: str
    source_message_id: uuid.UUID | None
    status: str
    replaces_id: uuid.UUID | None
    created_at: datetime
    ended_at: datetime | None


class OwnerGoalsOut(BaseModel):
    active: list[OwnerGoalOut]
    history: list[OwnerGoalOut]


class UndoOut(BaseModel):
    undone: str | None


def _out(goal: OwnerGoal) -> OwnerGoalOut:
    return OwnerGoalOut(
        id=goal.id,
        content=goal.content,
        reason=goal.reason,
        source_text=goal.source_text,
        source_message_id=goal.source_message_id,
        status=goal.status,
        replaces_id=goal.replaces_id,
        created_at=goal.created_at,
        ended_at=goal.ended_at,
    )


@router.get("")
def list_owner_goals(db: DbSession, user: CurrentUser) -> OwnerGoalsOut:
    return OwnerGoalsOut(
        active=[_out(g) for g in owner_goals.active(db, user.id)],
        history=[_out(g) for g in owner_goals.history(db, user.id)],
    )


@router.post("/undo")
def undo_last_change(db: DbSession, user: CurrentUser) -> UndoOut:
    """Undoes the newest change: an opened goal goes (the one it replaced comes back), or an
    ended goal comes back."""
    undone = owner_goals.undo_last(db, user.id)
    if undone:
        record_audit(db, "goal.undo", "success", actor_user_id=user.id, details={"what": undone})
    db.commit()
    return UndoOut(undone=undone)
