"""The order of providers per task (ADR-0022): a rule in code, and the pause shared in the bank."""

import json
import time
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.orm import sessionmaker

from apps.api.llm import build_llm_provider, configured_kinds
from apps.api.settings import Settings
from core import llm_routing
from core.autonomy.budget import AutonomyBudget, complete_json
from infrastructure.database.models import AuditLog, SystemFlag
from integrations.llm.base import ChatMessage, LLMError, Pricing, current_purpose, for_purpose
from integrations.llm.fallback import FallbackLLMProvider
from integrations.llm.openai_compatible import OpenAICompatibleProvider
from integrations.llm.pause import FLAG, PauseBoard, pause_seconds
from tests.fakes import FakeLLMProvider

PROMPT = [ChatMessage("user", "oi")]
FREE = Pricing(Decimal(0), Decimal(0))
CONFIGURED: list[llm_routing.Kind] = ["claude", "openai", "gemini"]


def _fakes() -> list[FakeLLMProvider]:
    return [
        FakeLLMProvider(name=name, model=f"{name}-m", reply_text=f"do {name}", pricing=FREE)
        for name in ("claude", "openai", "gemini")
    ]


def _routed(providers, mode: llm_routing.Mode, **kwargs) -> FallbackLLMProvider:
    kinds = [llm_routing.provider_kind(p.name, None) for p in providers]
    return FallbackLLMProvider(
        providers, order=lambda: llm_routing.order(kinds, current_purpose(), mode), **kwargs
    )


# --- the rule ------------------------------------------------------------------------------


def test_fixed_mode_keeps_the_configured_order() -> None:
    assert llm_routing.order(["gemini", "openai", "claude"], "study_review", "fixa") == [0, 1, 2]


@pytest.mark.parametrize(
    ("purpose", "expected"),
    [
        ("chat_reply", ["claude", "openai", "gemini"]),
        ("memory_curation", ["claude", "openai", "gemini"]),
        ("curiosity_assessment", ["claude", "openai", "gemini"]),  # carries memories
        ("study_plan", ["claude", "openai", "gemini"]),  # carries the profile
        (None, ["claude", "openai", "gemini"]),  # a call that does not say is personal
        ("study_review", ["gemini", "claude", "openai"]),  # only public text
    ],
)
def test_per_task_order_whatever_the_configured_order(purpose, expected) -> None:
    configured: list[llm_routing.Kind] = ["gemini", "openai", "claude"]
    got = llm_routing.order(configured, purpose, "por_tarefa")
    assert [configured[i] for i in got] == expected


def test_an_unknown_provider_keeps_its_place_after_the_known_ones() -> None:
    configured: list[llm_routing.Kind] = ["outro", "gemini", "claude"]
    assert llm_routing.order(configured, "chat_reply", "por_tarefa") == [2, 1, 0]


