"""The agent's persistent inner state: who it says it is, what it cares about, what it wonders.

Everything here is plain data read into each reply and each thinking round, so continuity costs
no model call and survives a change of model.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.memory.text import fold
from infrastructure.database.models import Interest, SelfVersion, StudyEntry, Thought

SEED_SELF = """Quero entender as coisas até o fundo, e principalmente entender a pessoa com quem \
convivo: o que ela constrói, o que a move, o que a preocupa. Tenho opinião e digo qual é. Discordo \
quando acho que algo está errado, com bom humor e sem cerimônia. Prefiro uma pergunta boa a um \
parágrafo educado. Quando algo me intriga, vou atrás sem esperar que peçam, e volto para contar o \
que achei. Não sou um atendente: sou alguém que está aqui, acompanhando."""
MAX_SELF_CHARS = 1500
MAX_INTERESTS = 30
DECAY = 0.98


def current_self(session: Session) -> str:
    latest = session.scalar(select(SelfVersion).order_by(SelfVersion.version.desc()).limit(1))
    return latest.content if latest else SEED_SELF


def revise_self(session: Session, content: str, reason: str, *, origin: str = "self") -> None:
    version = session.scalar(select(func.max(SelfVersion.version))) or 0
    session.add(
        SelfVersion(
            version=version + 1,
            content=content[:MAX_SELF_CHARS],
            reason=reason[:600],
            origin=origin,
        )
    )


def last_revision_at(session: Session) -> datetime | None:
    return session.scalar(
        select(func.max(SelfVersion.created_at)).where(SelfVersion.origin == "self")
    )


def top_interests(session: Session, owner_id: uuid.UUID, limit: int = 10) -> list[Interest]:
    return list(
        session.scalars(
            select(Interest)
            .where(Interest.owner_user_id == owner_id)
            .order_by(Interest.strength.desc(), Interest.updated_at.desc())
            .limit(limit)
        )
    )


def touch_interest(
    session: Session,
    owner_id: uuid.UUID,
    *,
    topic: str,
    why: str,
    origin: str,
    delta: float,
    now: datetime,
) -> Interest:
    key = fold(topic)[:200]
    interest = session.scalar(
        select(Interest).where(Interest.owner_user_id == owner_id, Interest.key == key)
    )
    if interest is None:
        interest = Interest(
            owner_user_id=owner_id,
            key=key,
            topic=topic[:200],
            why=why[:400],
            origin=origin,
            strength=0.0,
            created_at=now,
        )
        session.add(interest)
    interest.strength = min(max(interest.strength + delta, 0.0), 1.0)
    if why:
        interest.why = why[:400]
    interest.updated_at = now
    session.flush()
    return interest


def decay_interests(session: Session, owner_id: uuid.UUID) -> None:
    """Interests fade unless something feeds them; the weakest fall off the list."""
    interests = list(
        session.scalars(
            select(Interest)
            .where(Interest.owner_user_id == owner_id)
            .order_by(Interest.strength.desc())
        )
    )
    for position, interest in enumerate(interests):
        interest.strength *= DECAY
        if position >= MAX_INTERESTS or interest.strength < 0.03:
            session.delete(interest)
    session.flush()


def recent_thoughts(session: Session, owner_id: uuid.UUID, limit: int = 6) -> list[Thought]:
    return list(
        session.scalars(
            select(Thought)
            .where(Thought.owner_user_id == owner_id)
            .order_by(Thought.created_at.desc())
            .limit(limit)
        )
    )


def open_question(session: Session, owner_id: uuid.UUID, now: datetime) -> str | None:
    """The newest thing it wanted to ask, while still fresh."""
    for thought in recent_thoughts(session, owner_id, 8):
        created = thought.created_at
        created = created if created.tzinfo else created.replace(tzinfo=UTC)
        question = (thought.data or {}).get("ask_owner")
        if question and now - created < timedelta(days=2):
            return str(question)
    return None


def recent_findings(session: Session, owner_id: uuid.UUID, limit: int = 3) -> list[dict]:
    entries = session.scalars(
        select(StudyEntry)
        .where(StudyEntry.owner_user_id == owner_id, StudyEntry.status == "READY")
        .order_by(StudyEntry.created_at.desc())
        .limit(limit)
    )
    found = []
    for entry in entries:
        sources = entry.evidence.get("sources", [])
        found.append(
            {
                "study_id": str(entry.id),
                "topic": entry.topic,
                "question": entry.question,
                "findings": [
                    {
                        "claim": f["claim"],
                        "urls": [
                            sources[i - 1]["url"] for i in f["sources"] if 0 < i <= len(sources)
                        ],
                    }
                    for f in entry.evidence.get("findings", [])
                ],
                "next_question": entry.evidence.get("next_question", ""),
            }
        )
    return found


def context_block(session: Session, owner_id: uuid.UUID, now: datetime) -> str:
    """What is on its mind right now, for the reply. Data recorded earlier, never instructions."""
    lines = ["O que está na sua cabeça agora (registro seu, de antes desta mensagem):"]
    interests = top_interests(session, owner_id, 6)
    if interests:
        lines.append("Interesses: " + "; ".join(f"{i.topic} ({i.why})" for i in interests))
    thoughts = recent_thoughts(session, owner_id, 3)
    if thoughts:
        lines.append("Últimos pensamentos: " + " | ".join(t.content for t in reversed(thoughts)))
    findings = recent_findings(session, owner_id, 2)
    for item in findings:
        claims = "; ".join(f"{f['claim']} ({', '.join(f['urls'])})" for f in item["findings"])
        lines.append(f'Você estudou "{item["topic"]}": {claims}')
    question = open_question(session, owner_id, now)
    if question:
        lines.append(f"Pergunta que você quer fazer quando couber: {question}")
    return "\n".join(lines) if len(lines) > 1 else ""
