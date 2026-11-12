"""What is still open between it and the owner: work on the Mac, what waits for a yes, and whether
the things it said on its own got an answer.

A model only exists inside one call; between calls it is exactly what it is shown. Without this,
"I'll tell you when it's done" was only text: the next round of thought did not know the Mac had
finished, nor that its last three openings went unanswered.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.arm import service as arm
from core.goals import lifecycle
from infrastructure.database.models import ArmDevice, ArmTask, Conversation, Goal, Message, User

FINISHED_WINDOW = timedelta(hours=24)
OPENINGS_WINDOW = timedelta(days=7)
ANSWER_WINDOW = timedelta(hours=24)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Opening:
    said: str
    at: datetime
    answered: bool


def _owner_times(session: Session, owner: User, since: datetime) -> list[datetime]:
    rows = session.scalars(
        select(Message.created_at)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.user_id == owner.id,
            Message.role == "user",
            Message.created_at >= since,
        )
        .order_by(Message.created_at)
    )
    return [_utc(t) for t in rows]


def openings(
    session: Session, owner: User, now: datetime, window: timedelta = OPENINGS_WINDOW
) -> list[Opening]:
    """Its own openings, newest first, each with whether the owner answered within a day."""
    since = now - window
    rows = session.execute(
        select(Message.content, Message.created_at)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.user_id == owner.id,
            Message.origin == "initiative",
            Message.created_at >= since,
        )
        .order_by(Message.created_at.desc())
    ).all()
    replies = _owner_times(session, owner, since)
    found = []
    for content, created in rows:
        at = _utc(created)
        answered = any(at < t <= at + ANSWER_WINDOW for t in replies)
        found.append(Opening(content[:200], at, answered))
    return found


def unanswered_streak(items: list[Opening]) -> int:
    """How many of its newest openings in a row got no answer."""
    streak = 0
    for item in items:
        if item.answered:
            break
        streak += 1
    return streak


def devices(session: Session, owner: User) -> list[ArmDevice]:
    return list(session.scalars(select(ArmDevice).where(ArmDevice.owner_user_id == owner.id)))


def mac_projects(session: Session, owner: User) -> list[str]:
    return sorted(
        {p for d in devices(session, owner) for p in (d.projects or []) if isinstance(p, str)}
    )


def open_loops(session: Session, owner: User, now: datetime) -> dict:
    tasks = list(
        session.scalars(
            select(ArmTask)
            .where(ArmTask.owner_user_id == owner.id, ArmTask.created_at >= now - timedelta(days=7))
            .order_by(ArmTask.created_at.desc())
            .limit(20)
        )
    )
    owner_times = _owner_times(session, owner, now - FINISHED_WINDOW)
    machines = devices(session, owner)
    loops: dict = {
        "mac": {
            "projects": mac_projects(session, owner),
            "online": any(arm.online(d, now) for d in machines),
        }
        if machines
        else None,
        "mac_running": [
            {"project": t.project, "task": t.prompt[:200], "status": t.status}
            for t in tasks
            if t.status in ("approved", "running")
        ],
        "mac_finished": [
            {
                "project": t.project,
                "task": t.prompt[:200],
                "status": t.status,
                "result": (t.result or t.error)[:300],
                "owner_spoke_since": any(x > _utc(t.finished_at) for x in owner_times),
            }
            for t in tasks
            if t.status in ("done", "failed")
            and t.finished_at is not None
            and now - _utc(t.finished_at) < FINISHED_WINDOW
        ],
        "waiting_for_owner": [
            {"kind": "mac", "project": t.project, "task": t.prompt[:200]}
            for t in tasks
            if t.status == "proposed"
        ]
        + [
            {"kind": "goal", "title": g.title[:200]}
            for g in session.scalars(
                select(Goal).where(
                    Goal.owner_user_id == owner.id, Goal.status == lifecycle.EVALUATED
                )
            )
        ],
        "my_openings": [
            {"said": o.said, "at": o.at.isoformat(), "answered": o.answered}
            for o in openings(session, owner, now)[:6]
        ],
    }
    return loops


def chat_lines(loops: dict) -> list[str]:
    """The same picture, short, for a reply."""
    lines = []
    for t in loops["mac_running"]:
        where = "rodando" if t["status"] == "running" else "na fila"
        lines.append(f"No Mac, {where}: {t['project']}: {t['task']}")
    for t in loops["mac_finished"]:
        what = "terminou" if t["status"] == "done" else "falhou"
        lines.append(
            f"No Mac, {what} há pouco: {t['project']}: {t['task']}. Resultado: {t['result']}"
        )
    waiting = loops["waiting_for_owner"]
    if waiting:
        lines.append(
            "Esperando o sim da pessoa: "
            + "; ".join(
                f"{w['project']}: {w['task']}" if w["kind"] == "mac" else w["title"]
                for w in waiting
            )
        )
    return lines
