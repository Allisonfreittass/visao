"""Feedback, adaptive behavior state (versioned, reversible), observable metrics and lessons."""

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from apps.api.deps import CurrentUser, DbSession
from core.behavior import state
from core.behavior.metrics import summarize
from core.reflection.reflect import retire
from infrastructure.database.models import (
    BehaviorObservation,
    BehaviorStateVersion,
    Conversation,
    Lesson,
    Message,
    MessageFeedback,
)

router = APIRouter(tags=["behavior"])


class FeedbackIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    tags: list[str] = Field(default_factory=list, max_length=6)
    comment: str = Field(default="", max_length=1000)

    @field_validator("rating")
    @classmethod
    def _non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("use 1 or -1")
        return value

    @field_validator("tags")
    @classmethod
    def _known_tags(cls, value: list[str]) -> list[str]:
        unknown = set(value) - state.ALLOWED_TAGS
        if unknown:
            raise ValueError(f"unknown tags: {sorted(unknown)}")
        return sorted(set(value))


class FeedbackOut(BaseModel):
    feedback_id: uuid.UUID
    state_version: int
    state_changed: bool


class StateVersionOut(BaseModel):
    version: int
    params: dict[str, Any]
    cause: str
    summary: str
    evidence: dict[str, Any]
    rules_version: str
    created_at: datetime


class StateOut(BaseModel):
    current_version: int
    params: dict[str, Any]
    prompt_adjustments: list[str]
    history: list[StateVersionOut]


class RevertIn(BaseModel):
    to_version: int = Field(ge=0)


class LessonOut(BaseModel):
    id: uuid.UUID
    scope: str
    observation: str
    lesson: str
    evidence: list[str]
    status: str
    confidence: float
    created_at: datetime
    updated_at: datetime


@router.post("/messages/{message_id}/feedback")
def give_feedback(
    message_id: uuid.UUID, body: FeedbackIn, db: DbSession, user: CurrentUser
) -> FeedbackOut:
    message = db.get(Message, message_id)
    conversation = db.get(Conversation, message.conversation_id) if message else None
    if message is None or conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada")
    if message.role != "assistant":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Só respostas recebem retorno")
    feedback = MessageFeedback(
        message_id=message.id,
        owner_user_id=user.id,
        rating=body.rating,
        tags=body.tags,
        comment=body.comment,
    )
    db.add(feedback)
    db.flush()
    new_version = state.recompute(db, user.id)
    db.commit()
    version, _ = state.current_params(db, user.id)
    return FeedbackOut(
        feedback_id=feedback.id, state_version=version, state_changed=new_version is not None
    )


def _state_out(db: DbSession, user: CurrentUser) -> StateOut:
    version, params = state.current_params(db, user.id)
    history = db.scalars(
        select(BehaviorStateVersion)
        .where(BehaviorStateVersion.owner_user_id == user.id)
        .order_by(BehaviorStateVersion.version)
    )
    return StateOut(
        current_version=version,
        params=params,
        prompt_adjustments=state.prompt_lines(params),
        history=[
            StateVersionOut(
                version=v.version,
                params=v.params,
                cause=v.cause,
                summary=v.summary,
                evidence=v.evidence,
                rules_version=v.rules_version,
                created_at=v.created_at,
            )
            for v in history
        ],
    )


@router.get("/behavior/state")
def get_state(db: DbSession, user: CurrentUser) -> StateOut:
    return _state_out(db, user)


@router.post("/behavior/state/revert")
def revert_state(body: RevertIn, db: DbSession, user: CurrentUser) -> StateOut:
    try:
        state.revert(db, user.id, body.to_version)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _state_out(db, user)


@router.get("/behavior/report")
def behavior_report(
    db: DbSession, user: CurrentUser, window: int = Query(default=20, ge=1, le=500)
) -> dict[str, Any]:
    """Longitudinal comparison from measured replies: first `window` vs last `window`, and the
    mean of each metric per state version (what changed, under which version)."""
    rows = list(
        db.scalars(
            select(BehaviorObservation)
            .where(BehaviorObservation.owner_user_id == user.id)
            .order_by(BehaviorObservation.created_at)
        )
    )
    by_version: dict[int, list[dict[str, int]]] = defaultdict(list)
    for row in rows:
        by_version[row.state_version].append(row.metrics)
    return {
        "observations": len(rows),
        "baseline": summarize([r.metrics for r in rows[:window]]),
        "recent": summarize([r.metrics for r in rows[-window:]]),
        "by_state_version": {v: summarize(m) for v, m in sorted(by_version.items())},
        "note": "Métricas calculadas em código sobre as respostas, não autodescrição do modelo.",
    }


@router.get("/lessons")
def list_lessons(db: DbSession, user: CurrentUser) -> list[LessonOut]:
    lessons = db.scalars(
        select(Lesson).where(Lesson.owner_user_id == user.id).order_by(Lesson.created_at.desc())
    )
    return [
        LessonOut(
            id=lesson.id,
            scope=lesson.scope,
            observation=lesson.observation,
            lesson=lesson.lesson,
            evidence=lesson.evidence,
            status=lesson.status,
            confidence=lesson.confidence,
            created_at=lesson.created_at,
            updated_at=lesson.updated_at,
        )
        for lesson in lessons
    ]


@router.post("/lessons/{lesson_id}/retire", status_code=status.HTTP_204_NO_CONTENT)
def retire_lesson(lesson_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None or lesson.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lição não encontrada")
    retire(db, lesson, user.id)
