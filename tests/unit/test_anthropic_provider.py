"""Claude provider and the paid spending caps: a priced call runs only inside the caps, and the
ledger records what the call really cost."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api.llm import build_llm_provider, is_anthropic
from apps.api.settings import Settings
from infrastructure.database.base import Base
from integrations.llm.anthropic_provider import AnthropicProvider, to_messages_api
from integrations.llm.base import ChatMessage, LLMError, Pricing, drafting
from integrations.llm.budget import BudgetGuard, BudgetLimits, GuardedLLMProvider

HAIKU = Pricing(input_per_mtok=Decimal("0.10"), output_per_mtok=Decimal("0.50"))


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.calls, self.response, self.error = [], response, error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeStream:
    def __init__(self, pieces, final):
        self.text_stream, self._final = iter(pieces), final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._final


class StreamingMessages(FakeMessages):
    def __init__(self, pieces, response):
        super().__init__(response)
        self.pieces, self.streamed = pieces, []

    def stream(self, **kwargs):
        self.streamed.append(kwargs)
        return FakeStream(self.pieces, self.response)


def reply(text="oi", stop="end_turn", input_tokens=1000, output_tokens=200):
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop,
        model="claude-haiku-5-5",
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


def provider(messages, extra=None):
    return AnthropicProvider(
        name="anthropic",
        api_key="sk-ant-test",
        model="claude-haiku-5-5",
        pricing=HAIKU,
        extra_body=extra,
        client=SimpleNamespace(messages=messages),
    )


def test_system_prompts_go_top_level_and_an_agent_opening_gets_a_user_turn():
    system, turns = to_messages_api(
        [
            ChatMessage("system", "regras"),
            ChatMessage("assistant", "Pensei em você."),
            ChatMessage("system", "contexto"),
            ChatMessage("user", "oi"),
        ]
    )
    assert system == "regras\n\ncontexto"
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]


def test_a_reply_is_text_only_with_tokens_and_cost():
    messages = FakeMessages(reply())
    response = provider(
        messages, {"thinking": {"type": "disabled"}, "reasoning": {"x": 1}}
    ).complete([ChatMessage("system", "s"), ChatMessage("user", "u")], max_output_tokens=512)
    assert response.text == "oi" and response.finish_reason == "end_turn"
    assert response.cost_usd == Decimal("0.0002")  # 1000 * 0.10/1M + 200 * 0.50/1M
    sent = messages.calls[0]
    assert sent["system"] == "s" and sent["max_tokens"] == 512
    assert sent["thinking"] == {"type": "disabled"} and "reasoning" not in sent


def test_truncation_refusal_and_errors_map_to_the_shared_kinds():
    cut = provider(FakeMessages(reply(stop="max_tokens"))).complete(
        [ChatMessage("user", "u")], max_output_tokens=10
    )
    assert cut.finish_reason == "length"
    with pytest.raises(LLMError) as refused:
        provider(FakeMessages(reply(stop="refusal"))).complete(
            [ChatMessage("user", "u")], max_output_tokens=10
        )
    assert refused.value.kind == "refusal"
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    limited = anthropic.RateLimitError(
        "slow down", response=httpx.Response(429, request=request), body=None
    )
    with pytest.raises(LLMError) as rate:
        provider(FakeMessages(error=limited)).complete(
            [ChatMessage("user", "u")], max_output_tokens=10
        )
    assert rate.value.kind == "http_429"
    with pytest.raises(LLMError) as timeout:
        provider(FakeMessages(error=anthropic.APITimeoutError(request=request))).complete(
            [ChatMessage("user", "u")], max_output_tokens=10
        )
    assert timeout.value.kind == "timeout"


def guard(daily="0.50", monthly="10"):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    clock = lambda: datetime(2026, 11, 12, 15, 0, tzinfo=UTC)  # noqa: E731
    limits = BudgetLimits(
        calls_per_day=1000,
        calls_per_hour=1000,
        input_tokens_per_day=10**9,
        output_tokens_per_day=10**9,
        concurrency=4,
    )
    return BudgetGuard(
        factory,
        [],
        limits,
        clock=clock,
        paid_daily_usd=Decimal(daily),
        paid_monthly_usd=Decimal(monthly),
    ), factory


def ledger(factory):
    from infrastructure.database.models import SystemFlag

    with factory() as db:
        return db.get(SystemFlag, "llm_budget_v1").value


def test_a_paid_provider_is_refused_without_caps():
    budget, _ = guard("0", "0")
    guarded = GuardedLLMProvider(
        provider(FakeMessages(reply())), "https://api.anthropic.com", budget
    )
    with pytest.raises(LLMError, match="paid"):
        guarded.complete([ChatMessage("user", "u")], max_output_tokens=100)


def test_the_ledger_charges_the_real_cost_and_stops_at_the_daily_cap():
    budget, factory = guard(daily="0.001")
    guarded = GuardedLLMProvider(
        provider(FakeMessages(reply())), "https://api.anthropic.com", budget
    )
    guarded.complete([ChatMessage("user", "u")], max_output_tokens=300)
    state = ledger(factory)
    assert Decimal(state["usd_day"]) == Decimal("0.0002") == Decimal(state["usd_month"])
    # The worst case of a big call (4096 output tokens) no longer fits under $0.001 today.
    with pytest.raises(LLMError, match="paid spending cap"):
        guarded.complete([ChatMessage("user", "u" * 3000)], max_output_tokens=4096)


def test_a_provider_reporting_more_than_it_reserved_freezes_the_ledger():
    budget, factory = guard()
    greedy = provider(FakeMessages(reply(output_tokens=5000)))
    guarded = GuardedLLMProvider(greedy, "https://api.anthropic.com", budget)
    with pytest.raises(LLMError):
        guarded.complete([ChatMessage("user", "u")], max_output_tokens=100)
    assert ledger(factory)["frozen"]


def test_the_builder_picks_claude_for_anthropic_settings():
    assert is_anthropic("anthropic", "https://api.anthropic.com") and not is_anthropic(
        "openrouter", "https://openrouter.ai/api/v1"
    )
    settings = Settings(
        llm_provider_name="anthropic",
        llm_base_url="https://api.anthropic.com",
        llm_api_key="sk-ant-test",
        llm_model="claude-haiku-5-5",
        llm_price_input_per_mtok=Decimal("0.10"),
        llm_price_output_per_mtok=Decimal("0.50"),
        llm_paid_daily_usd=Decimal("0.50"),
        llm_paid_monthly_usd=Decimal("10"),
    )
    built = build_llm_provider(settings, budget_guard=guard()[0], fast=True)
    assert isinstance(built._provider, AnthropicProvider) and built.admits_paid


def test_with_a_draft_wanted_the_reply_streams_and_ends_the_same():
    messages = StreamingMessages(["Cam", "berra."], reply("Camberra."))
    seen: list[str] = []
    with drafting(seen.append):
        response = provider(messages).complete(
            [ChatMessage("user", "capital?")], max_output_tokens=50
        )
    assert seen == ["Cam", "Camberra."]
    assert (response.text, response.input_tokens, response.output_tokens) == (
        "Camberra.",
        1000,
        200,
    )
    assert messages.calls == [] and messages.streamed[0]["max_tokens"] == 50


def test_without_a_draft_wanted_it_does_not_stream():
    messages = StreamingMessages(["x"], reply("Camberra."))
    response = provider(messages).complete([ChatMessage("user", "capital?")], max_output_tokens=50)
    assert response.text == "Camberra." and messages.streamed == [] and len(messages.calls) == 1


def test_a_broken_draft_sink_never_costs_the_reply():
    def boom(_text):
        raise RuntimeError("sink")

    messages = StreamingMessages(["Cam", "berra."], reply("Camberra."))
    with drafting(boom):
        response = provider(messages).complete(
            [ChatMessage("user", "capital?")], max_output_tokens=50
        )
    assert response.text == "Camberra."
