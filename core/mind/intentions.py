"""Things the agent decided to bring up later, at a time it picked itself.

Without this it could only speak in the round where a thought happened to occur, so "ask how the
race went" came out before the race. An intention is a note to its future self: when the time
comes a thinking round runs with fresh context and decides again whether it is still worth
saying. Nothing is sent from here.
"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.initiatives.notify import deliver_after
from core.memory.text import fold
from infrastructure.database.models import Intention, User
from infrastructure.jobs import queue

PENDING, DONE, DROPPED = "PENDING", "DONE", "DROPPED"
JOB_KIND = "mind_think"
MAX_PENDING = 8
MIN_AHEAD = timedelta(minutes=5)
MAX_AHEAD = timedelta(days=30)
POSTPONE_BY = timedelta(minutes=20)
GIVE_UP_AFTER = timedelta(hours=12)
WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def local(owner: User, moment: datetime) -> str:
    """The owner's wall clock, the only time the model should reason in."""
    there = _utc(moment).astimezone(ZoneInfo(owner.timezone))
    return f"{WEEKDAYS[there.weekday()]} {there:%d/%m/%Y %H:%M}"


def local_iso(owner: User, moment: datetime) -> str:
    """Same clock, in the shape the model is asked to answer in (AAAA-MM-DDTHH:MM)."""
    return f"{_utc(moment).astimezone(ZoneInfo(owner.timezone)):%Y-%m-%dT%H:%M}"


def parse_when(owner: User, value: object) -> datetime | None:
    """ISO date-time from the model; without an offset it means the owner's local time."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(owner.timezone))
    return moment.astimezone(UTC)


def pending(session: Session, owner_id: uuid.UUID) -> list[Intention]:
    return list(
        session.scalars(
            select(Intention)
            .where(Intention.owner_user_id == owner_id, Intention.status == PENDING)
            .order_by(Intention.due_at)
        )
    )


def due(session: Session, owner_id: uuid.UUID, now: datetime) -> list[Intention]:
    return [item for item in pending(session, owner_id) if _utc(item.due_at) <= now]


def _wake(session: Session, intention: Intention) -> None:
    # Event-based: the hourly cycle would be too coarse for "at half past nine".
    queue.enqueue(
        session,
        kind=JOB_KIND,
        owner_user_id=intention.owner_user_id,
        payload={"owner_id": str(intention.owner_user_id), "intention_id": str(intention.id)},
        idempotency_key=f"intention:{intention.id}:{int(_utc(intention.due_at).timestamp())}",
        reason="Algo que ele decidiu retomar nesta hora",
        run_after=intention.due_at,
        max_attempts=2,
    )


def plan(
    session: Session, owner: User, *, about: str, when: datetime, now: datetime
) -> Intention | None:
    """Records it, moved past the quiet hours when it lands inside them. None when refused."""
    about = " ".join(about.split())[:400]
    if not about or not (now + MIN_AHEAD <= when <= now + MAX_AHEAD):
        return None
    current = pending(session, owner.id)
    key = fold(about)
    if len(current) >= MAX_PENDING or any(fold(item.about) == key for item in current):
        return None
    intention = Intention(
        owner_user_id=owner.id,
        about=about,
        due_at=deliver_after(owner, when),
        status=PENDING,
        created_at=now,
    )
    session.add(intention)
    session.flush()
    _wake(session, intention)
    return intention


def resolve(intention: Intention, status: str, outcome: str, now: datetime) -> None:
    intention.status, intention.outcome, intention.resolved_at = status, outcome[:64], now


def postpone(session: Session, owner: User, intention: Intention, now: datetime) -> None:
    """It could not speak right now (the owner is mid-conversation, quiet hours): try again
    soon, and let go once the moment has clearly passed."""
    first_due = intention.outcome.removeprefix("postponed:") or _utc(intention.due_at).isoformat()
    if now - datetime.fromisoformat(first_due) > GIVE_UP_AFTER:
        resolve(intention, DROPPED, "moment_passed", now)
        return
    intention.outcome = f"postponed:{first_due}"
    intention.due_at = deliver_after(owner, now + POSTPONE_BY)
    session.flush()
    _wake(session, intention)
