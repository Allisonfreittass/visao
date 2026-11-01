"""Ordered fallback across LLM providers (e.g. OpenRouter free tier, then NVIDIA's API).

Moves to the next provider only on failures that another host may not share: exhausted quota,
rate limits, server errors, timeouts, network errors and malformed responses. Client errors
such as an invalid key (http_401) are raised at once, so a misconfiguration is never hidden.
"""

import logging
import time

from integrations.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse, Pricing

logger = logging.getLogger(__name__)

_FALLBACK_KINDS = {
    "quota_exhausted",
    "http_429",
    "timeout",
    "network",
    "bad_response",
    "budget_denied",
}
QUOTA_COOLDOWN_SECONDS = 15 * 60


def _should_fall_back(kind: str) -> bool:
    return kind in _FALLBACK_KINDS or kind.startswith("http_5")


class FallbackLLMProvider:
    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = providers
        self._skip_until = [0.0] * len(providers)
        self.name = "+".join(p.name for p in providers)
        self.model = providers[0].model
        self.pricing: Pricing = providers[0].pricing

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        last_error = LLMError("budget_denied", "no eligible provider outside cooldown")
        for index, provider in enumerate(self._providers):
            # A provider whose quota ran out is skipped for a while instead of wasting a call.
            if time.monotonic() < self._skip_until[index]:
                continue
            if provider.pricing.input_per_mtok != 0 or provider.pricing.output_per_mtok != 0:
                last_error = LLMError("budget_denied", "paid provider refused before dispatch")
                continue
            try:
                return provider.complete(messages, max_output_tokens=max_output_tokens)
            except LLMError as exc:
                if not _should_fall_back(exc.kind):
                    raise
                if exc.kind == "quota_exhausted":
                    self._skip_until[index] = time.monotonic() + QUOTA_COOLDOWN_SECONDS
                logger.warning(
                    f"llm provider {provider.name} failed ({exc.kind}), trying next",
                    extra={"event": "llm_fallback"},
                )
                last_error = exc
        raise last_error
