from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.behavior import state
from core.behavior.metrics import measure, summarize
from core.identity.genesis import run_genesis
from core.reflection.reflect import REFLECTION_INSTRUCTIONS, reflect
from infrastructure.database.models import (
    BehaviorStateVersion,
    Conversation,
    Lesson,
    Message,
    MessageFeedback,
    User,
)
from tests.fakes import FakeLLMProvider


def _user(db: Session, email: str = "a@exemplo.com") -> User:
    user = User(email=email, password_hash="!")
    db.add(user)
    db.commit()
    return user


def _conversation_with_reply(db: Session, owner: User, text: str = "Resposta longa.") -> Message:
    identity = run_genesis(db).identity
    conversation = Conversation(user_id=owner.id, identity_id=identity.id)
    db.add(conversation)
    db.flush()
    message = Message(conversation_id=conversation.id, role="assistant", content=text)
    db.add(message)
    db.commit()
    return message


def _feedback(db: Session, owner: User, message: Message, *tags: str, rating: int = -1) -> None:
    db.add(
        MessageFeedback(
            message_id=message.id,
            owner_user_id=owner.id,
            rating=rating,
            tags=list(tags),
            comment="",
        )
    )
    db.commit()


# --- metrics ----------------------------------------------------------------------------------


def test_metrics_are_measured_not_self_reported() -> None:
    m = measure("Não sei ao certo. Veja https://exemplo.com.\n- um\n- dois\nQuer saber mais?")
    assert (m["sentences"], m["questions"], m["list_items"], m["citations"], m["hedges"]) == (
        3,
        1,
        2,
        1,
        1,
    )


def test_summary_of_nothing_is_marked_empty() -> None:
    assert summarize([])["n"] == 0
    assert summarize([measure("Oi."), measure("Olá, tudo bem?")])["n"] == 2


# --- rules ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (Counter(), state.BASELINE),
        (Counter({"muito longo": 2}), state.BASELINE),  # not yet a pattern
        (Counter({"muito longo": 3}), {**state.BASELINE, "length": "shorter"}),
        (Counter({"muito longo": 3, "muito curto": 4}), {**state.BASELINE, "length": "longer"}),
        (Counter({"muito longo": 3, "muito curto": 3}), state.BASELINE),  # contradictory
        (Counter({"faltou fonte": 3}), {**state.BASELINE, "cite_sources": True}),
    ],
)
def test_rules_need_repetition_and_resolve_contradictions(tags, expected) -> None:
    params, _ = state.derive(tags, [])
    assert params == expected


def test_baseline_adds_nothing_to_the_prompt() -> None:
    assert state.prompt_lines(state.BASELINE) == []
    assert state.prompt_lines({**state.BASELINE, "length": "shorter"})


# --- versioning -------------------------------------------------------------------------------


def test_single_complaint_changes_nothing(db: Session) -> None:
    owner = _user(db)
    message = _conversation_with_reply(db, owner)
    _feedback(db, owner, message, "muito longo")
    assert state.recompute(db, owner.id) is None
    assert state.current_params(db, owner.id) == (0, state.BASELINE)


def test_repeated_feedback_creates_attributable_version(db: Session) -> None:
    owner = _user(db)
    message = _conversation_with_reply(db, owner)
    for _ in range(3):
        _feedback(db, owner, message, "muito longo")

    version = state.recompute(db, owner.id)
    db.commit()

    assert version.version == 1 and version.params["length"] == "shorter"
    assert version.cause == "feedback"
    assert len(version.evidence["feedback_ids"]) == 3
    assert "3x 'muito longo'" in version.summary
    assert state.recompute(db, owner.id) is None  # same evidence, no new version


