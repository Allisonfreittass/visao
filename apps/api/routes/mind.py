"""A window into the agent's inner state, and the owner's undo for its self-description."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from apps.api.deps import AppSettings, CurrentUser, DbSession
from core.mind import state
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


class MindOut(BaseModel):
    enabled: bool
    self_text: str
    interests: list[InterestOut]
    thoughts: list[ThoughtOut]
    self_history: list[SelfVersionOut]


class RevertIn(BaseModel):
    version: int | None = None  # None goes back to the original description


@router.get("")
def read_mind(db: DbSession, user: CurrentUser, settings: AppSettings) -> MindOut:
    history = db.scalars(select(SelfVersion).order_by(SelfVersion.version.desc()).limit(10))
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
    )


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
