"""Learned rules are enforced on the finished reply, and that step can only ever fail open."""

import json
import time
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import select

from core.conversation import service
from core.conversation.service import PURPOSE_RULE_CHECK, Budgets, reply
from core.decision.pipeline import run_turn
from core.identity.system_prompt import RULE_CHECK_INSTRUCTIONS
from core.mind import notes
from infrastructure.database.models import (
    BehaviorObservation,
    Conversation,
    Message,
    ModelUsage,
)
from integrations.llm.base import LLMError
from tests.fakes import FakeLLMProvider
from tests.integration.test_phase9 import CONFIG, _world

RULES = "Não termine toda resposta com pergunta. Pergunte só quando for importante mesmo."
DRAFT = "Rust ganha em desempenho, mas Python é mais rápido de escrever. Qual é o worker?"
FIXED = "Rust ganha em desempenho, mas Python é mais rápido de escrever."


def is_check(prompt):
    return prompt[0].content == RULE_CHECK_INSTRUCTIONS


def llm(check, draft=DRAFT, **kwargs):
    """`check` is the text the rule check answers, or an exception it raises."""

    def respond(prompt):
        if not is_check(prompt):
            return draft
        if isinstance(check, Exception):
            raise check
        return check

    return FakeLLMProvider(responder=respond, **kwargs)


def rewrite(text):
    return json.dumps({"obeys": False, "rewrite": text}, ensure_ascii=False)


def world(db):
    identity, owner = _world(db)
    conversation = Conversation(user_id=owner.id, identity_id=identity.id)
    db.add(conversation)
    db.commit()
    return identity, owner, conversation


def turn(
    db, provider, rules=RULES, budgets=None, text="Rust ou Python pro worker?", modality="text"
):
    identity, owner, conversation = world(db)
    return reply(
        db,
        conversation=conversation,
        identity=identity,
        owner=owner,
        user_text=text,
        provider=provider,
        budgets=budgets or Budgets(daily_usd=Decimal("9"), conversation_usd=Decimal("9")),
        max_output_tokens=100,
        context_char_budget=4000,
        self_text="eu",
        owner_rules=rules,
        modality=modality,
    )


def checks(db):
    return list(db.scalars(select(ModelUsage).where(ModelUsage.purpose == PURPOSE_RULE_CHECK)))


def test_a_broken_rule_is_rewritten_and_only_the_final_text_is_kept(db):
    result = turn(db, llm(rewrite(FIXED)))
    assert result.assistant_message.content == FIXED
    saved = list(db.scalars(select(Message).where(Message.role == "assistant")))
    assert [m.content for m in saved] == [FIXED]
    observed = db.scalar(select(BehaviorObservation))
    assert observed.message_id == saved[0].id and observed.metrics["questions"] == 0
    assert result.usage.purpose == "chat_reply"
    assert saved[0].model_usage_id == result.usage.id
    assert [c.outcome for c in checks(db)] == ["rewritten"]


def test_a_voice_call_skips_the_check_so_the_reply_can_be_spoken_sooner(db):
    provider = llm(rewrite(FIXED))
    result = turn(db, provider, modality="voice")
    assert result.assistant_message.content == DRAFT
    assert checks(db) == []
    assert not any(is_check(p) for p in provider.prompts)
    assert RULES in provider.prompts[0][0].content


def test_a_reply_that_obeys_goes_out_untouched(db):
    result = turn(db, llm('{"obeys": true}'))
    assert result.assistant_message.content == DRAFT
    assert [c.outcome for c in checks(db)] == ["success"]


def test_a_rewrite_identical_to_the_reply_is_not_counted_as_one(db):
    result = turn(db, llm(rewrite(f"{DRAFT}\n")))
    assert result.assistant_message.content == DRAFT
    assert [c.outcome for c in checks(db)] == ["success"]


def test_the_check_is_counted_like_any_other_call(db):
    turn(db, llm('{"obeys": true}'))
    usage = checks(db)[0]
    assert (usage.provider, usage.input_tokens, usage.cost_usd) == (
        "fake-provider",
        1000,
        Decimal("0.002"),
    )
    assert usage.conversation_id is not None


def test_the_check_sees_rules_and_recent_endings_as_data(db):
    identity, owner, conversation = world(db)
    db.add(Message(conversation_id=conversation.id, role="assistant", content="Antes. E você?"))
    db.commit()
    provider = llm('{"obeys": true}')
    reply(
        db,
        conversation=conversation,
        identity=identity,
        owner=owner,
        user_text="oi de novo",
        provider=provider,
        budgets=Budgets(daily_usd=Decimal("9"), conversation_usd=Decimal("9")),
        max_output_tokens=100,
        context_char_budget=4000,
        self_text="eu",
        owner_rules=RULES,
    )
    data = json.loads(next(p for p in provider.prompts if is_check(p))[-1].content)
    assert data == {
        "regras": RULES,
        "mensagem": "oi de novo",
        "respostas_anteriores": ["Antes. E você?"],
        "resposta": DRAFT,
    }


@pytest.mark.parametrize(
    ("check", "outcome", "kind"),
    [
        (LLMError("http_500", "falha"), "error", "http_500"),
        (LLMError("budget_denied", "cota"), "error", "budget_denied"),
        (RuntimeError("ledger"), "error", "RuntimeError"),
        ("não é JSON", "bad_output", None),
        ("[1, 2]", "bad_output", None),
        ('{"obeys": "não", "rewrite": "x"}', "bad_output", None),
        ('{"obeys": false}', "bad_output", None),
        ('{"obeys": false, "rewrite": "   "}', "bad_output", None),
        ('{"obeys": false, "rewrite": 3}', "bad_output", None),
    ],
)
def test_any_failure_keeps_the_original_reply(db, check, outcome, kind):
    result = turn(db, llm(check))
    assert result.assistant_message.content == DRAFT
    assert [(c.outcome, c.error_kind) for c in checks(db)] == [(outcome, kind)]


