"""Lexical + recency + confidence retrieval, always scoped to one owner.

Semantic (embedding) retrieval is Phase 3b. Relational memories (what the person told about
themselves) stay eligible without word overlap, because questions like "do you remember me?"
share no words with them.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.memory.text import overlap, tokens
from infrastructure.database.models import MemoryRecord

DEFAULT_LIMIT = 5
MAX_PROMPT_CHARS = 2000
RELATIONAL_FLOOR = 0.2
RECENCY_WEIGHT = 0.1
RECENCY_HALF_LIFE_DAYS = 30.0


@dataclass(frozen=True)
class ScoredMemory:
    record: MemoryRecord
    score: float


def _age_days(created_at: datetime, now: datetime) -> float:
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return max((now - created).total_seconds() / 86400, 0.0)


def score(record: MemoryRecord, query_tokens: set[str], now: datetime) -> float | None:
    """None means "not relevant enough to include"."""
    lexical = overlap(query_tokens, tokens(record.content))
    floor = RELATIONAL_FLOOR if record.memory_type == "relational" else 0.0
    if lexical == 0.0 and floor == 0.0:
        return None
    recency = math.exp(-_age_days(record.created_at, now) * math.log(2) / RECENCY_HALF_LIFE_DAYS)
    return (lexical + floor) * (0.5 + 0.5 * record.confidence) + RECENCY_WEIGHT * recency


def retrieve(
    session: Session,
    owner_user_id: uuid.UUID,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    max_chars: int = MAX_PROMPT_CHARS,
) -> list[ScoredMemory]:
    now = datetime.now(UTC)
    records = session.scalars(
        select(MemoryRecord).where(
            MemoryRecord.owner_user_id == owner_user_id,
            or_(MemoryRecord.valid_until.is_(None), MemoryRecord.valid_until > now),
        )
    )
    query_tokens = tokens(query)
    scored = [
        ScoredMemory(record, value)
        for record in records
        if (value := score(record, query_tokens, now)) is not None
    ]
    scored.sort(key=lambda item: item.score, reverse=True)

    selected: list[ScoredMemory] = []
    used = 0
    for item in scored[:limit]:
        if used + len(item.record.content) > max_chars:
            break
        selected.append(item)
        used += len(item.record.content)
    return selected
