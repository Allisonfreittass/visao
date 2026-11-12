"""What it wants to ask the owner: each question asked once, at a fitting moment, kept with the
answer so it never asks the same thing twice.

A thought proposes a question (`offer`). The reply or an opening that actually asks it marks it
asked (`notice_assistant_text`); the owner's next message after that is taken as the answer
(`notice_owner_reply`). Answers are personal: they are kept only with memory consent and are
erased with the rest of the memory.
"""

import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.database.models import OwnerQuestion, User

WAITING_FOR = timedelta(days=3)  # unasked after this, it was not that important
REMEMBER_FOR = timedelta(days=30)  # no repeats inside this window
MAX_WAITING = 3
_STOP = {
    "você",
    "voce",
    "para",
    "como",
    "isso",
    "esse",
    "essa",
    "este",
    "esta",
    "qual",
    "quais",
    "quando",
    "onde",
    "porque",
    "sobre",
    "mais",
    "menos",
    "muito",
    "ainda",
    "algo",
    "alguma",
    "algum",
    "pode",
    "acha",
    "seria",
    "fazer",
    "está",
    "estar",
    "tem",
    "tinha",
    "foi",
    "sua",
    "seu",
    "suas",
    "seus",
    "que",
    "com",
    "uma",
    "dos",
    "das",
    "nos",
    "nas",
    "pelo",
    "pela",
}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _words(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) >= 4 and w not in _STOP}


def similar(a: str, b: str, threshold: float = 0.5) -> bool:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return a.strip().lower() == b.strip().lower()
    return len(wa & wb) / len(wa | wb) >= threshold


def asks(text: str, question: str) -> bool:
    """Whether a message really puts this question: one of its questions covers most of it."""
    key = _words(question)
    if not key:
        return False
    for sentence in re.findall(r"[^.!?\n]*\?", text):
        if len(key & _words(sentence)) / len(key) >= 0.6:
            return True
    return False


def _recent(session: Session, owner_id: uuid.UUID, now: datetime) -> list[OwnerQuestion]:
    return list(
        session.scalars(
            select(OwnerQuestion)
            .where(
                OwnerQuestion.owner_user_id == owner_id,
                OwnerQuestion.created_at >= now - REMEMBER_FOR,
            )
            .order_by(OwnerQuestion.created_at.desc())
        )
    )


def expire(session: Session, owner_id: uuid.UUID, now: datetime) -> None:
    for item in _recent(session, owner_id, now):
        if item.status == "waiting" and now - _utc(item.created_at) > WAITING_FOR:
            item.status = "dropped"
    session.flush()


def offer(session: Session, owner_id: uuid.UUID, text: str, now: datetime) -> OwnerQuestion | None:
    """Queue a question unless it (or something close) was already queued, asked or answered."""
    text = text.strip()[:400]
    if len(text) < 8:
        return None
    expire(session, owner_id, now)
    recent = _recent(session, owner_id, now)
    if any(similar(text, item.text) for item in recent if item.status != "dropped"):
        return None
    question = OwnerQuestion(
        owner_user_id=owner_id, text=text, status="waiting", answer="", created_at=now
    )
    session.add(question)
    waiting = [item for item in recent if item.status == "waiting"]
    for stale in waiting[MAX_WAITING - 1 :]:
        stale.status = "dropped"
    session.flush()
    return question


def next_to_ask(session: Session, owner_id: uuid.UUID, now: datetime) -> OwnerQuestion | None:
    expire(session, owner_id, now)
    return next((q for q in _recent(session, owner_id, now) if q.status == "waiting"), None)


def notice_assistant_text(
    session: Session, owner_id: uuid.UUID, text: str, message_id: uuid.UUID | None, now: datetime
) -> None:
    for item in _recent(session, owner_id, now):
        if item.status == "waiting" and asks(text, item.text):
            item.status, item.asked_at, item.asked_message_id = "asked", now, message_id
    session.flush()


def notice_owner_reply(session: Session, owner: User, text: str, now: datetime) -> None:
    for item in _recent(session, owner.id, now):
        if item.status == "asked" and item.asked_at is not None and _utc(item.asked_at) < now:
            item.status, item.answered_at = "answered", now
            item.answer = text.strip()[:600] if owner.memory_consent else ""
    session.flush()


def for_context(session: Session, owner_id: uuid.UUID, now: datetime) -> list[dict]:
    """What it already asked and what is still queued, so a new thought does not repeat it."""
    rows = [q for q in _recent(session, owner_id, now) if q.status != "dropped"][:8]
    return [
        {"question": q.text, "status": q.status, **({"answer": q.answer} if q.answer else {})}
        for q in rows
    ]


def erase(session: Session, owner_id: uuid.UUID) -> None:
    for item in session.scalars(
        select(OwnerQuestion).where(OwnerQuestion.owner_user_id == owner_id)
    ):
        session.delete(item)
    session.flush()


def export(session: Session, owner_id: uuid.UUID) -> list[dict]:
    return [
        {
            "question": q.text,
            "status": q.status,
            "answer": q.answer,
            "created_at": _utc(q.created_at).isoformat(),
        }
        for q in session.scalars(
            select(OwnerQuestion)
            .where(OwnerQuestion.owner_user_id == owner_id)
            .order_by(OwnerQuestion.created_at)
        )
    ]
