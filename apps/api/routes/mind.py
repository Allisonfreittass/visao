"""A window into the agent's inner state, and the owner's undo for its self-description."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from apps.api.deps import AppSettings, CurrentUser, DbSession
from core.mind import notes, questions, state
from core.mind import temperament as temper
from infrastructure.database.audit import record_audit
from infrastructure.database.models import SelfVersion

router = APIRouter(prefix="/mind", tags=["mind"])


class ThoughtOut(BaseModel):
    content: str
    created_at: datetime
    ask_owner: str = ""
    wanted_to_say: str = ""
    delivery: str | None = None


class InterestOut(BaseModel):
    topic: str
    why: str
    strength: float


class SelfVersionOut(BaseModel):
    version: int
    content: str
    reason: str
    created_at: datetime


class NoteOut(BaseModel):
    content: str = ""
    reason: str = ""
    limit: int
    updated_at: datetime | None = None


class TendencyOut(BaseModel):
    name: str
    value: float
    level: str
    why: str


class TemperamentOut(BaseModel):
    states: list[TendencyOut]
    traits: list[TendencyOut]
    avoids: list[TendencyOut]


class QuestionOut(BaseModel):
    question: str
    status: str
    answer: str = ""


class MindOut(BaseModel):
    enabled: bool
    self_text: str
    interests: list[InterestOut]
    thoughts: list[ThoughtOut]
    self_history: list[SelfVersionOut]
    profile: NoteOut
    rules: NoteOut
    temperament: TemperamentOut
    questions: list[QuestionOut]


class RevertIn(BaseModel):
    version: int | None = None  # None goes back to the original description


def _note(db: DbSession, user_id, kind: str) -> NoteOut:
    note = notes.latest(db, user_id, kind)
    if note is None:
        return NoteOut(limit=notes.LIMITS[kind])
    return NoteOut(
        content=note.content,
        reason=note.reason,
        limit=notes.LIMITS[kind],
        updated_at=note.created_at,
    )


def _tendency(t: temper.Tendency) -> TendencyOut:
    return TendencyOut(name=t.name, value=t.value, level=t.level, why=t.why)


@router.get("")
def read_mind(db: DbSession, user: CurrentUser, settings: AppSettings) -> MindOut:
    history = db.scalars(select(SelfVersion).order_by(SelfVersion.version.desc()).limit(10))
    now = datetime.now(UTC)
    mood = temper.compute(db, user, now)
    return MindOut(
        enabled=settings.mind_enabled,
        self_text=state.current_self(db),
        interests=[
            InterestOut(topic=i.topic, why=i.why, strength=i.strength)
            for i in state.top_interests(db, user.id, 12)
        ],
        thoughts=[
            ThoughtOut(
                content=t.content,
                created_at=t.created_at,
                ask_owner=(t.data or {}).get("ask_owner", ""),
                wanted_to_say=(t.data or {}).get("wanted_to_say", ""),
                delivery=(t.data or {}).get("delivery"),
            )
            for t in state.recent_thoughts(db, user.id, 12)
        ],
        self_history=[
            SelfVersionOut(
                version=v.version, content=v.content, reason=v.reason, created_at=v.created_at
            )
            for v in history
        ],
        profile=_note(db, user.id, notes.PROFILE),
        rules=_note(db, user.id, notes.RULES),
        temperament=TemperamentOut(
            states=[_tendency(t) for t in mood.states],
            traits=[_tendency(t) for t in mood.traits],
            avoids=[TendencyOut(name=n, value=0, level="evita", why=w) for n, w in temper.AVOIDS],
        ),
        questions=[QuestionOut(**q) for q in questions.for_context(db, user.id, now)],
    )


@router.post("/notes/{kind}/undo", status_code=status.HTTP_204_NO_CONTENT)
def undo_note(kind: notes.Kind, db: DbSession, user: CurrentUser) -> None:
    if not notes.undo(db, user.id, kind):
        raise HTTPException(404, "Nada para desfazer")
    db.commit()


@router.delete("/notes/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def erase_note(kind: notes.Kind, db: DbSession, user: CurrentUser) -> None:
    notes.erase(db, user.id, kind)
    record_audit(db, "mind.note_erased", "success", actor_user_id=user.id, details={"kind": kind})
    db.commit()


@router.post("/self/revert", status_code=status.HTTP_204_NO_CONTENT)
def revert_self(body: RevertIn, db: DbSession, user: CurrentUser) -> None:
    content = state.SEED_SELF
    if body.version is not None:
        version = db.scalar(select(SelfVersion).where(SelfVersion.version == body.version))
        if version is None:
            raise HTTPException(404, "Versão não encontrada")
        content = version.content
    state.revise_self(db, content, "revertido pelo dono", origin="owner")
    db.commit()
