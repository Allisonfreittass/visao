"""Each model gets the version of the prompt that fits its limit (docs/MODO_COMPACTO.md).

Real case (2026-11-21): Groq's free tier takes about 8 000 tokens per request, the answer
included, and one turn of the conversation sends 11 000 to 17 000. The model said 413 and the
person got no reply. Now the limit comes from configuration or is learned from the 413 itself,
and the model receives the largest version of the prompt (core.conversation.service builds them,
from complete to compact) that fits. A model with no known limit gets the complete prompt.
"""

import logging
import math
import re

from integrations.llm.base import (
    IMAGE_TOKEN_ESTIMATE,
    ChatMessage,
    LLMError,
    LLMProvider,
    LLMResponse,
    prompt_levels,
)
from integrations.llm.budget import input_estimate

logger = logging.getLogger(__name__)

BYTES_PER_TOKEN = 3  # conservative for Portuguese in JSON: accents are two bytes
SAFETY_TOKENS = 200
MIN_OUTPUT_TOKENS = 256
_LIMIT = re.compile(r"(?i)limit[^0-9]{0,12}([0-9][0-9_,.]{2,})")
# What each model said it accepts, learned from a 413 while this process runs.
_learned: dict[tuple[str, str], int] = {}


def tokens(messages: list[ChatMessage]) -> int:
    images = sum(len(m.images) for m in messages)
    return math.ceil(input_estimate(messages) / BYTES_PER_TOKEN) + images * IMAGE_TOKEN_ESTIMATE


def limit_in(message: str) -> int | None:
    """ "Limit 8000, Requested 14210" (Groq) -> 8000."""
    match = _LIMIT.search(message)
    if not match:
        return None
    value = int(re.sub(r"[_,.]", "", match.group(1)))
    return value if value >= 1000 else None


def forget_learned() -> None:
    _learned.clear()


class FittingProvider:
    """Wraps one model of the chain; passes everything else through untouched."""

    def __init__(self, provider: LLMProvider, max_request_tokens: int | None = None) -> None:
        self._inner = provider
        self._configured = max_request_tokens
        self.name, self.model, self.pricing = provider.name, provider.model, provider.pricing

    def __getattr__(self, name: str):
        # Transparent for whatever the wrapped provider offers (admits_paid, its own provider).
        if name.startswith("__") or name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)

    @property
    def limit(self) -> int | None:
        return self._configured or _learned.get((self.name, self.model))

    def _plan(
        self, levels: tuple[list[ChatMessage], ...], max_output_tokens: int, limit: int | None
    ) -> tuple[list[ChatMessage], int]:
        if limit is None:
            return levels[0], max_output_tokens
        # Groq counts the answer it may write against the same limit as the prompt.
        output = min(max_output_tokens, max(MIN_OUTPUT_TOKENS, limit // 4))
        room = limit - output - SAFETY_TOKENS
        chosen = next((level for level in levels if tokens(level) <= room), levels[-1])
        return chosen, output

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        levels = prompt_levels(messages)
        chosen, output = self._plan(levels, max_output_tokens, self.limit)
        if chosen is not levels[0]:
            self._log(levels, chosen)
        try:
            return self._inner.complete(chosen, max_output_tokens=output)
        except LLMError as exc:
            if exc.kind != "too_large":
                raise
            sent = tokens(chosen) + output
            learned = limit_in(str(exc)) or int(sent * 0.7)
            if learned >= sent:  # the number is not what we think it is: do not loop on it
                raise
            _learned[(self.name, self.model)] = learned
            retry, output = self._plan(levels, max_output_tokens, learned)
            if retry is chosen:
                raise
            self._log(levels, retry)
            return self._inner.complete(retry, max_output_tokens=output)

    def _log(self, levels, chosen) -> None:
        logger.info(
            f"compact prompt for {self.name}: level {levels.index(chosen)} of {len(levels) - 1}",
            extra={"event": "prompt_compacted", "tokens": tokens(chosen), "limit": self.limit},
        )
