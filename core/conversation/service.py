"""Text conversation turn: history within one conversation, budget check, LLM call, usage log.

Raw history comes only from the current conversation. The only cross-conversation context is
curated memory of the same owner, and only when that owner opted in.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.behavior import state as behavior_state
from core.identity.capabilities import Capabilities
from core.identity.system_prompt import build_system_prompt
from core.memory.retrieval import ScoredMemory, retrieve
from infrastructure.database.models import (
    AgentIdentity,
    Conversation,
    MemoryRetrieval,
    Message,
    ModelUsage,
    User,
)
from integrations.llm.base import ChatMessage, LLMError, LLMProvider

PURPOSE_CHAT = "chat_reply"
TRUNCATION_NOTICE = "[resposta interrompida pelo limite de tamanho]"


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
    recalled: list[ScoredMemory]


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
    owner: User,
    user_text: str,
    provider: LLMProvider,
    budgets: Budgets,
    max_output_tokens: int,
    context_char_budget: int,
    extra_system: str | None = None,
    capabilities: Capabilities | None = None,
    modality: str = "text",
    name_history_summary: str | None = None,
) -> TurnResult:
    check_budgets(session, conversation, budgets)

    user_message = Message(conversation_id=conversation.id, role="user", content=user_text)
    session.add(user_message)
    session.flush()

    # Memory is recalled only for owners who opted in, and only from their own records.
    recalled = retrieve(session, owner.id, user_text) if owner.memory_consent else []
    for item in recalled:
        session.add(
            MemoryRetrieval(message_id=user_message.id, record_id=item.record.id, score=item.score)
        )
    session.commit()

    system_prompt = build_system_prompt(
        identity,
        memory_enabled=owner.memory_consent,
        memories=[item.record for item in recalled],
        capabilities=capabilities,
        name_history_summary=name_history_summary,
        modality=modality,
    )
    version, params = behavior_state.current_params(session, owner.id)
    adjustments = behavior_state.prompt_lines(params)
    if adjustments:
        system_prompt += (
            f"\n\nAjustes de comunicação aprendidos com o retorno deste interlocutor "
            f"(versão {version}, revertíveis):\n" + "\n".join(f"- {a}" for a in adjustments)
        )
    if extra_system:
        # Per-turn context from the curiosity pipeline (a question to ask, or sources).
        system_prompt += f"\n\nContexto desta resposta:\n{extra_system}"
    prompt = [ChatMessage(role="system", content=system_prompt)]
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
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
        outcome="success" if response.text.strip() else "empty",
    )
    truncated = response.finish_reason == "length"
    if truncated and response.text.strip():
        # Real case (2026-10-31): a reasoning model spent the output budget thinking and the
        # reply stopped mid-sentence. Never present a cut reply as complete.
        usage.outcome = "truncated"
    session.add(usage)
    if not response.text.strip():
        session.commit()
        raise EmptyReplyError("provider returned an empty reply")

    content = response.text
    if truncated:
        content = content.rstrip() + f"\n\n{TRUNCATION_NOTICE}"
    assistant_message = Message(conversation_id=conversation.id, role="assistant", content=content)
    session.add(assistant_message)
    session.flush()
    assistant_message.model_usage_id = usage.id
    # Observable behavior, measured in code, tagged with the state version in force.
    behavior_state.observe(session, assistant_message, owner.id)
    session.commit()
    return TurnResult(user_message, assistant_message, usage, recalled)


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
