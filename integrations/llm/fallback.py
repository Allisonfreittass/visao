"""Ordered fallback across LLM providers (e.g. OpenRouter free tier, then NVIDIA's API).

Moves to the next provider only on failures that another host may not share: exhausted quota,
rate limits, server errors, timeouts, network errors and malformed responses. Client errors
such as an invalid key (http_401) are raised at once, so a misconfiguration is never hidden.

The order is the configured one unless `order` says otherwise for this call (the order per task,
core/llm_routing.py, ADR-0022). A provider out of quota is skipped until the reset it announced;
with a `PauseBoard` the API and the worker see the same pause.
"""

import logging
import time
from collections.abc import Callable

from integrations.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse, Pricing
from integrations.llm.pause import DEFAULT_SECONDS, PauseBoard, key, pause_seconds

logger = logging.getLogger(__name__)

_FALLBACK_KINDS = {
    "quota_exhausted",
    "http_429",
    "timeout",
    "network",
    "bad_response",
    "budget_denied",
    "too_large",  # a host with a bigger limit may take the same request
}
QUOTA_COOLDOWN_SECONDS = DEFAULT_SECONDS


def _should_fall_back(kind: str) -> bool:
    return kind in _FALLBACK_KINDS or kind.startswith("http_5")


class FallbackLLMProvider:
    def __init__(
        self,
        providers: list[LLMProvider],
        *,
        order: Callable[[], list[int]] | None = None,
        pauses: PauseBoard | None = None,
    ) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = providers
        self._order = order
        self._pauses = pauses
        self._skip_until = [0.0] * len(providers)
        self.name = "+".join(p.name for p in providers)
        self.model = providers[0].model
        self.pricing: Pricing = providers[0].pricing

    def order(self) -> list[int]:
        """The indexes to try for this call. A broken or malformed order falls back to the
        configured one: choosing must never cost the reply."""
        configured = list(range(len(self._providers)))
        if self._order is None:
            return configured
        try:
            chosen = list(self._order())
        except Exception:  # noqa: BLE001
            logger.warning("llm order unavailable", extra={"event": "llm_order_failed"})
            return configured
        return chosen if sorted(chosen) == configured else configured

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        last_error = LLMError("budget_denied", "no eligible provider outside cooldown")
        shared = self._pauses.snapshot() if self._pauses else {}
        for index in self.order():
            provider = self._providers[index]
            # A provider whose quota ran out is skipped for a while instead of wasting a call.
            if time.monotonic() < self._skip_until[index]:
                continue
            if shared.get(key(provider.name, provider.model), 0) > time.time():
                continue
            paid = provider.pricing.input_per_mtok != 0 or provider.pricing.output_per_mtok != 0
            # A priced provider only when its guard has spending caps (budget.py enforces them).
            if paid and not getattr(provider, "admits_paid", False):
                last_error = LLMError("budget_denied", "paid provider refused before dispatch")
                continue
            try:
                return provider.complete(messages, max_output_tokens=max_output_tokens)
            except LLMError as exc:
                if not _should_fall_back(exc.kind):
                    raise
                if exc.kind == "quota_exhausted":
                    self._pause(index, exc.retry_at)
                logger.warning(
                    f"llm provider {provider.name} failed ({exc.kind}), trying next",
                    extra={"event": "llm_fallback"},
                )
                last_error = exc
        raise last_error

    def _pause(self, index: int, retry_at: float | None) -> None:
        now = time.time()
        seconds = pause_seconds(retry_at, now)
        self._skip_until[index] = time.monotonic() + seconds
        if self._pauses is not None:
            provider = self._providers[index]
            self._pauses.pause(provider.name, provider.model, now + seconds)
