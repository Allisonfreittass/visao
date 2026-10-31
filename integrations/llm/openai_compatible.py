"""Provider for any OpenAI-compatible /chat/completions endpoint (Alibaba Model Studio,
OpenRouter, DeepInfra, vLLM...). Choosing a host is configuration, not code."""

import logging
import time

import httpx

from integrations.llm.base import ChatMessage, LLMError, LLMResponse, Pricing

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


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
        )

    def _post_with_retries(self, payload: dict) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            last_attempt = attempt == self._max_retries
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
                if response.status_code not in _RETRYABLE_STATUS or last_attempt:
                    raise LLMError(
                        f"http_{response.status_code}",
                        f"provider returned {response.status_code}: {response.text[:300]}",
                    )
            delay = 0.5 * 2**attempt
            logger.warning("llm call failed, retrying", extra={"event": "llm_retry"})
            time.sleep(delay)
        raise AssertionError("unreachable")
