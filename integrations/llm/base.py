"""Model-agnostic LLM interface. The agent's state never lives behind this boundary."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ImagePart:
    """A picture that goes with a message. Bytes as received; each provider encodes them."""

    media_type: str
    data: bytes


# Rough tokens one picture costs, for budget reservations (a 1568 px photo is about 1600).
IMAGE_TOKEN_ESTIMATE = 1600


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    images: tuple[ImagePart, ...] = ()


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    finish_reason: str | None
    # Priced by whichever provider actually answered (matters when a fallback took over).
    cost_usd: Decimal


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens, as configured. Never guessed."""

    input_per_mtok: Decimal
    output_per_mtok: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        return (
            Decimal(input_tokens) * self.input_per_mtok
            + Decimal(output_tokens) * self.output_per_mtok
        ) / million


class LLMError(Exception):
    """The provider failed. `kind` is safe to log; the message may contain provider details."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class LLMProvider(Protocol):
    name: str
    model: str
    pricing: Pricing

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse: ...


# Where a provider that can stream says the reply written so far (in a voice call, so the phone can
# speak the first sentence while the rest is written). A context variable instead of a new
# `complete` argument: the wrappers in between (budget guard, fallback) pass it through untouched,
# and a provider that cannot stream simply ignores it and answers whole, as before. Calls made on
# other threads (the rule check) do not see it.
_draft_sink: ContextVar[Callable[[str], None] | None] = ContextVar("llm_draft_sink", default=None)


@contextmanager
def drafting(sink: Callable[[str], None]) -> Iterator[None]:
    """Inside this block, a streaming provider calls `sink` with the whole text so far, each time
    it grows. A new attempt (a fallback provider) starts over from the beginning."""
    token = _draft_sink.set(sink)
    try:
        yield
    finally:
        _draft_sink.reset(token)


def tell_draft(text: str) -> None:
    """Hands the text so far to the sink, if any. Never lets the sink break the call."""
    sink = _draft_sink.get()
    if sink is None:
        return
    try:
        sink(text)
    except Exception:  # noqa: BLE001 - a live preview must never cost the reply
        logging.getLogger(__name__).warning("draft sink failed", extra={"event": "draft_failed"})


def wants_draft() -> bool:
    return _draft_sink.get() is not None
