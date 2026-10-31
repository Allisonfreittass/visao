"""Owner-scoped study notebook and its explicit opt-in."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from apps.api.deps import CurrentUser, DbSession
from core.evolution.service import recent_runs
from core.policies.autonomy import is_paused
from core.study.service import INTERVAL, enabled, next_opportunity
from infrastructure.database.audit import record_audit
from infrastructure.database.models import StudyEntry, SystemFlag
from infrastructure.jobs import queue

router = APIRouter(prefix="/study", tags=["study"])


class StudySettingsIn(BaseModel):
    enabled: bool


def _out(entry: StudyEntry) -> dict[str, Any]:
    return {
        key: getattr(entry, key)
        for key in (
            "id",
            "previous_entry_id",
            "status",
            "topic",
            "question",
            "rationale",
            "evidence",
            "outcome_reason",
            "created_at",
            "finished_at",
        )
    }


@router.get("")
def notebook(db: DbSession, user: CurrentUser) -> dict[str, Any]:
    entries = list(
        db.scalars(
            select(StudyEntry)
            .where(
                StudyEntry.owner_user_id == user.id,
            )
            .order_by(StudyEntry.created_at.desc())
            .limit(12)
        )
    )
    scheduler = db.get(SystemFlag, "cloud_scheduler")
    return {
        "code_evolution": recent_runs(db),
        "scheduler": scheduler.value if scheduler else None,
        "enabled": enabled(user),
        "paused": is_paused(db),
        "interval_hours": int(INTERVAL.total_seconds() / 3600),
        "next_eligible_at": next_opportunity(entries[0]) if entries else None,
        "source": "Wikipédia em português",
        "entries": [_out(entry) for entry in entries],
    }


@router.put("/settings")
def settings(body: StudySettingsIn, db: DbSession, user: CurrentUser) -> dict[str, bool]:
    record_audit(
        db, "study.permission", "enabled" if body.enabled else "disabled", actor_user_id=user.id
    )
    user.autonomy_permissions = {**(user.autonomy_permissions or {}), "auto_study": body.enabled}
    if body.enabled and not is_paused(db):
        now = datetime.now(UTC)
        queue.enqueue(
            db,
            kind="cognitive_cycle",
            owner_user_id=user.id,
            payload={"study_owner": str(user.id)},
            idempotency_key=f"study-start:{user.id}:{int(now.timestamp() // 21600)}",
            reason="Estudo autônomo ativado pelo interlocutor",
            run_after=now,
            max_attempts=1,
        )
    db.commit()
    return {"enabled": enabled(user)}
