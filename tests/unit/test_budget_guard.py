from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.llm import build_llm_provider
from apps.api.settings import Settings
from infrastructure.database.models import SystemFlag
from integrations.llm.base import ChatMessage, LLMError, Pricing
from integrations.llm.budget import (
    DIMENSIONS,
    LEDGER,
    BudgetGuard,
    BudgetLimits,
    FreeEndpointGrant,
    GuardedLLMProvider,
)
from integrations.llm.fallback import FallbackLLMProvider
from tests.fakes import FakeLLMProvider

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)
ENDPOINT = "https://llm.example/v1"
PROMPT = [ChatMessage("user", "oi")]


def grant(**changes):
    fields = dict(
        provider="fake-provider",
        endpoint=ENDPOINT,
        model="fake-model",
        evidence_url="https://llm.example/pricing",
        verified_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
        prices=dict.fromkeys(DIMENSIONS, Decimal(0)),
    )
    fields.update(changes)
    return FreeEndpointGrant(**fields)


def fake(**kwargs):
    return FakeLLMProvider(pricing=Pricing(Decimal(0), Decimal(0)), **kwargs)


def make_guard(factory, *, grants=None, limits=None, clock=None):
    return BudgetGuard(
        factory,
        [grant()] if grants is None else grants,
        limits or BudgetLimits(),
        clock=clock or (lambda: NOW),
    )


@pytest.fixture
def factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def ledger(factory):
    with factory() as db:
        return db.get(SystemFlag, LEDGER).value


@pytest.mark.parametrize(
    "change",
    [
        {"expires_at": NOW},
        {"verified_at": NOW + timedelta(minutes=1)},
        {"endpoint": "https://another.example/v1"},
        {"model": "another-model"},
        {"provider": "another-provider"},
    ],
)
def test_unknown_expired_or_wrong_grant_never_dispatches(factory, change):
    provider = fake()
    guarded = GuardedLLMProvider(provider, ENDPOINT, make_guard(factory, grants=[grant(**change)]))
    with pytest.raises(LLMError) as exc:
        guarded.complete(PROMPT, max_output_tokens=512)
    assert exc.value.kind == "budget_denied" and not provider.prompts
    with factory() as db:
        assert db.get(SystemFlag, LEDGER) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"prices": {"input": 0, "output": 0}},
        {"prices": {**dict.fromkeys(DIMENSIONS, 0), "routing": 1}},
        {"expires_at": NOW + timedelta(days=8)},
        {"endpoint": "https://secret:password@llm.example/v1"},
    ],
)
def test_incomplete_or_paid_evidence_rejected(changes):
    with pytest.raises(ValidationError):
        grant(**changes)


def test_paid_primary_and_no_grant_are_refused_before_database_or_network():
    def unavailable():
        raise AssertionError("must not even access database")

    for provider, grants in ((FakeLLMProvider(), [grant()]), (fake(), [])):
        guarded = GuardedLLMProvider(provider, ENDPOINT, make_guard(unavailable, grants=grants))
        with pytest.raises(LLMError):
            guarded.complete(PROMPT, max_output_tokens=512)
        assert not provider.prompts


def test_paid_spend_cannot_be_enabled_in_this_scope():
    with pytest.raises(ValidationError):
        Settings(llm_max_paid_spend_usd=Decimal("0.01"))


def test_success_retains_reservation_and_persists_quota_across_guard_restart(factory):
    limits = BudgetLimits(calls_per_day=1)
    p = fake()
    GuardedLLMProvider(p, ENDPOINT, make_guard(factory, limits=limits)).complete(
        PROMPT, max_output_tokens=512
    )
    state = ledger(factory)
    assert state["calls"] == 1 and state["input"] >= 1000 and state["output"] == 512
    assert not state["active"]
    other = fake()
    with pytest.raises(LLMError):
        GuardedLLMProvider(other, ENDPOINT, make_guard(factory, limits=limits)).complete(
            PROMPT, max_output_tokens=512
        )
    assert not other.prompts


