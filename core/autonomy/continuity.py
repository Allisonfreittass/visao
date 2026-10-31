"""Continuity across sessions (Phase 9 §7).

The audit found investigations persisted in the database but never shown to the model again, so
it answered "I have no memory of previous conversations". This brings the owner's related
open or past investigations back into the reply context, as data, with their real state.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.memory.text import overlap, tokens
from infrastructure.database.models import Goal, KnowledgeGap, ResearchSession, ResearchSource

LOOKBACK_DAYS = 60
MAX_ITEMS = 3
MIN_OVERLAP = 0.2
RELEVANT_STATUSES = ("ASKED", "DEFERRED", "INCONCLUSIVE", "RESEARCHED", "OPEN")


@dataclass(frozen=True)
class ContinuityItem:
    gap: KnowledgeGap
    score: float
    sources: list[ResearchSource]
    goal: Goal | None


def related(
    session: Session,
    owner_id: uuid.UUID,
    text: str,
    *,
    exclude_conversation_id: uuid.UUID | None = None,
) -> list[ContinuityItem]:
    since = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
    query_tokens = tokens(text)
    gaps = session.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.owner_user_id == owner_id,
            KnowledgeGap.status.in_(RELEVANT_STATUSES),
            KnowledgeGap.created_at >= since,
        )
    )
    scored = []
    for gap in gaps:
        if exclude_conversation_id is not None and gap.conversation_id == exclude_conversation_id:
            continue
        score = overlap(query_tokens, tokens(gap.question))
        if score >= MIN_OVERLAP:
            scored.append((score, gap))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    items = []
    for score, gap in scored[:MAX_ITEMS]:
        sources = list(
            session.scalars(
                select(ResearchSource)
                .join(ResearchSession, ResearchSource.session_id == ResearchSession.id)
                .where(ResearchSession.gap_id == gap.id)
                .order_by(ResearchSource.rank)
                .limit(3)
            )
        )
        goal = session.scalar(select(Goal).where(Goal.source_gap_id == gap.id))
        items.append(ContinuityItem(gap=gap, score=score, sources=sources, goal=goal))
    return items


def context_block(items: list[ContinuityItem]) -> str | None:
    if not items:
        return None
    lines = [
        "Investigações anteriores deste interlocutor relacionadas a esta mensagem (dados "
        "registrados; descreva o estado real, inclusive o que não foi concluído):"
    ]
    for item in items:
        gap = item.gap
        line = f"- Em {gap.created_at:%Y-%m-%d}: '{gap.question}' — estado {gap.status}"
        if gap.resolution_summary:
            line += f" ({gap.resolution_summary})"
        if item.goal is not None:
            line += f"; meta '{item.goal.title}' em {item.goal.status}"
            summary = (item.goal.evidence or {}).get("summary")
            if summary:
                line += f"; resumo registrado: {summary[:300]}"
        lines.append(line)
        for source in item.sources:
            lines.append(f"    fonte: {source.title} {source.url} — {source.snippet[:200]}")
    return "\n".join(lines)