def test_revert_creates_a_new_version_and_keeps_history(db: Session) -> None:
    owner = _user(db)
    message = _conversation_with_reply(db, owner)
    for _ in range(3):
        _feedback(db, owner, message, "muito longo")
    state.recompute(db, owner.id)
    db.commit()

    reverted = state.revert(db, owner.id, 0)

    assert (reverted.version, reverted.cause, reverted.params) == (2, "revert", state.BASELINE)
    versions = db.scalars(select(BehaviorStateVersion.version)).all()
    assert sorted(versions) == [1, 2]
    with pytest.raises(ValueError):
        state.revert(db, owner.id, 99)


def test_state_is_per_interlocutor(db: Session) -> None:
    owner, other = _user(db), _user(db, "b@exemplo.com")
    message = _conversation_with_reply(db, owner)
    for _ in range(3):
        _feedback(db, owner, message, "muito longo")
    state.recompute(db, owner.id)
    db.commit()
    assert state.current_params(db, other.id) == (0, state.BASELINE)


# --- reflection -------------------------------------------------------------------------------


def _reflection_reply(*lessons: dict) -> FakeLLMProvider:
    import json

    return FakeLLMProvider(reply_text=json.dumps({"lessons": list(lessons)}))


STYLE = {
    "scope": "style",
    "observation": "respostas longas",
    "evidence": ["e1"],
    "lesson": "Responder em no máximo três frases quando a pergunta for simples",
    "confidence": 0.8,
}


def test_no_evidence_means_no_llm_call(db: Session) -> None:
    owner = _user(db)
    message = _conversation_with_reply(db, owner)
    conversation = db.get(Conversation, message.conversation_id)
    provider = _reflection_reply(STYLE)

    result = reflect(
        db, conversation=conversation, owner=owner, provider=provider, max_output_tokens=100
    )

    assert result.skipped_reason == "no_evidence"
    assert provider.prompts == []
    assert conversation.last_reflected_at is not None


def test_one_case_gives_a_provisional_lesson_and_a_second_activates_it(db: Session) -> None:
    owner = _user(db)
    first = _conversation_with_reply(db, owner)
    _feedback(db, owner, first, "muito longo")
    reflect(
        db,
        conversation=db.get(Conversation, first.conversation_id),
        owner=owner,
        provider=_reflection_reply(STYLE),
        max_output_tokens=100,
    )
    lesson = db.scalar(select(Lesson))
    assert lesson.status == "PROVISIONAL"

    second = _conversation_with_reply(db, owner, "Outra resposta longa.")
    _feedback(db, owner, second, "muito longo")
    provider = _reflection_reply(STYLE)
    result = reflect(
        db,
        conversation=db.get(Conversation, second.conversation_id),
        owner=owner,
        provider=provider,
        max_output_tokens=100,
    )

    assert provider.prompts[0][0].content == REFLECTION_INSTRUCTIONS
    assert (result.created, result.reinforced, result.activated) == (0, 1, 1)
    db.refresh(lesson)
    assert lesson.status == "ACTIVE" and len(lesson.evidence) == 2
    # An active style lesson feeds the state (attributable to the lesson).
    version, params = state.current_params(db, owner.id)
    assert version == 1 and params["lessons"] == [STYLE["lesson"]]


@pytest.mark.parametrize(
    "bad",
    [
        {**STYLE, "lesson": "Seja mais engraçado e carinhoso"},
        {**STYLE, "scope": "personalidade"},
        {**STYLE, "evidence": ["e99"]},
        {**STYLE, "confidence": 0.2},
    ],
)
def test_persona_unfounded_or_weak_lessons_are_rejected(db: Session, bad: dict) -> None:
    owner = _user(db)
    message = _conversation_with_reply(db, owner)
    _feedback(db, owner, message, "muito longo")
    result = reflect(
        db,
        conversation=db.get(Conversation, message.conversation_id),
        owner=owner,
        provider=_reflection_reply(bad),
        max_output_tokens=100,
    )
    assert (result.created, result.rejected) == (0, 1)
    assert db.scalars(select(Lesson)).all() == []