@pytest.mark.parametrize("kind", ["timeout", "network", "bad_response"])
def test_uncertain_failure_keeps_quota_charged_and_holds_the_slot_only_for_a_while(factory, kind):
    p = fake(fail_with=kind)
    guarded = GuardedLLMProvider(p, ENDPOINT, make_guard(factory))
    with pytest.raises(LLMError) as exc:
        guarded.complete(PROMPT, max_output_tokens=512)
    assert exc.value.kind == kind
    state = ledger(factory)
    assert state["calls"] == 1
    assert list(state["active"].values())[0]["state"] == "unknown"

    def guard_at(moment):
        return make_guard(
            factory,
            clock=lambda: moment,
            grants=[grant(verified_at=moment, expires_at=moment + timedelta(hours=1))],
        )

    with pytest.raises(LLMError):
        guard_at(NOW + timedelta(minutes=14)).reserve(fake(), ENDPOINT, PROMPT, 512)
    assert ledger(factory)["calls"] == 1
    # One lost call must not silence the agent for good; what it consumed is never refunded.
    guard_at(NOW + timedelta(minutes=16)).reserve(fake(), ENDPOINT, PROMPT, 512)
    assert ledger(factory)["calls"] == 2


def test_crash_between_reserve_and_dispatch_blocks_second_dispatch(factory):
    guard = make_guard(factory)
    reservation = guard.reserve(fake(), ENDPOINT, PROMPT, 512)
    p = fake()
    with pytest.raises(LLMError):
        GuardedLLMProvider(p, ENDPOINT, make_guard(factory)).complete(PROMPT, max_output_tokens=512)
    assert reservation in ledger(factory)["active"] and not p.prompts


def test_paid_fallback_and_unknown_endpoint_receive_zero_calls(factory):
    primary, paid, unknown = fake(fail_with="http_503"), FakeLLMProvider(), fake(model="unknown")
    guard = make_guard(factory)
    chain = FallbackLLMProvider(
        [
            GuardedLLMProvider(primary, ENDPOINT, guard),
            GuardedLLMProvider(paid, ENDPOINT, guard),
            GuardedLLMProvider(unknown, ENDPOINT, guard),
        ]
    )
    with pytest.raises(LLMError):
        chain.complete(PROMPT, max_output_tokens=512)
    assert len(primary.prompts) == 1 and not paid.prompts and not unknown.prompts
    assert ledger(factory)["calls"] == 1


def test_eligible_fallback_reserves_again_after_known_failure(factory):
    primary, backup = fake(fail_with="http_503"), fake(model="backup")
    guard = make_guard(factory, grants=[grant(), grant(model="backup")])
    chain = FallbackLLMProvider(
        [GuardedLLMProvider(primary, ENDPOINT, guard), GuardedLLMProvider(backup, ENDPOINT, guard)]
    )
    assert chain.complete(PROMPT, max_output_tokens=512).model == "backup"
    assert ledger(factory)["calls"] == 2


@pytest.mark.parametrize(
    "limits,output",
    [
        (BudgetLimits(input_tokens_per_call=1), 512),
        (BudgetLimits(input_tokens_per_day=1), 512),
        (BudgetLimits(output_tokens_per_day=500), 512),
        (BudgetLimits(output_tokens_per_call=500), 512),
        (BudgetLimits(), 0),
    ],
)
def test_payload_and_token_limits_are_checked_before_io(factory, limits, output):
    p = fake()
    with pytest.raises(LLMError):
        GuardedLLMProvider(p, ENDPOINT, make_guard(factory, limits=limits)).complete(
            PROMPT, max_output_tokens=output
        )
    assert not p.prompts


def test_circuit_breaker_survives_reconstruction(factory):
    clock = [NOW]
    p = fake(fail_with="http_503")
    for _ in range(3):
        with pytest.raises(LLMError):
            GuardedLLMProvider(p, ENDPOINT, make_guard(factory, clock=lambda: clock[0])).complete(
                PROMPT, max_output_tokens=512
            )
    with pytest.raises(LLMError, match="cooling down"):
        GuardedLLMProvider(p, ENDPOINT, make_guard(factory)).complete(PROMPT, max_output_tokens=512)
    assert len(p.prompts) == 3
    clock[0] += timedelta(minutes=16)
    p.fail_with = None
    GuardedLLMProvider(p, ENDPOINT, make_guard(factory, clock=lambda: clock[0])).complete(
        PROMPT, max_output_tokens=512
    )
    assert len(p.prompts) == 4


