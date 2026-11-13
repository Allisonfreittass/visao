"""Claude through the official Anthropic SDK (Messages API).

Same contract as the other providers: text in, text out, tokens and cost of this one call. The
agent's state never lives here. Retries are off: each attempt needs its own budget reservation
(integrations/llm/budget.py), so the fallback chain, not the SDK, decides whether to try again.
"""

import base64
import time
from typing import Any

import anthropic

from integrations.llm.base import ChatMessage, LLMError, LLMResponse, Pricing

# Only these request fields can come from configuration (VISION_LLM_FAST_EXTRA_BODY etc.).
_ALLOWED_EXTRA = {"thinking", "output_config"}
# The Messages API needs the conversation to open with the person; an opening the agent made
# on its own (an initiative) would otherwise be rejected.
_OPENING = "(Conversa aberta por você; a pessoa ainda não falou.)"


def _content(message: ChatMessage) -> str | list[dict[str, Any]]:
    if not message.images:
        return message.content
    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.media_type,
                "data": base64.b64encode(image.data).decode("ascii"),
            },
        }
        for image in message.images
    ]
    if message.content.strip():
        blocks.append({"type": "text", "text": message.content})
    return blocks


def to_messages_api(messages: list[ChatMessage]) -> tuple[str, list[dict[str, Any]]]:
    """System prompts become the top-level `system`; turns keep their order."""
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    turns = [{"role": m.role, "content": _content(m)} for m in messages if m.role != "system"]
    if turns and turns[0]["role"] == "assistant":
        turns.insert(0, {"role": "user", "content": _OPENING})
    if not turns:
        turns = [{"role": "user", "content": _OPENING}]
    return system, turns


class AnthropicProvider:
    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        model: str,
        pricing: Pricing,
        timeout_seconds: float = 60.0,
        extra_body: dict | None = None,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.pricing = pricing
        self._extra = {k: v for k, v in (extra_body or {}).items() if k in _ALLOWED_EXTRA}
        self._client = client or anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        system, turns = to_messages_api(messages)
        request: dict[str, Any] = {
            **self._extra,
            "model": self.model,
            "max_tokens": max_output_tokens,
            "messages": turns,
        }
        if system:
            request["system"] = system
        started = time.monotonic()
        try:
            response = self._client.messages.create(**request)
        except anthropic.APITimeoutError as exc:
            raise LLMError("timeout", "provider timed out") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("network", f"network error: {type(exc).__name__}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("http_429", "rate limited") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"http_{exc.status_code}", f"provider error {exc.status_code}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.stop_reason == "refusal":
            raise LLMError("refusal", "the model declined this request")
        try:
            text = "".join(block.text for block in response.content if block.type == "text")
            usage = response.usage
            input_tokens = (
                int(usage.input_tokens)
                + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
                + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            )
            output_tokens = int(usage.output_tokens)
        except (AttributeError, TypeError, ValueError) as exc:
            raise LLMError("bad_response", f"unexpected response shape: {exc}") from exc
        return LLMResponse(
            text=text,
            provider=self.name,
            model=getattr(response, "model", self.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            finish_reason="length"
            if response.stop_reason == "max_tokens"
            else response.stop_reason,
            cost_usd=self.pricing.cost(input_tokens, output_tokens),
        )
