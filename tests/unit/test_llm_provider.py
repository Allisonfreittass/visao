import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from apps.api.llm import build_llm_provider, missing_llm_settings
from apps.api.settings import Settings
from integrations.llm import openai_compatible
from integrations.llm.base import ChatMessage, LLMError, Pricing
from integrations.llm.openai_compatible import OpenAICompatibleProvider

PRICING = Pricing(input_per_mtok=Decimal("0.5"), output_per_mtok=Decimal("3"))
OK_BODY = {
    "model": "qwen-test",
    "choices": [{"message": {"content": "olá"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_compatible.time, "sleep", lambda _: None)


def _provider(handler, max_retries: int = 2) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="test",
        base_url="https://llm.example/v1/",
        api_key="chave-de-teste",
        model="qwen-test",
        pricing=PRICING,
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


def test_complete_parses_response_and_sends_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=OK_BODY)

    response = _provider(handler).complete([ChatMessage("user", "oi")], max_output_tokens=50)

    assert response.text == "olá"
    assert (response.input_tokens, response.output_tokens) == (12, 3)
    request = seen[0]
    assert str(request.url) == "https://llm.example/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer chave-de-teste"
    payload = json.loads(request.content)
    assert payload["model"] == "qwen-test"
    assert payload["max_tokens"] == 50
    assert payload["messages"] == [{"role": "user", "content": "oi"}]


def test_retries_transient_errors() -> None:
    statuses = iter([503, 429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        return httpx.Response(status, json=OK_BODY if status == 200 else {})

    assert (
        _provider(handler).complete([ChatMessage("user", "oi")], max_output_tokens=5).text == "olá"
    )


def test_gives_up_after_max_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    with pytest.raises(LLMError) as exc:
        _provider(handler, max_retries=2).complete([ChatMessage("user", "oi")], max_output_tokens=5)
    assert exc.value.kind == "http_503"
    assert calls == 3


def test_client_error_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": "invalid key"})

    with pytest.raises(LLMError) as exc:
        _provider(handler).complete([ChatMessage("user", "oi")], max_output_tokens=5)
    assert exc.value.kind == "http_401"
    assert calls == 1


def test_timeout_becomes_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento", request=request)

    with pytest.raises(LLMError) as exc:
        _provider(handler).complete([ChatMessage("user", "oi")], max_output_tokens=5)
    assert exc.value.kind == "timeout"


def test_unexpected_shape_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(LLMError) as exc:
        _provider(handler).complete([ChatMessage("user", "oi")], max_output_tokens=5)
    assert exc.value.kind == "bad_response"


def test_pricing_cost() -> None:
    assert PRICING.cost(1_000_000, 1_000_000) == Decimal("3.5")
    assert PRICING.cost(1000, 500) == Decimal("0.002")


def test_provider_disabled_until_fully_configured() -> None:
    complete = {
        "llm_provider_name": "alibaba",
        "llm_base_url": "https://llm.example/v1",
        "llm_api_key": SecretStr("k"),
        "llm_model": "qwen-test",
        "llm_price_input_per_mtok": Decimal("0.5"),
        "llm_price_output_per_mtok": Decimal("3"),
    }
    assert build_llm_provider(Settings(**complete)) is not None

    without_price = {**complete, "llm_price_output_per_mtok": None}
    settings = Settings(**without_price)
    assert build_llm_provider(settings) is None
    assert missing_llm_settings(settings) == ["VISION_LLM_PRICE_OUTPUT_PER_MTOK"]


def test_free_pricing_is_allowed() -> None:
    settings = Settings(
        llm_provider_name="local",
        llm_base_url="http://127.0.0.1:8001/v1",
        llm_api_key=SecretStr("k"),
        llm_model="qwen-local",
        llm_price_input_per_mtok=Decimal(0),
        llm_price_output_per_mtok=Decimal(0),
    )
    assert build_llm_provider(settings) is not None


def test_blank_env_values_mean_unconfigured() -> None:
    settings = Settings(llm_api_key="", llm_price_input_per_mtok="  ", llm_model="")
    assert settings.llm_api_key is None
    assert settings.llm_price_input_per_mtok is None
    assert build_llm_provider(settings) is None


def test_rate_limit_honors_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(openai_compatible.time, "sleep", sleeps.append)
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(429),
            httpx.Response(200, json=OK_BODY),
        ]
    )

    _provider(lambda request: next(responses)).complete(
        [ChatMessage("user", "oi")], max_output_tokens=5
    )

    # Retry-After wins; without it, rate limits back off longer than server errors.
    assert sleeps == [7.0, 10.0]


def test_retry_after_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(openai_compatible.time, "sleep", sleeps.append)
    responses = iter(
        [httpx.Response(503, headers={"Retry-After": "3600"}), httpx.Response(200, json=OK_BODY)]
    )

    _provider(lambda request: next(responses)).complete(
        [ChatMessage("user", "oi")], max_output_tokens=5
    )

    assert sleeps == [30.0]