def test_only_one_probe_is_admitted_after_cooldown(factory):
    clock = [NOW]
    limits = BudgetLimits(concurrency=2, failure_threshold=1)
    guard = make_guard(factory, limits=limits, clock=lambda: clock[0])
    reservation = guard.reserve(fake(), ENDPOINT, PROMPT, 512)
    guard.finish(reservation, None, "http_503")
    clock[0] += timedelta(minutes=16)
    probe = guard.reserve(fake(), ENDPOINT, PROMPT, 512)
    with pytest.raises(LLMError, match="probe"):
        guard.reserve(fake(), ENDPOINT, PROMPT, 512)
    guard.finish(probe, fake().complete(PROMPT, max_output_tokens=512), None)
    assert guard.reserve(fake(), ENDPOINT, PROMPT, 512)


def test_reported_token_overrun_is_rejected_and_freezes_next_admission(factory):
    p = fake()
    guard = make_guard(factory)
    with pytest.raises(LLMError, match="violated"):
        GuardedLLMProvider(p, ENDPOINT, guard).complete(PROMPT, max_output_tokens=10)
    assert ledger(factory)["frozen"]
    with pytest.raises(LLMError, match="frozen"):
        GuardedLLMProvider(p, ENDPOINT, guard).complete(PROMPT, max_output_tokens=512)
    assert len(p.prompts) == 1


def test_failure_to_reconcile_keeps_reservation_charged(factory, monkeypatch):
    guard = make_guard(factory)
    p = fake()

    def unavailable(*args):
        raise RuntimeError("ledger offline after provider returned")

    monkeypatch.setattr(guard, "finish", unavailable)
    with pytest.raises(LLMError, match="reconciliation failed"):
        GuardedLLMProvider(p, ENDPOINT, guard).complete(PROMPT, max_output_tokens=512)
    state = ledger(factory)
    assert state["calls"] == 1 and len(state["active"]) == 1
    with pytest.raises(LLMError):
        GuardedLLMProvider(p, ENDPOINT, make_guard(factory)).complete(PROMPT, max_output_tokens=512)
    assert len(p.prompts) == 1


def test_database_failure_is_closed_before_provider_io():
    def broken():
        raise RuntimeError("database unavailable")

    p = fake()
    with pytest.raises(LLMError, match="ledger unavailable"):
        GuardedLLMProvider(p, ENDPOINT, make_guard(broken)).complete(PROMPT, max_output_tokens=512)
    assert not p.prompts


def test_provider_contract_violation_freezes_future_calls(factory):
    class Mispriced:
        name, model, pricing = "fake-provider", "fake-model", Pricing(Decimal(0), Decimal(0))

        def complete(self, messages, *, max_output_tokens):
            return FakeLLMProvider().complete(messages, max_output_tokens=max_output_tokens)

    guard = make_guard(factory)
    with pytest.raises(LLMError, match="violated"):
        GuardedLLMProvider(Mispriced(), ENDPOINT, guard).complete(PROMPT, max_output_tokens=512)
    assert ledger(factory)["frozen"]
    p = fake()
    with pytest.raises(LLMError, match="frozen"):
        GuardedLLMProvider(p, ENDPOINT, guard).complete(PROMPT, max_output_tokens=512)
    assert not p.prompts


def test_parallel_admissions_use_shared_persistent_quota(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'budget.sqlite'}", connect_args={"timeout": 20})
    SystemFlag.__table__.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    limits = BudgetLimits(calls_per_day=5, concurrency=32)

    def attempt(_):
        try:
            make_guard(factory, limits=limits).reserve(fake(), ENDPOINT, PROMPT, 512)
            return True
        except LLMError:
            return False

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(attempt, range(100)))
        state = ledger(factory)
        assert sum(accepted) == state["calls"] == len(state["active"]) == 5
        assert state["input"] <= limits.input_tokens_per_day
        assert state["output"] <= limits.output_tokens_per_day
    finally:
        engine.dispose()


def test_factory_wraps_every_endpoint_and_disables_hidden_http_retries(factory, monkeypatch):
    from integrations.llm import openai_compatible

    seen = []

    def post(client, path, **kwargs):
        seen.append(path)
        return httpx.Response(503, request=httpx.Request("POST", ENDPOINT + path))

    monkeypatch.setattr(openai_compatible.httpx.Client, "post", post)
    fields = dict(
        llm_provider_name="fake-provider",
        llm_base_url=ENDPOINT,
        llm_api_key="test-key",
        llm_model="fake-model",
        llm_price_input_per_mtok=0,
        llm_price_output_per_mtok=0,
        llm_fallback_provider_name="fake-provider",
        llm_fallback_base_url=ENDPOINT,
        llm_fallback_api_key="test-key",
        llm_fallback_model="backup",
        llm_fallback_price_input_per_mtok=1,
        llm_fallback_price_output_per_mtok=1,
    )
    provider = build_llm_provider(Settings(**fields), budget_guard=make_guard(factory))
    with pytest.raises(LLMError):
        provider.complete(PROMPT, max_output_tokens=512)
    assert seen == ["/chat/completions"]
    assert ledger(factory)["calls"] == 1


