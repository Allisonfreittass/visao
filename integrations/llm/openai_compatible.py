"""Provider for any OpenAI-compatible /chat/completions endpoint (Alibaba Model Studio,
OpenRouter, DeepInfra, vLLM...). Choosing a host is configuration, not code."""

import logging
import time

import httpx

from integrations.llm.base import ChatMessage, LLMError, LLMResponse, Pricing

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
_MAX_RETRY_DELAY_SECONDS = 30.0


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        pricing: Pricing,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.pricing = pricing
        self._max_retries = max_retries
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            transport=transport,
        )

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_output_tokens,
        }
        started = time.monotonic()
        response = self._post_with_retries(payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            body = response.json()
            choice = body["choices"][0]
            usage = body["usage"]
            text = choice["message"]["content"] or ""
            input_tokens = int(usage["prompt_tokens"])
            output_tokens = int(usage["completion_tokens"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("bad_response", f"unexpected response shape: {exc}") from exc

        return LLMResponse(
            text=text,
            provider=self.name,
            model=body.get("model", self.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason"),
            cost_usd=self.pricing.cost(input_tokens, output_tokens),
        )

    def _post_with_retries(self, payload: dict) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            last_attempt = attempt == self._max_retries
            response: httpx.Response | None = None
            try:
                response = self._client.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:
                if last_attempt:
                    raise LLMError("timeout", "provider timed out") from exc
            except httpx.HTTPError as exc:
                if last_attempt:
                    raise LLMError("network", f"network error: {type(exc).__name__}") from exc
            else:
                if response.status_code < 400:
                    return response
                if response.status_code == 429 and _quota_exhausted(response):
                    raise LLMError(
                        "quota_exhausted",
                        f"provider quota exhausted; retrying won't help: {response.text[:300]}",
                    )
                if response.status_code not in _RETRYABLE_STATUS or last_attempt:
                    raise LLMError(
                        f"http_{response.status_code}",
                        f"provider returned {response.status_code}: {response.text[:300]}",
                    )
            delay = _retry_delay(response, attempt)
            logger.warning(
                f"llm call failed, retrying in {delay:.1f}s", extra={"event": "llm_retry"}
            )
            time.sleep(delay)
        raise AssertionError("unreachable")


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Honors Retry-After (seconds) when the provider sends it; otherwise exponential backoff.
    Rate limits get a longer base delay than transient server errors."""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), _MAX_RETRY_DELAY_SECONDS)
            except ValueError:
                pass
        if response.status_code == 429:
            return min(5.0 * 2**attempt, _MAX_RETRY_DELAY_SECONDS)
    return min(0.5 * 2**attempt, _MAX_RETRY_DELAY_SECONDS)


def _rate_limit_headers(response: httpx.Response) -> dict[str, str]:
    """X-RateLimit-* from the HTTP headers or, as OpenRouter does on errors, from the body's
    error.metadata.headers. Keys are lower-cased."""
    found = {
        k.lower(): v for k, v in response.headers.items() if k.lower().startswith("x-ratelimit")
    }
    if found:
        return found
    try:
        nested = response.json()["error"]["metadata"]["headers"]
    except (ValueError, KeyError, TypeError):
        return {}
    if not isinstance(nested, dict):
        return {}
    return {
        str(k).lower(): str(v)
        for k, v in nested.items()
        if str(k).lower().startswith("x-ratelimit")
    }


def _quota_exhausted(response: httpx.Response) -> bool:
    """True when the provider says no requests remain until a reset further away than we would
    ever wait (e.g. a daily free-tier cap). Short per-minute limits still get retried."""
    headers = _rate_limit_headers(response)
    if headers.get("x-ratelimit-remaining") != "0":
        return False
    reset = headers.get("x-ratelimit-reset")
    if reset is None:
        return True
    try:
        reset_at = float(reset)
    except ValueError:
        return True
    if reset_at > 1e12:  # milliseconds since epoch
        reset_at /= 1000
    return reset_at - time.time() > _MAX_RETRY_DELAY_SECONDS
