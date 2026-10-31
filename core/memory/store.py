"""Owner-facing memory operations: list, delete, export. Always scoped to one owner."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import (
    MemoryCandidate,
    MemoryDecision,
    MemoryRecord,
    MemorySource,
    User,
)


def list_records(session: Session, owner_id: uuid.UUID) -> list[MemoryRecord]:
    return list(
        session.scalars(
            select(MemoryRecord)
            .where(MemoryRecord.owner_user_id == owner_id)
            .order_by(MemoryRecord.created_at.desc())
        )
    )


def get_record(session: Session, owner_id: uuid.UUID, record_id: uuid.UUID) -> MemoryRecord | None:
    record = session.get(MemoryRecord, record_id)
    return record if record is not None and record.owner_user_id == owner_id else None


def source_message_ids(session: Session, record_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        session.scalars(select(MemorySource.message_id).where(MemorySource.record_id == record_id))
    )


def _scrub(candidate: MemoryCandidate, now: datetime) -> None:
    candidate.content = ""
    candidate.rationale = ""
    candidate.evidence_message_ids = []
    candidate.scrubbed_at = now


def delete_record(session: Session, owner: User, record: MemoryRecord) -> None:
    """Deletes the memory and scrubs its content from the candidate log. The append-only
    decision row keeps only codes, so nothing of the content survives."""
    candidate = session.get(MemoryCandidate, record.candidate_id)
    if candidate is not None:
        _scrub(candidate, datetime.now(UTC))
    session.delete(record)
    record_audit(session, "memory.delete", "success", actor_user_id=owner.id, details={"count": 1})
    session.commit()


def delete_all(session: Session, owner: User) -> int:
    """Deletes every memory of the owner and scrubs every candidate, stored or not."""
    now = datetime.now(UTC)
    records = list_records(session, owner.id)
    for record in records:
        session.delete(record)
    for candidate in session.scalars(
        select(MemoryCandidate).where(
            MemoryCandidate.owner_user_id == owner.id, MemoryCandidate.scrubbed_at.is_(None)
        )
    ):
        _scrub(candidate, now)
    record_audit(
        session,
        "memory.delete_all",
        "success",
        actor_user_id=owner.id,
        details={"count": len(records)},
    )
    session.commit()
    return len(records)


def decisions(
    session: Session, owner_id: uuid.UUID
) -> list[tuple[MemoryDecision, MemoryCandidate]]:
    rows = session.execute(
        select(MemoryDecision, MemoryCandidate)
        .join(MemoryCandidate, MemoryDecision.candidate_id == MemoryCandidate.id)
        .where(MemoryCandidate.owner_user_id == owner_id)
        .order_by(MemoryDecision.created_at.desc())
    )
    return [(decision, candidate) for decision, candidate in rows]


def export(session: Session, owner: User) -> dict[str, Any]:
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "memory_consent": owner.memory_consent,
        "records": [
            {
                "id": str(r.id),
                "type": r.memory_type,
                "content": r.content,
                "confidence": r.confidence,
                "created_at": r.created_at.isoformat(),
                "source_message_ids": [str(m) for m in source_message_ids(session, r.id)],
            }
            for r in list_records(session, owner.id)
        ],
        "decisions": [
            {
                "decision": d.decision,
                "reason_code": d.reason_code,
                "policy_version": d.policy_version,
                "proposed_type": c.memory_type,
                "proposed_content": c.content,
                "model_rationale": c.rationale,
                "scrubbed": c.scrubbed_at is not None,
                "created_at": d.created_at.isoformat(),
            }
            for d, c in decisions(session, owner.id)
        ],
    }