def test_longest_allowed_conversation_fits_the_per_call_limit(factory):
    settings = Settings(_env_file=None)
    system = "s" * 12_000  # system prompt with memories, mind and per-turn context
    history = "á" * settings.llm_context_char_budget  # accents take two bytes
    prompt = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=history)]
    limits = BudgetLimits(
        input_tokens_per_call=settings.llm_budget_input_tokens_per_call,
        input_tokens_per_day=1_000_000,
    )
    assert make_guard(factory, limits=limits).reserve(fake(), ENDPOINT, prompt, 512)


def test_second_fallback_joins_the_chain_only_when_complete(factory):
    def fields(**extra):
        base = {
            f"llm_{prefix}{name}": value
            for prefix in ("", "fallback_")
            for name, value in {
                "provider_name": f"p{prefix}",
                "base_url": "https://example.com/v1",
                "api_key": "x",
                "model": "m",
                "price_input_per_mtok": Decimal(0),
                "price_output_per_mtok": Decimal(0),
            }.items()
        }
        return Settings(_env_file=None, **base, **extra)

    chain = build_llm_provider(fields(), budget_guard=make_guard(factory))
    assert len(chain._providers) == 2
    partial = build_llm_provider(
        fields(llm_fallback2_provider_name="groq"), budget_guard=make_guard(factory)
    )
    assert len(partial._providers) == 2
    full = build_llm_provider(
        fields(
            llm_fallback2_provider_name="groq",
            llm_fallback2_base_url="https://api.groq.com/openai/v1",
            llm_fallback2_api_key="x",
            llm_fallback2_model="m",
            llm_fallback2_price_input_per_mtok=Decimal(0),
            llm_fallback2_price_output_per_mtok=Decimal(0),
        ),
        budget_guard=make_guard(factory),
    )
    assert len(full._providers) == 3


@pytest.mark.parametrize("kind", ["timeout", "network"])
def test_timed_out_primary_does_not_lock_out_the_fallback(factory, kind):
    primary, backup = fake(fail_with=kind), fake(model="backup")
    guard = make_guard(factory, grants=[grant(), grant(model="backup")])
    chain = FallbackLLMProvider(
        [GuardedLLMProvider(primary, ENDPOINT, guard), GuardedLLMProvider(backup, ENDPOINT, guard)]
    )
    assert chain.complete(PROMPT, max_output_tokens=512).model == "backup"
    state = ledger(factory)
    # The uncertain primary call stays charged and keeps holding its own slot.
    assert state["calls"] == 2
    assert [item["state"] for item in state["active"].values()] == ["unknown"]
    with pytest.raises(LLMError, match="quota"):
        guard.reserve(fake(), ENDPOINT, PROMPT, 512)


def test_in_flight_calls_are_still_capped_across_providers(factory):
    guard = make_guard(factory, grants=[grant(), grant(model="backup")])
    guard.reserve(fake(), ENDPOINT, PROMPT, 512)
    with pytest.raises(LLMError, match="quota"):
        guard.reserve(fake(model="backup"), ENDPOINT, PROMPT, 512)


def test_every_fallback_slot_receives_its_fast_extra_body(factory):
    base = {
        f"llm_{prefix}{name}": value
        for prefix in ("", "fallback_", "fallback2_")
        for name, value in {
            "provider_name": f"p{prefix}",
            "base_url": "https://example.com/v1",
            "api_key": "x",
            "model": "m",
            "price_input_per_mtok": Decimal(0),
            "price_output_per_mtok": Decimal(0),
        }.items()
    }
    settings = Settings(
        _env_file=None,
        **base,
        llm_fast_extra_body={"a": 1},
        llm_fallback_fast_extra_body={"b": 2},
        llm_fallback2_fast_extra_body={"c": 3},
    )
    fast = build_llm_provider(settings, budget_guard=make_guard(factory), fast=True)
    assert [p._provider._extra_body for p in fast._providers] == [{"a": 1}, {"b": 2}, {"c": 3}]
    slow = build_llm_provider(settings, budget_guard=make_guard(factory))
    assert [p._provider._extra_body for p in slow._providers] == [{}, {}, {}]
