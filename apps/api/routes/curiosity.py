"""Audit trail of curiosity: what gaps were detected, what was decided, what was searched."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from apps.api.deps import CurrentUser, DbSession
from infrastructure.database.models import KnowledgeGap, ResearchSession, ResearchSource

router = APIRouter(tags=["curiosity"])

LIMIT = 50


class SourceOut(BaseModel):
    rank: int
    title: str
    url: str
    source: str
    snippet: str
    updated_at: datetime | None
    retrieved_at: datetime


class ResearchOut(BaseModel):
    id: uuid.UUID
    gap_id: uuid.UUID
    query: str
    provider: str
    status: str
    error_kind: str | None
    elapsed_ms: int
    created_at: datetime
    sources: list[SourceOut]


class GapOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    trigger_kind: str
    depends_on: str
    question: str
    hypothesis: str
    scores: dict[str, Any]
    chosen_action: str
    decision_reason: str
    status: str
    resolution_summary: str
    created_at: datetime
    resolved_at: datetime | None


def _research_out(db: DbSession, research: ResearchSession) -> ResearchOut:
    sources = db.scalars(
        select(ResearchSource)
        .where(ResearchSource.session_id == research.id)
        .order_by(ResearchSource.rank)
    )
    return ResearchOut(
        id=research.id,
        gap_id=research.gap_id,
        query=research.query,
        provider=research.provider,
        status=research.status,
        error_kind=research.error_kind,
        elapsed_ms=research.elapsed_ms,
        created_at=research.created_at,
        sources=[
            SourceOut(
                rank=s.rank,
                title=s.title,
                url=s.url,
                source=s.source,
                snippet=s.snippet,
                updated_at=s.updated_at,
                retrieved_at=s.retrieved_at,
            )
            for s in sources
        ],
    )


@router.get("/knowledge-gaps")
def list_gaps(db: DbSession, user: CurrentUser) -> list[GapOut]:
    gaps = db.scalars(
        select(KnowledgeGap)
        .where(KnowledgeGap.owner_user_id == user.id)
        .order_by(KnowledgeGap.created_at.desc())
        .limit(LIMIT)
    )
    return [
        GapOut(
            id=g.id,
            conversation_id=g.conversation_id,
            trigger_kind=g.trigger_kind,
            depends_on=g.depends_on,
            question=g.question,
            hypothesis=g.hypothesis,
            scores=g.scores,
            chosen_action=g.chosen_action,
            decision_reason=g.decision_reason,
            status=g.status,
            resolution_summary=g.resolution_summary,
            created_at=g.created_at,
            resolved_at=g.resolved_at,
        )
        for g in gaps
    ]


@router.get("/research")
def list_research(db: DbSession, user: CurrentUser) -> list[ResearchOut]:
    sessions = db.scalars(
        select(ResearchSession)
        .where(ResearchSession.owner_user_id == user.id)
        .order_by(ResearchSession.created_at.desc())
        .limit(LIMIT)
    )
    return [_research_out(db, r) for r in sessions]
