"""Test doubles. Never used outside tests and never presented as a real capability."""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from integrations.llm.base import ChatMessage, LLMError, LLMResponse, Pricing


@dataclass
class FakeLLMProvider:
    name: str = "fake-provider"
    model: str = "fake-model"
    pricing: Pricing = field(
        default_factory=lambda: Pricing(input_per_mtok=Decimal("1"), output_per_mtok=Decimal("2"))
    )
    reply_text: str = "resposta de teste"
    # Optional: computes the reply from the prompt (e.g. curation JSON vs chat text).
    responder: Callable[[list[ChatMessage]], str] | None = None
    fail_with: str | None = None
    finish_reason: str = "stop"
    prompts: list[list[ChatMessage]] = field(default_factory=list)

    def complete(self, messages: list[ChatMessage], *, max_output_tokens: int) -> LLMResponse:
        self.prompts.append(list(messages))
        if self.fail_with:
            raise LLMError(self.fail_with, "falha simulada")
        return LLMResponse(
            text=self.responder(messages) if self.responder else self.reply_text,
            provider=self.name,
            model=self.model,
            input_tokens=1000,
            output_tokens=500,
            latency_ms=5,
            finish_reason=self.finish_reason,
            cost_usd=self.pricing.cost(1000, 500),
        )
