from decimal import Decimal

import pytest
from pydantic import SecretStr

from apps.api.llm import build_llm_provider, missing_fallback_settings
from apps.api.settings import Settings
from integrations.llm import fallback as fallback_module
from integrations.llm.base import ChatMessage, LLMError, Pricing
from integrations.llm.fallback import FallbackLLMProvider
from tests.fakes import FakeLLMProvider

PROMPT = [ChatMessage("user", "oi")]


def _primary(**kwargs: object) -> FakeLLMProvider:
    return FakeLLMProvider(
        name="openrouter",
        reply_text="do primário",
        pricing=Pricing(Decimal(0), Decimal(0)),
        **kwargs,
    )


def _backup() -> FakeLLMProvider:
    return FakeLLMProvider(
        name="nvidia",
        model="nemotron-nvidia",
        reply_text="da reserva",
        pricing=Pricing(Decimal(0), Decimal(0)),
    )


def test_uses_primary_when_it_works() -> None:
    backup = _backup()
    provider = FallbackLLMProvider([_primary(), backup])
    assert provider.complete(PROMPT, max_output_tokens=5).text == "do primário"
    assert backup.prompts == []


@pytest.mark.parametrize(
    "kind", ["quota_exhausted", "http_429", "http_503", "timeout", "network", "bad_response"]
)
def test_falls_back_on_transient_or_quota_errors(kind: str) -> None:
    provider = FallbackLLMProvider([_primary(fail_with=kind), _backup()])
    response = provider.complete(PROMPT, max_output_tokens=5)
    assert (response.text, response.provider) == ("da reserva", "nvidia")
    assert response.cost_usd == 0


def test_timeout_never_dispatches_paid_backup() -> None:
    backup = _backup()
    backup.pricing = Pricing(Decimal(1), Decimal(2))
    provider = FallbackLLMProvider([_primary(fail_with="timeout"), backup])
    with pytest.raises(LLMError, match="paid provider") as exc:
        provider.complete(PROMPT, max_output_tokens=5)
    assert exc.value.kind == "budget_denied"
    assert not backup.prompts


@pytest.mark.parametrize("kind", ["http_401", "http_400", "http_404"])
def test_configuration_errors_are_not_masked(kind: str) -> None:
    backup = _backup()
    provider = FallbackLLMProvider([_primary(fail_with=kind), backup])
    with pytest.raises(LLMError) as exc:
        provider.complete(PROMPT, max_output_tokens=5)
    assert exc.value.kind == kind
    assert backup.prompts == []


def test_raises_last_error_when_everyone_fails() -> None:
    backup = _backup()
    backup.fail_with = "http_503"
    provider = FallbackLLMProvider([_primary(fail_with="quota_exhausted"), backup])
    with pytest.raises(LLMError) as exc:
        provider.complete(PROMPT, max_output_tokens=5)
    assert exc.value.kind == "http_503"


def test_exhausted_provider_is_skipped_during_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(fallback_module.time, "monotonic", lambda: now[0])
    primary = _primary(fail_with="quota_exhausted")
    provider = FallbackLLMProvider([primary, _backup()])

    provider.complete(PROMPT, max_output_tokens=5)
    provider.complete(PROMPT, max_output_tokens=5)
    assert len(primary.prompts) == 1  # second call went straight to the backup

    now[0] += fallback_module.QUOTA_COOLDOWN_SECONDS + 1
    provider.complete(PROMPT, max_output_tokens=5)
    assert len(primary.prompts) == 2  # retried after the cooldown


PRIMARY_SETTINGS = {
    "llm_provider_name": "openrouter",
    "llm_base_url": "https://openrouter.ai/api/v1",
    "llm_api_key": SecretStr("k1"),
    "llm_model": "m1",
    "llm_price_input_per_mtok": Decimal(0),
    "llm_price_output_per_mtok": Decimal(0),
}
FALLBACK_SETTINGS = {
    "llm_fallback_provider_name": "nvidia",
    "llm_fallback_base_url": "https://integrate.api.nvidia.com/v1",
    "llm_fallback_api_key": SecretStr("k2"),
    "llm_fallback_model": "m2",
    "llm_fallback_price_input_per_mtok": Decimal(0),
    "llm_fallback_price_output_per_mtok": Decimal(0),
}


def test_factory_chains_a_complete_fallback() -> None:
    provider = build_llm_provider(Settings(**PRIMARY_SETTINGS, **FALLBACK_SETTINGS))
    assert isinstance(provider, FallbackLLMProvider)
    assert provider.name == "openrouter+nvidia"


def test_factory_ignores_partial_fallback() -> None:
    partial = {**FALLBACK_SETTINGS, "llm_fallback_api_key": None}
    settings = Settings(**PRIMARY_SETTINGS, **partial)
    provider = build_llm_provider(settings)
    assert provider is not None and not isinstance(provider, FallbackLLMProvider)
    assert missing_fallback_settings(settings) == ["VISION_LLM_FALLBACK_API_KEY"]


def test_factory_without_fallback_returns_primary() -> None:
    provider = build_llm_provider(Settings(**PRIMARY_SETTINGS))
    assert provider is not None and not isinstance(provider, FallbackLLMProvider)
