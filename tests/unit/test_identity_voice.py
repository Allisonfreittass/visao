import json

import pytest
from sqlalchemy.orm import Session

from core.identity.genesis import run_genesis
from core.identity.voice import (
    DELIBERATION_INSTRUCTIONS,
    DeliberationOutputError,
    VoiceDecision,
    deliberate_voice,
    record_voice_decision,
    resolve_voice,
    voice_history,
)
from integrations.tts.catalog import CATALOG, approved_voices, system_default
from tests.fakes import FakeLLMProvider

DORA = CATALOG["kokoro-dora"]
FABER = CATALOG["piper-faber"]


def _decision(**overrides: object) -> VoiceDecision:
    fields: dict[str, object] = {
        "action": "choose",
        "voice_id": "kokoro-dora",
        "rationale_summary": "teste",
        "model_provider": "fake",
        "model_version": "fake-1",
    }
    fields.update(overrides)
    return VoiceDecision(**fields)  # type: ignore[arg-type]


def test_approved_list_parsing_ignores_unknown_ids() -> None:
    assert approved_voices(" kokoro-dora, inexistente ,") == [DORA]
    assert approved_voices("") == []


def test_system_default_is_lowest_latency_not_taste() -> None:
    assert system_default([DORA, FABER]) == FABER
    assert system_default([]) is None


def test_before_any_decision_the_default_is_labelled_as_system(db: Session) -> None:
    identity = run_genesis(db).identity
    resolved = resolve_voice(identity, [DORA])
    assert (resolved.spec, resolved.source) == (DORA, "system_default")
    assert resolve_voice(identity, []).source == "none"


def test_choice_is_recorded_and_used(db: Session) -> None:
    identity = run_genesis(db).identity
    event = record_voice_decision(db, identity, _decision(), [DORA, FABER])

    assert event.event_type == "CHOSEN"
    assert event.options_offered == ["kokoro-dora", "piper-faber"]
    assert resolve_voice(identity, [DORA, FABER]).source == "chosen"


def test_choice_outside_approved_list_is_refused(db: Session) -> None:
    identity = run_genesis(db).identity
    with pytest.raises(ValueError):
        record_voice_decision(db, identity, _decision(voice_id="piper-faber"), [DORA])


def test_withdrawn_approval_falls_back_to_system_default(db: Session) -> None:
    identity = run_genesis(db).identity
    record_voice_decision(db, identity, _decision(), [DORA, FABER])
    resolved = resolve_voice(identity, [FABER])
    assert (resolved.spec, resolved.source) == (FABER, "system_default")


@pytest.mark.parametrize(("action", "event_type"), [("defer", "DEFERRED"), ("decline", "DECLINED")])
def test_defer_and_decline_keep_no_voice(db: Session, action: str, event_type: str) -> None:
    identity = run_genesis(db).identity
    event = record_voice_decision(db, identity, _decision(action=action, voice_id=None), [DORA])
    assert event.event_type == event_type
    assert identity.chosen_voice is None
    assert [e.event_type for e in voice_history(db, identity)] == [event_type]


def test_change_keeps_history_and_uuid(db: Session) -> None:
    identity = run_genesis(db).identity
    original = identity.id
    record_voice_decision(db, identity, _decision(), [DORA, FABER])
    event = record_voice_decision(db, identity, _decision(voice_id="piper-faber"), [DORA, FABER])
    assert (event.event_type, event.previous_voice) == ("CHANGED", "kokoro-dora")
    assert identity.id == original
    assert len(voice_history(db, identity)) == 2


def test_deliberation_records_the_models_decision(db: Session) -> None:
    identity = run_genesis(db).identity
    reply = json.dumps({"action": "choose", "voice_id": "kokoro-dora", "rationale": "única opção"})
    provider = FakeLLMProvider(reply_text=reply)

    event = deliberate_voice(db, identity, [DORA], provider, max_output_tokens=100)

    assert identity.chosen_voice == "kokoro-dora"
    assert event.rationale_summary == "única opção"
    prompt = provider.prompts[0]
    assert prompt[0].content == DELIBERATION_INSTRUCTIONS
    assert "id=kokoro-dora" in prompt[1].content
    # Defer and decline are offered as real options; nothing pushes a choice.
    assert "adiar" in DELIBERATION_INSTRUCTIONS and "recusar" in DELIBERATION_INSTRUCTIONS


def test_deliberation_can_defer(db: Session) -> None:
    identity = run_genesis(db).identity
    provider = FakeLLMProvider(reply_text='{"action": "defer", "voice_id": null, "rationale": "x"}')
    event = deliberate_voice(db, identity, [DORA], provider, max_output_tokens=100)
    assert event.event_type == "DEFERRED"
    assert identity.chosen_voice is None


@pytest.mark.parametrize("reply", ["não sei", '{"action": "talvez"}'])
def test_unreadable_deliberation_records_nothing(db: Session, reply: str) -> None:
    identity = run_genesis(db).identity
    with pytest.raises(DeliberationOutputError):
        deliberate_voice(
            db, identity, [DORA], FakeLLMProvider(reply_text=reply), max_output_tokens=9
        )
    assert voice_history(db, identity) == []
