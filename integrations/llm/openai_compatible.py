"""Provider for any OpenAI-compatible /chat/completions endpoint (Alibaba Model Studio,
OpenRouter, DeepInfra, vLLM...). Choosing a host is configuration, not code."""

import base64
import json
import logging
import re
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from integrations.llm.base import (
    ChatMessage,
    LLMError,
    LLMResponse,
    Pricing,
    ToolCall,
    cache_key,
    offered_tools,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
_MAX_RETRY_DELAY_SECONDS = 30.0


def _content(message: ChatMessage) -> str | list[dict]:
    if not message.images:
        return message.content
    parts: list[dict] = [{"type": "text", "text": message.content}] if message.content else []
    for image in message.images:
        encoded = base64.b64encode(image.data).decode("ascii")
        parts.append(
            {"type": "image_url", "image_url": {"url": f"data:{image.media_type};base64,{encoded}"}}
        )
    return parts


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
        extra_body: dict | None = None,
        native_tools: bool | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.pricing = pricing
        self._max_retries = max_retries
        self._extra_body = extra_body or {}
        # OpenAI's reasoning models (gpt-5 and later) refuse max_tokens with a 400 and take
        # max_completion_tokens, which bounds the reasoning plus the answer. Other hosts
        # (Gemini, Groq, OpenRouter) keep the classic name.
        self._output_param = (
            "max_completion_tokens" if "api.openai.com" in base_url.lower() else "max_tokens"
        )
        # Tools go natively only where they were checked (OpenAI); elsewhere (Gemini, Groq,
        # OpenRouter) the caller's prompt carries them as a JSON protocol (ADR-0023).
        self._native_tools = (
            "api.openai.com" in base_url.lower() if native_tools is None else native_tools
        )
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            transport=transport,
        )

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        payload = {
            **self._extra_body,
            "model": self.model,
            "messages": [{"role": m.role, "content": _content(m)} for m in messages],
            self._output_param: max_output_tokens,
        }
        if self._native_tools and cache_key():
            payload["prompt_cache_key"] = cache_key()
        tools = offered_tools() if self._native_tools else ()
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        started = time.monotonic()
        response = self._post_with_retries(payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            body = response.json()
            choice = body["choices"][0]
            usage = body["usage"]
            text = choice["message"].get("content") or ""
            calls = _tool_calls(choice["message"].get("tool_calls"))
            input_tokens = int(usage["prompt_tokens"])
            output_tokens = int(usage["completion_tokens"])
            configured_cost = self.pricing.cost(input_tokens, output_tokens)
            reported_cost = (
                Decimal(str(usage["cost"])) if usage.get("cost") is not None else configured_cost
            )
            if not reported_cost.is_finite() or reported_cost < 0:
                raise ValueError("invalid reported cost")
        except (ValueError, KeyError, IndexError, TypeError, InvalidOperation) as exc:
            raise LLMError("bad_response", f"unexpected response shape: {exc}") from exc

        return LLMResponse(
            text=text,
            provider=self.name,
            model=body.get("model", self.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason"),
            # Never hide a positive provider-reported cost behind configured free prices.
            cost_usd=max(configured_cost, reported_cost),
            tool_calls=calls,
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
                exhausted, retry_at = _quota(response)
                if exhausted:
                    raise LLMError(
                        "quota_exhausted",
                        f"provider quota exhausted; retrying won't help: {response.text[:300]}",
                        retry_at=retry_at,
                    )
                if response.status_code == 413:
                    # Real case (2026-11-21): Groq's free tier caps a request at 8 000 tokens per
                    # minute, below one chat turn. Another host in the chain may take it.
                    raise LLMError(
                        "too_large",
                        f"request too large for this provider: {response.text[:300]}",
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


def _tool_calls(raw: object) -> tuple[ToolCall, ...]:
    """Calls whose arguments are not a JSON object are dropped: the caller then sees no call and
    tells the model its answer was not an action."""
    calls = []
    for item in raw if isinstance(raw, list) else []:
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict) or not function.get("name"):
            continue
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(arguments, dict):
            calls.append(ToolCall(str(function["name"]), arguments))
    return tuple(calls)


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


def _error_body(response: httpx.Response) -> dict:
    """The error object, as OpenAI ({"error": ...}) or Gemini ([{"error": ...}]) sends it."""
    try:
        body = response.json()
    except ValueError:
        return {}
    if isinstance(body, list) and body:
        body = body[0]
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, dict) else {}


def _next_pacific_midnight(now: float) -> float | None:
    """Gemini's daily free quota comes back at midnight, Pacific time."""
    try:
        zone = ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        return None
    here = datetime.fromtimestamp(now, zone)
    return (here.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def _seconds(text: object) -> float | None:
    """ "43s" or "1.5s" (Google's RetryInfo.retryDelay) -> 43.0."""
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", str(text).strip())
    return float(match.group(1)) if match else None


def _quota(response: httpx.Response) -> tuple[bool, float | None]:
    """(exhausted, when it comes back in seconds since the epoch, if the provider said).

    Exhausted means retrying soon won't help: no requests left until a reset further away than we
    would ever wait (e.g. a daily free-tier cap), or an account without credit. Short
    per-minute limits stay a plain 429 and still get retried."""
    now = time.time()
    if response.status_code != 429:
        return False, None
    error = _error_body(response)
    # OpenAI: the account ran out of credit.
    if error.get("code") == "insufficient_quota" or error.get("type") == "insufficient_quota":
        return True, None
    # Gemini: RESOURCE_EXHAUSTED, a per-day quota or a long RetryInfo delay.
    if error.get("status") == "RESOURCE_EXHAUSTED":
        details = [d for d in error.get("details") or [] if isinstance(d, dict)]
        if "PerDay" in json.dumps(details):
            return True, _next_pacific_midnight(now)
        for detail in details:
            delay = _seconds(detail.get("retryDelay", ""))
            if delay is not None and delay > _MAX_RETRY_DELAY_SECONDS:
                return True, now + delay
        return False, None
    headers = _rate_limit_headers(response)
    if headers.get("x-ratelimit-remaining") != "0":
        return False, None
    reset = headers.get("x-ratelimit-reset")
    if reset is None:
        return True, None
    try:
        reset_at = float(reset)
    except ValueError:
        return True, None
    if reset_at > 1e12:  # milliseconds since epoch
        reset_at /= 1000
    if reset_at - now > _MAX_RETRY_DELAY_SECONDS:
        return True, reset_at
    return False, None
