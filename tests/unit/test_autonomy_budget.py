"""The shared autonomy ledger: when a step may call the model, and what each call records."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from core.autonomy.budget import (
    AutonomyBudget,
    complete_json,
    has_room,
    parse_json_object,
    usage_today,
)
from infrastructure.database.models import ModelUsage
from integrations.llm.base import ChatMessage, LLMError
from tests.fakes import FakeLLMProvider

NOW = datetime(2026, 5, 1, 12, tzinfo=UTC)
PROMPT = [ChatMessage(role="user", content="{}")]


def _budget(**overrides) -> AutonomyBudget:
    values = {
        "llm_calls_per_day": 3,
        "tokens_per_day": 10_000,
        "max_actions_per_cycle": 5,
        "max_seconds": 60,
        "research_per_day": 10,
        "max_output_tokens": 100,
    }
    values.update(overrides)
    return AutonomyBudget(**values)


def _usage(db, purpose="mind_think", *, tokens=0, cost="0", at=NOW) -> None:
    db.add(
        ModelUsage(
            purpose=purpose,
            provider="p",
            model="m",
            outcome="success",
            input_tokens=tokens,
            output_tokens=0,
            cost_usd=Decimal(cost),
            created_at=at,
        )
    )
    db.commit()


def test_room_counts_only_todays_autonomous_calls(db):
    _usage(db, at=NOW - timedelta(days=1))  # yesterday
    _usage(db, purpose="conversation")  # a reply, not autonomy
    _usage(db)
    _usage(db)
    assert usage_today(db, NOW) == (2, 0)
    assert has_room(db, _budget(), NOW)
    assert not has_room(db, _budget(), NOW, calls=2)  # a two-call round must fit whole


def test_room_closes_on_tokens_or_on_total_daily_spend(db):
    _usage(db, tokens=10_000)
    assert not has_room(db, _budget(), NOW)
    assert has_room(db, _budget(tokens_per_day=20_000), NOW)
    _usage(db, purpose="conversation", cost="1.50")  # conversations share the money cap
    assert not has_room(db, _budget(tokens_per_day=20_000), NOW)


@pytest.mark.parametrize(
    ("text", "expected"),
    [('{"a": 1}', {"a": 1}), ('```json\n{"a": 1}\n```', {"a": 1})],
)
def test_parse_accepts_one_object_optionally_fenced(text, expected):
    assert parse_json_object(text) == expected


@pytest.mark.parametrize("text", ["[1]", 'prefixo {"a": 1}', "```\n{}\n```"])
def test_parse_refuses_anything_else(text):
    with pytest.raises(ValueError):
        parse_json_object(text)


def test_complete_json_records_a_successful_call(db):
    provider = FakeLLMProvider(reply_text='{"ok": true}')
    assert complete_json(db, provider, "mind_think", PROMPT, _budget(), NOW) == {"ok": True}
    usage = db.scalar(select(ModelUsage))
    assert (usage.purpose, usage.outcome) == ("mind_think", "success")
    assert (usage.input_tokens, usage.output_tokens) == (1000, 500)
    assert usage.cost_usd == provider.pricing.cost(1000, 500)


@pytest.mark.parametrize(
    "provider",
    [FakeLLMProvider(reply_text="não é json"), FakeLLMProvider(finish_reason="length")],
    ids=["malformed", "truncated"],
)
def test_complete_json_marks_bad_output(db, provider):
    with pytest.raises(ValueError, match="invalid_model_output"):
        complete_json(db, provider, "mind_think", PROMPT, _budget(), NOW)
    assert db.scalar(select(ModelUsage.outcome)) == "bad_output"


def test_complete_json_records_provider_errors_and_reraises(db):
    with pytest.raises(LLMError):
        complete_json(
            db, FakeLLMProvider(fail_with="rate_limited"), "mind_think", PROMPT, _budget(), NOW
        )
    usage = db.scalar(select(ModelUsage))
    assert (usage.outcome, usage.error_kind) == ("error", "rate_limited")


def test_complete_json_never_calls_without_room(db):
    provider = FakeLLMProvider(reply_text="{}")
    with pytest.raises(ValueError, match="autonomy_budget"):
        complete_json(db, provider, "mind_think", PROMPT, _budget(llm_calls_per_day=0), NOW)
    assert provider.prompts == []
    assert db.scalar(select(ModelUsage)) is None
