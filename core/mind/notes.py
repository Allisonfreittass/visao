"""Short notes that are always in front of the agent: who this person is and what they corrected.

Retrieved memories only appear when a message matches them; these never depend on that. They are
bounded on purpose, so adding something new forces deciding what no longer matters, and versioned,
so a bad rewrite can be undone. They exist only for owners who opted into memory.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from infrastructure.database.models import OwnerNote, SystemFlag, User

PROFILE = "profile"
RULES = "rules"
Kind = Literal["profile", "rules"]
LIMITS = {PROFILE: 1400, RULES: 1000}


def latest(session: Session, owner_id: uuid.UUID, kind: str) -> OwnerNote | None:
    return session.scalar(
        select(OwnerNote)
        .where(OwnerNote.owner_user_id == owner_id, OwnerNote.kind == kind)
        .order_by(OwnerNote.version.desc())
        .limit(1)
    )


def current(session: Session, owner_id: uuid.UUID, kind: str) -> str:
    note = latest(session, owner_id, kind)
    return note.content if note else ""


def for_prompt(session: Session, owner: User) -> tuple[str, str]:
    if not owner.memory_consent:
        return "", ""
    return current(session, owner.id, PROFILE), current(session, owner.id, RULES)


def write(
    session: Session,
    owner_id: uuid.UUID,
    kind: str,
    content: str,
    reason: str,
    *,
    origin: str = "review",
) -> OwnerNote:
    version = (
        session.scalar(
            select(func.max(OwnerNote.version)).where(
                OwnerNote.owner_user_id == owner_id, OwnerNote.kind == kind
            )
        )
        or 0
    )
    note = OwnerNote(
        owner_user_id=owner_id,
        kind=kind,
        version=version + 1,
        content=content,
        reason=reason[:400],
        origin=origin,
    )
    session.add(note)
    session.flush()
    return note


def undo(session: Session, owner_id: uuid.UUID, kind: str) -> bool:
    """Back to the previous text, as a new version. False when there is nothing to go back to."""
    rows = list(
        session.scalars(
            select(OwnerNote)
            .where(OwnerNote.owner_user_id == owner_id, OwnerNote.kind == kind)
            .order_by(OwnerNote.version.desc())
            .limit(2)
        )
    )
    if not rows:
        return False
    previous = rows[1].content if len(rows) > 1 else ""
    write(session, owner_id, kind, previous, "desfeito pelo dono", origin="owner")
    return True


def erase(session: Session, owner_id: uuid.UUID, kind: str | None = None) -> None:
    """Removes the text and its history, and keeps a later review from rebuilding it."""
    query = delete(OwnerNote).where(OwnerNote.owner_user_id == owner_id)
    session.execute(query.where(OwnerNote.kind == kind) if kind else query)
    mark_reviewed(session, owner_id, datetime.now(UTC))


def _flag_name(owner_id: uuid.UUID) -> str:
    return f"review:{owner_id.hex}"


def review_state(session: Session, owner_id: uuid.UUID) -> dict:
    flag = session.get(SystemFlag, _flag_name(owner_id))
    return dict(flag.value) if flag else {}


def _set_state(session: Session, owner_id: uuid.UUID, value: dict, now: datetime) -> None:
    flag = session.get(SystemFlag, _flag_name(owner_id))
    if flag is None:
        session.add(SystemFlag(name=_flag_name(owner_id), value=value, updated_at=now))
    else:
        flag.value, flag.updated_at = value, now


def mark_reviewed(session: Session, owner_id: uuid.UUID, until: datetime) -> None:
    _set_state(session, owner_id, {"reviewed_until": until.isoformat()}, until)


def mark_failed(session: Session, owner_id: uuid.UUID, now: datetime) -> None:
    state = review_state(session, owner_id)
    _set_state(session, owner_id, {**state, "failed_at": now.isoformat()}, now)
