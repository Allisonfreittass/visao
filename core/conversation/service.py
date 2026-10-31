"""Text conversation turn: history within one conversation, budget check, LLM call, usage log.

Context comes only from the current conversation. Nothing from other conversations or users is
ever sent to the model; cross-conversation recall arrives with curated memory (Phase 3).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.identity.system_prompt import build_system_prompt
from infrastructure.database.models import AgentIdentity, Conversation, Message, ModelUsage
from integrations.llm.base import ChatMessage, LLMError, LLMProvider

PURPOSE_CHAT = "chat_reply"


class BudgetExceededError(Exception):
    def __init__(self, scope: str, spent: Decimal, limit: Decimal) -> None:
        super().__init__(f"{scope} LLM budget exhausted: {spent} of {limit} USD")
        self.scope = scope


class EmptyReplyError(Exception):
    pass


@dataclass(frozen=True)
class Budgets:
    daily_usd: Decimal
    conversation_usd: Decimal


@dataclass(frozen=True)
class TurnResult:
    user_message: Message
    assistant_message: Message
    usage: ModelUsage


def _spent(session: Session, *conditions: object) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(ModelUsage.cost_usd), 0)).where(*conditions)
    )
    return Decimal(str(total))


def check_budgets(session: Session, conversation: Conversation, budgets: Budgets) -> None:
    """Pre-call check. A single call can overshoot by at most one reply (bounded by max tokens)."""
    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    daily = _spent(session, ModelUsage.created_at >= start_of_day)
    if daily >= budgets.daily_usd:
        raise BudgetExceededError("daily", daily, budgets.daily_usd)
    per_conversation = _spent(session, ModelUsage.conversation_id == conversation.id)
    if per_conversation >= budgets.conversation_usd:
        raise BudgetExceededError("conversation", per_conversation, budgets.conversation_usd)


def conversation_history(session: Session, conversation: Conversation) -> list[Message]:
    return list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.id)
        )
    )


def build_context(history: list[Message], char_budget: int) -> list[ChatMessage]:
    """Most recent messages that fit the budget, oldest first. The latest one is always kept."""
    selected: list[ChatMessage] = []
    used = 0
    for message in reversed(history):
        if selected and used + len(message.content) > char_budget:
            break
        selected.append(ChatMessage(role=message.role, content=message.content))  # type: ignore[arg-type]
        used += len(message.content)
    selected.reverse()
    return selected


def reply(
    session: Session,
    *,
    conversation: Conversation,
    identity: AgentIdentity,
    user_text: str,
    provider: LLMProvider,
    budgets: Budgets,
    max_output_tokens: int,
    context_char_budget: int,
) -> TurnResult:
    check_budgets(session, conversation, budgets)

    user_message = Message(conversation_id=conversation.id, role="user", content=user_text)
    session.add(user_message)
    session.commit()

    prompt = [ChatMessage(role="system", content=build_system_prompt(identity))]
    prompt += build_context(conversation_history(session, conversation), context_char_budget)

    try:
        response = provider.complete(prompt, max_output_tokens=max_output_tokens)
    except LLMError as exc:
        _record_failure(session, conversation, provider, exc.kind)
        raise

    usage = ModelUsage(
        conversation_id=conversation.id,
        purpose=PURPOSE_CHAT,
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=provider.pricing.cost(response.input_tokens, response.output_tokens),
        latency_ms=response.latency_ms,
        outcome="success" if response.text.strip() else "empty",
    )
    session.add(usage)
    if not response.text.strip():
        session.commit()
        raise EmptyReplyError("provider returned an empty reply")

    assistant_message = Message(
        conversation_id=conversation.id, role="assistant", content=response.text
    )
    session.add(assistant_message)
    session.flush()
    assistant_message.model_usage_id = usage.id
    session.commit()
    return TurnResult(user_message, assistant_message, usage)


def _record_failure(
    session: Session, conversation: Conversation, provider: LLMProvider, error_kind: str
) -> None:
    session.add(
        ModelUsage(
            conversation_id=conversation.id,
            purpose=PURPOSE_CHAT,
            provider=provider.name,
            model=provider.model,
            outcome="error",
            error_kind=error_kind[:50],
        )
    )
    session.commit()
