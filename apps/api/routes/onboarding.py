"""First run: what the agent is, a few questions and the permissions, once per person.

The answers are the person's own words, so they go straight to the permanent notes with no model
in between, and only with memory consent. The flag and the audit record only that it finished:
they never carry the text.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from apps.api.deps import AppSettings, CurrentUser, DbSession
from core.memory.policy import _SECRETS
from core.mind import notes
from infrastructure.database.audit import record_audit
from infrastructure.database.models import SystemFlag, User

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

NOTE_NAMES = {notes.PROFILE: "suas respostas sobre você", notes.RULES: "o jeito de falar"}


class Answers(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # No answer can be longer than the note it goes into; refused early, never truncated.
    who: str = Field(default="", max_length=notes.LIMITS[notes.PROFILE])
    work: str = Field(default="", max_length=notes.LIMITS[notes.PROFILE])
    goal: str = Field(default="", max_length=notes.LIMITS[notes.PROFILE])
    tone: str = Field(default="", max_length=notes.LIMITS[notes.RULES])


class FinishIn(BaseModel):
    skip: bool = False
    answers: Answers = Field(default_factory=Answers)


class OnboardingOut(BaseModel):
    completed: bool
    mind_enabled: bool
    room: dict[str, int]  # characters still free in each note


class FinishOut(BaseModel):
    completed: bool = True
    skipped: bool = False
    saved: list[str] = []
    discarded: bool = False  # the person wrote something and it was not kept


def _flag_name(owner_id: uuid.UUID) -> str:
    return f"onboarding:{owner_id.hex}"


def _additions(answers: Answers) -> dict[str, str]:
    profile = [
        f"{label}: {value}"
        for label, value in (
            ("Quem é", answers.who),
            ("Trabalha com", answers.work),
            ("Espera do agente", answers.goal),
        )
        if value
    ]
    additions = {notes.PROFILE: "\n".join(profile)}
    if answers.tone:
        additions[notes.RULES] = f"Jeito de falar que a pessoa pediu: {answers.tone}"
    return {kind: text for kind, text in additions.items() if text}


def _merged(db: DbSession, user: User, answers: Answers) -> dict[str, str]:
    """The new text of each note, after what it already says. Refuses rather than cutting."""
    additions = _additions(answers)
    if any(pattern.search(text) for text in additions.values() for pattern in _SECRETS):
        raise HTTPException(
            422,
            "Isto parece ter senha, chave, CPF ou número de cartão, e eles não ficam guardados. "
            "Tire esse trecho e tente de novo: nada foi guardado.",
        )
    merged = {}
    for kind, addition in additions.items():
        existing = notes.current(db, user.id, kind).rstrip()
        merged[kind] = f"{existing}\n{addition}" if existing else addition
    over = [
        f"{len(text) - notes.LIMITS[kind]} caracteres em {NOTE_NAMES[kind]}"
        for kind, text in merged.items()
        if len(text) > notes.LIMITS[kind]
    ]
    if over:
        raise HTTPException(422, f"Não coube: corte {' e '.join(over)}. Nada foi guardado.")
    return merged


@router.get("")
def read_onboarding(db: DbSession, user: CurrentUser, settings: AppSettings) -> OnboardingOut:
    return OnboardingOut(
        completed=db.get(SystemFlag, _flag_name(user.id)) is not None,
        mind_enabled=settings.mind_enabled,
        room={
            kind: max(0, limit - len(notes.current(db, user.id, kind)))
            for kind, limit in notes.LIMITS.items()
        },
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def restart_onboarding(db: DbSession, user: CurrentUser) -> None:
    """Asks again, e.g. after skipping by accident. The notes stay; new answers add to them."""
    flag = db.get(SystemFlag, _flag_name(user.id))
    if flag is not None:
        db.delete(flag)
        record_audit(db, "onboarding.restarted", "success", actor_user_id=user.id)
    db.commit()


@router.post("")
def finish_onboarding(body: FinishIn, db: DbSession, user: CurrentUser) -> FinishOut:
    wrote = any(body.answers.model_dump().values())
    if body.skip and wrote:
        raise HTTPException(422, "Pular não leva respostas: nada foi guardado.")
    flag = db.get(SystemFlag, _flag_name(user.id))
    if flag is not None:  # a retry or a second tab: the notes were already decided
        return FinishOut(skipped=bool(flag.value.get("skipped")), discarded=wrote)

    merged = _merged(db, user, body.answers) if user.memory_consent else {}
    now = datetime.now(UTC)
    db.add(
        SystemFlag(
            name=_flag_name(user.id),
            value={"finished_at": now.isoformat(), "skipped": body.skip},
            updated_at=now,
        )
    )
    # The flag goes first: of two requests at once, only one gets past here and appends.
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return FinishOut(discarded=wrote)
    for kind, text in merged.items():
        notes.write(db, user.id, kind, text, "respostas do primeiro acesso", origin="owner")
    saved = list(merged)
    discarded = wrote and not saved
    record_audit(
        db,
        "onboarding.finished",
        "skipped" if body.skip else "completed",
        actor_user_id=user.id,
        details={"saved": saved, "discarded": discarded},
    )
    db.commit()
    return FinishOut(skipped=body.skip, saved=saved, discarded=discarded)
