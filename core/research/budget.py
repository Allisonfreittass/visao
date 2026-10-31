"""Shared daily search count for chat, follow-ups and autonomous study."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from infrastructure.database.models import ResearchSession, StudyEntry


def searches_today(session: Session, owner_id: uuid.UUID, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    research = (
        session.scalar(
            select(func.count())
            .select_from(ResearchSession)
            .where(
                ResearchSession.owner_user_id == owner_id,
                ResearchSession.created_at >= since,
            )
        )
        or 0
    )
    entries = session.scalars(
        select(StudyEntry).where(
            StudyEntry.owner_user_id == owner_id,
            StudyEntry.created_at >= since,
            StudyEntry.search_query != "",
        )
    )
    study = sum(
        len(entry.evidence["search_queries"])
        if isinstance(entry.evidence.get("search_queries"), list)
        else 1
        for entry in entries
    )
    return research + study