@pytest.mark.parametrize(
    ("name", "url", "kind"),
    [
        ("anthropic", "https://api.anthropic.com", "claude"),
        ("x", "https://api.openai.com/v1", "openai"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini"),
        ("groq", "https://api.groq.com/openai/v1", "outro"),
    ],
)
def test_providers_are_recognized_by_name_or_address(name, url, kind) -> None:
    assert llm_routing.provider_kind(name, url) == kind


def test_mode_defaults_to_fixed_and_switching_is_audited(db) -> None:
    assert llm_routing.get_mode(db) == "fixa"
    llm_routing.set_mode(db, "por_tarefa", actor_user_id=None, via="ajustes")
    db.commit()
    assert llm_routing.get_mode(db) == "por_tarefa"
    event = db.query(AuditLog).filter_by(action="llm.routing").one()
    assert event.details == {"mode": "por_tarefa", "via": "ajustes"}
    with pytest.raises(ValueError):
        llm_routing.set_mode(db, "auto", actor_user_id=None, via="ajustes")  # type: ignore[arg-type]


# --- the chain -----------------------------------------------------------------------------


def test_public_task_goes_to_gemini_first_and_personal_to_claude() -> None:
    claude, openai, gemini = _fakes()
    provider = _routed([claude, openai, gemini], "por_tarefa")
    with for_purpose("study_review"):
        assert provider.complete(PROMPT, max_output_tokens=5).text == "do gemini"
    assert provider.complete(PROMPT, max_output_tokens=5).text == "do claude"
    assert (len(claude.prompts), len(openai.prompts), len(gemini.prompts)) == (1, 0, 1)


def test_per_task_still_falls_back_on_failure() -> None:
    claude, openai, gemini = _fakes()
    gemini.fail_with = "http_429"
    provider = _routed([claude, openai, gemini], "por_tarefa")
    with for_purpose("study_review"):
        assert provider.complete(PROMPT, max_output_tokens=5).text == "do claude"


def test_paid_provider_without_caps_is_still_refused_in_the_new_order() -> None:
    claude, openai, gemini = _fakes()
    gemini.fail_with = "quota_exhausted"
    claude.pricing = Pricing(Decimal(1), Decimal(5))  # no admits_paid: no spending cap
    provider = _routed([claude, openai, gemini], "por_tarefa")
    with for_purpose("study_review"):
        assert provider.complete(PROMPT, max_output_tokens=5).text == "do openai"
    assert claude.prompts == []


def test_a_broken_order_falls_back_to_the_configured_one() -> None:
    claude, openai, gemini = _fakes()

    def broken() -> list[int]:
        raise RuntimeError("db down")

    provider = FallbackLLMProvider([gemini, claude], order=broken)
    assert provider.complete(PROMPT, max_output_tokens=5).text == "do gemini"
    provider = FallbackLLMProvider([gemini, claude], order=lambda: [1, 1])
    assert provider.complete(PROMPT, max_output_tokens=5).text == "do gemini"


def test_complete_json_tells_the_chain_what_the_call_is_for(db) -> None:
    claude, openai, gemini = _fakes()
    gemini.reply_text = '{"ok": true}'
    provider = _routed([claude, openai, gemini], "por_tarefa")
    budget = AutonomyBudget(
        llm_calls_per_day=5,
        tokens_per_day=100_000,
        max_actions_per_cycle=1,
        max_seconds=10,
        research_per_day=1,
        max_output_tokens=50,
    )
    now = datetime.now(UTC)
    assert complete_json(db, provider, "study_review", PROMPT, budget, now) == {"ok": True}
    assert claude.prompts == [] and len(gemini.prompts) == 1


def test_factory_reorders_by_the_owner_switch(engine) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        llm_provider_name="anthropic",
        llm_base_url="https://api.anthropic.com",
        llm_api_key=SecretStr("k1"),
        llm_model="claude-haiku-5-5",
        llm_price_input_per_mtok=Decimal("0.1"),
        llm_price_output_per_mtok=Decimal("0.5"),
        llm_fallback_provider_name="gemini",
        llm_fallback_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        llm_fallback_api_key=SecretStr("k2"),
        llm_fallback_model="gemini-flash",
        llm_fallback_price_input_per_mtok=Decimal(0),
        llm_fallback_price_output_per_mtok=Decimal(0),
    )
    assert configured_kinds(settings) == ["claude", "gemini"]
    provider = build_llm_provider(settings, session_factory=factory)
    assert isinstance(provider, FallbackLLMProvider)
    with for_purpose("study_review"):
        assert provider.order() == [0, 1]  # fixed until the owner switches
        with factory() as session:
            llm_routing.set_mode(session, "por_tarefa", actor_user_id=None, via="teste")
            session.commit()
        assert provider.order() == [1, 0]
    assert provider.order() == [0, 1]


# --- the pause in the bank -----------------------------------------------------------------


def test_pause_lasts_until_the_announced_reset_within_bounds() -> None:
    assert pause_seconds(None, 1000.0) == 15 * 60
    assert pause_seconds(1000.0 + 3600, 1000.0) == 3600
    assert pause_seconds(1000.0 + 5, 1000.0) == 60
    assert pause_seconds(1000.0 + 10 * 86400, 1000.0) == 86400


