"""Model-agnostic LLM interface. The agent's state never lives behind this boundary."""

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