def test_a_truncated_check_keeps_the_original_reply(db):
    def respond(prompt):
        provider.finish_reason = "length" if is_check(prompt) else "stop"
        return rewrite("Corta") if is_check(prompt) else DRAFT

    provider = FakeLLMProvider(responder=respond)
    result = turn(db, provider)
    assert result.assistant_message.content == DRAFT
    assert [c.outcome for c in checks(db)] == ["truncated"]


def test_a_check_past_the_deadline_does_not_hold_the_reply(db, monkeypatch):
    monkeypatch.setattr(service, "RULE_CHECK_DEADLINE_SECONDS", 0.01)

    def respond(prompt):
        if is_check(prompt):
            time.sleep(0.1)
        return DRAFT

    result = turn(db, FakeLLMProvider(responder=respond))
    assert result.assistant_message.content == DRAFT
    assert [(c.outcome, c.error_kind) for c in checks(db)] == [("error", "deadline")]


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Rust ganha em desempenho, veja https://exemplo.com/rust.", "new_url"),
        ("Rust ganha 30 vezes em desempenho.", "new_number"),
        ("Rust ganha em desempenho, segundo a Mozilla.", "new_name"),
        ("Pesquisei e Rust ganha em desempenho.", "new_action"),
        ("Rust ganha em desempenho, e eu li sobre isso.", "new_action"),
        (FIXED + " Isso vale também para quase todo serviço. " * 3, "longer"),
        ("Rust ganha em desempenho. Qual é o worker.", "question_as_statement"),
        ("Copiar tudo para outra máquina toda semana resolve sem esforço.", "new_words"),
    ],
)
def test_a_rewrite_cannot_add_claims_to_the_reply(db, text, reason):
    result = turn(db, llm(rewrite(text)))
    assert result.assistant_message.content == DRAFT
    assert [(c.outcome, c.error_kind) for c in checks(db)] == [("refused", reason)]


def test_a_rewrite_may_use_what_the_owner_said_and_what_the_reply_already_had(db):
    draft = "Li em https://exemplo.com que o Rust tem 3 vantagens. Quer que eu liste?"
    fixed = "Ali, li em https://exemplo.com que o Rust tem 3 vantagens."
    result = turn(db, llm(rewrite(fixed), draft=draft), rules="Me chame de Ali.")
    assert result.assistant_message.content == fixed


def test_no_budget_left_skips_the_check_without_failing_the_turn(db):
    provider = llm(rewrite(FIXED))
    budgets = Budgets(daily_usd=Decimal("0.001"), conversation_usd=Decimal("9"))
    result = turn(db, provider, budgets=budgets)
    assert result.assistant_message.content == DRAFT
    assert not any(is_check(p) for p in provider.prompts) and checks(db) == []


def test_without_rules_there_is_no_check(db):
    provider = llm(rewrite(FIXED))
    assert turn(db, provider, rules="").assistant_message.content == DRAFT
    assert len(provider.prompts) == 1


def test_a_cut_reply_is_not_rewritten_into_a_complete_one(db):
    provider = llm(rewrite(FIXED), finish_reason="length")
    result = turn(db, provider)
    assert result.assistant_message.content.startswith(DRAFT)
    assert service.TRUNCATION_NOTICE in result.assistant_message.content
    assert len(provider.prompts) == 1


@pytest.mark.parametrize(("draft", "calls"), [("De nada.", 1), ("Sério?", 2)])
def test_trivial_replies_skip_the_check_unless_they_ask_something(db, draft, calls):
    provider = llm('{"obeys": true}', draft=draft)
    turn(db, provider)
    assert len(provider.prompts) == calls


def test_the_reply_is_committed_before_the_check_calls_the_model(db):
    # The budget ledger takes SQLite's write lock in its own session during this call.
    pending = []

    def respond(prompt):
        if is_check(prompt):
            pending.extend([*db.new, *db.dirty])
        return '{"obeys": true}' if is_check(prompt) else DRAFT

    turn(db, FakeLLMProvider(responder=respond))
    assert pending == []


@pytest.mark.parametrize(
    ("mind_enabled", "consent"),
    [(False, True), (True, False)],
)
def test_legacy_path_and_no_consent_never_reach_the_check(db, mind_enabled, consent):
    identity, owner, conversation = world(db)
    owner.memory_consent = consent
    notes.write(db, owner.id, notes.RULES, RULES, "motivo")
    db.commit()
    provider = llm(rewrite(FIXED))
    run_turn(
        db,
        conversation=conversation,
        identity=identity,
        owner=owner,
        text="Rust ou Python pro worker?",
        provider=provider,
        search=None,
        config=replace(CONFIG, curiosity_enabled=False, mind_enabled=mind_enabled),
    )
    assert not any(is_check(p) for p in provider.prompts) and checks(db) == []
    assert RULES not in provider.prompts[-1][0].content


def test_the_pipeline_sends_rules_through_the_check(db):
    identity, owner, conversation = world(db)
    notes.write(db, owner.id, notes.RULES, RULES, "motivo")
    db.commit()
    outcome = run_turn(
        db,
        conversation=conversation,
        identity=identity,
        owner=owner,
        text="Rust ou Python pro worker?",
        provider=llm(rewrite(FIXED)),
        search=None,
        config=replace(CONFIG, curiosity_enabled=False, mind_enabled=True),
    )
    assert outcome.result.assistant_message.content == FIXED
