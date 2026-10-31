import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from apps.api.deps import CurrentUser, DbSession
from core.memory import store
from core.memory.policy import REASONS
from core.memory.retrieval import retrieve
from infrastructure.database.audit import record_audit
from infrastructure.database.models import MemoryRecord

router = APIRouter(prefix="/memory", tags=["memory"])


class MemorySettings(BaseModel):
    enabled: bool


class MemoryOut(BaseModel):
    id: uuid.UUID
    type: str
    content: str
    confidence: float
    created_at: datetime
    source_message_ids: list[uuid.UUID]


class ScoredMemoryOut(MemoryOut):
    score: float


class DecisionOut(BaseModel):
    decision: str
    reason_code: str
    reason: str
    policy_version: str
    proposed_type: str
    proposed_content: str
    model_rationale: str
    scrubbed: bool
    created_at: datetime


def _memory_out(db: DbSession, record: MemoryRecord) -> MemoryOut:
    return MemoryOut(
        id=record.id,
        type=record.memory_type,
        content=record.content,
        confidence=record.confidence,
        created_at=record.created_at,
        source_message_ids=store.source_message_ids(db, record.id),
    )


@router.get("/settings")
def get_memory_settings(user: CurrentUser) -> MemorySettings:
    return MemorySettings(enabled=user.memory_consent)


@router.put("/settings")
def put_settings(body: MemorySettings, db: DbSession, user: CurrentUser) -> MemorySettings:
    """Opt in or out. Opting out stops curation and recall; existing memories stay until
    deleted with DELETE /memory."""
    user.memory_consent = body.enabled
    record_audit(
        db, "memory.consent", "success", actor_user_id=user.id, details={"enabled": body.enabled}
    )
    db.commit()
    return MemorySettings(enabled=user.memory_consent)


@router.get("")
def list_memories(db: DbSession, user: CurrentUser) -> list[MemoryOut]:
    return [_memory_out(db, r) for r in store.list_records(db, user.id)]


@router.get("/search")
def search_memories(
    db: DbSession, user: CurrentUser, q: str = Query(min_length=1, max_length=500)
) -> list[ScoredMemoryOut]:
    return [
        ScoredMemoryOut(**_memory_out(db, item.record).model_dump(), score=item.score)
        for item in retrieve(db, user.id, q, limit=20, max_chars=100_000)
    ]


@router.get("/decisions")
def list_decisions(db: DbSession, user: CurrentUser) -> list[DecisionOut]:
    return [
        DecisionOut(
            decision=d.decision,
            reason_code=d.reason_code,
            reason=REASONS.get(d.reason_code, d.reason_code),
            policy_version=d.policy_version,
            proposed_type=c.memory_type,
            proposed_content=c.content,
            model_rationale=c.rationale,
            scrubbed=c.scrubbed_at is not None,
            created_at=d.created_at,
        )
        for d, c in store.decisions(db, user.id)
    ]


@router.get("/export")
def export_memories(db: DbSession, user: CurrentUser) -> dict[str, Any]:
    return store.export(db, user)


@router.get("/{record_id}")
def get_memory(record_id: uuid.UUID, db: DbSession, user: CurrentUser) -> MemoryOut:
    record = store.get_record(db, user.id, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memória não encontrada")
    return _memory_out(db, record)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(record_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    record = store.get_record(db, user.id, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memória não encontrada")
    store.delete_record(db, user, record)


@router.delete("")
def delete_all_memories(db: DbSession, user: CurrentUser) -> dict[str, int]:
    return {"deleted": store.delete_all(db, user)}