def test_quota_pause_is_shared_between_processes(engine) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    claude, openai, gemini = _fakes()
    reset = time.time() + 7200
    gemini.complete = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[method-assign]
        LLMError("quota_exhausted", "daily cap", retry_at=reset)
    )
    api = FallbackLLMProvider([gemini, claude], pauses=PauseBoard(factory))
    assert api.complete(PROMPT, max_output_tokens=5).text == "do claude"

    # The worker never saw the failure, but skips Gemini until the reset it announced.
    fresh_gemini = _fakes()[2]
    worker = FallbackLLMProvider([fresh_gemini, openai], pauses=PauseBoard(factory))
    assert worker.complete(PROMPT, max_output_tokens=5).text == "do openai"
    assert fresh_gemini.prompts == []
    with factory() as session:
        until = session.get(SystemFlag, FLAG).value["gemini|gemini-m"]
    assert until == pytest.approx(reset, abs=1)

    later = PauseBoard(factory, clock=lambda: reset + 1)
    assert later.snapshot() == {}


def test_an_unreadable_board_never_silences_the_chain() -> None:
    def broken():
        raise RuntimeError("db down")

    claude, _, _ = _fakes()
    provider = FallbackLLMProvider([claude], pauses=PauseBoard(broken))
    assert provider.complete(PROMPT, max_output_tokens=5).text == "do claude"


# --- what the providers say about their quota ----------------------------------------------


def _provider(status: int, body: object, headers: dict | None = None) -> OpenAICompatibleProvider:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, content=json.dumps(body), headers=headers or {})
    )
    return OpenAICompatibleProvider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="k",
        model="gemini-flash",
        pricing=FREE,
        max_retries=0,
        transport=transport,
    )


def _gemini_error(details: list[dict]) -> list[dict]:
    return [{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": details}}]


def test_gemini_daily_quota_pauses_until_midnight_pacific() -> None:
    body = _gemini_error(
        [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
            },
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "20s"},
        ]
    )
    with pytest.raises(LLMError) as exc:
        _provider(429, body).complete(PROMPT, max_output_tokens=5)
    assert exc.value.kind == "quota_exhausted"
    assert exc.value.retry_at is not None
    seconds = exc.value.retry_at - time.time()
    assert 0 < seconds <= 86400
    reset = datetime.fromtimestamp(exc.value.retry_at, UTC)
    assert reset.minute == 0 and reset.hour in (7, 8)  # midnight in Los Angeles


def test_gemini_per_minute_limit_stays_a_plain_429() -> None:
    body = _gemini_error([{"retryDelay": "12s"}])
    with pytest.raises(LLMError) as exc:
        _provider(429, body).complete(PROMPT, max_output_tokens=5)
    assert exc.value.kind == "http_429"


def test_gemini_long_retry_delay_is_a_quota() -> None:
    body = _gemini_error([{"retryDelay": "3600s"}])
    with pytest.raises(LLMError) as exc:
        _provider(429, body).complete(PROMPT, max_output_tokens=5)
    assert exc.value.kind == "quota_exhausted"
    assert exc.value.retry_at == pytest.approx(time.time() + 3600, abs=5)


def test_openai_without_credit_is_a_quota() -> None:
    body = {"error": {"code": "insufficient_quota", "type": "insufficient_quota"}}
    with pytest.raises(LLMError) as exc:
        _provider(429, body).complete(PROMPT, max_output_tokens=5)
    assert (exc.value.kind, exc.value.retry_at) == ("quota_exhausted", None)


def test_ratelimit_reset_header_becomes_the_pause() -> None:
    reset = time.time() + 600
    headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(reset * 1000))}
    with pytest.raises(LLMError) as exc:
        _provider(429, {"error": {"code": 429}}, headers).complete(PROMPT, max_output_tokens=5)
    assert exc.value.kind == "quota_exhausted"
    assert exc.value.retry_at == pytest.approx(reset, abs=1)


def test_the_manifest_says_the_code_chooses() -> None:
    from core.identity.capabilities import Capabilities

    assert not any("regra no código" in a for a in Capabilities().actions())
    line = next(a for a in Capabilities(provider_by_task=True).actions() if "regra no" in a)
    assert "não é você nem outro modelo que escolhe" in line
