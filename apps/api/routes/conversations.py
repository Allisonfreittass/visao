import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from apps.api.deps import AppSettings, CurrentUser, DbSession
from apps.api.llm import get_llm_provider, missing_llm_settings
from core.conversation.service import (
    BudgetExceededError,
    Budgets,
    EmptyReplyError,
    conversation_history,
    reply,
)
from core.identity.genesis import get_identity
from infrastructure.database.models import Conversation, Message
from integrations.llm.base import LLMError, LLMProvider

router = APIRouter(prefix="/conversations", tags=["conversations"])

MAX_MESSAGE_CHARS = 8000


class ConversationOut(BaseModel):
    id: uuid.UUID
    created_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class UsageOut(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int | None


class TurnOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    usage: UsageOut


def _message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id, role=message.role, content=message.content, created_at=message.created_at
    )


def _own_conversation(db: DbSession, user: CurrentUser, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    # Someone else's conversation is indistinguishable from a missing one.
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada")
    return conversation


@router.post("", status_code=status.HTTP_201_CREATED)
def create_conversation(db: DbSession, user: CurrentUser) -> ConversationOut:
    identity = get_identity(db)
    if identity is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado")
    conversation = Conversation(user_id=user.id, identity_id=identity.id)
    db.add(conversation)
    db.commit()
    return ConversationOut(id=conversation.id, created_at=conversation.created_at)


@router.get("")
def list_conversations(db: DbSession, user: CurrentUser) -> list[ConversationOut]:
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
    )
    return [ConversationOut(id=c.id, created_at=c.created_at) for c in conversations]


@router.get("/{conversation_id}/messages")
def list_messages(conversation_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[MessageOut]:
    conversation = _own_conversation(db, user, conversation_id)
    return [_message_out(m) for m in conversation_history(db, conversation)]


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: uuid.UUID,
    body: MessageIn,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: Annotated[LLMProvider | None, Depends(get_llm_provider)],
) -> TurnOut:
    conversation = _own_conversation(db, user, conversation_id)
    if provider is None:
        missing = ", ".join(missing_llm_settings(settings))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"LLM não configurado. Faltam: {missing}"
        )
    identity = get_identity(db)
    if identity is None or identity.id != conversation.identity_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Identidade da conversa indisponível")

    try:
        result = reply(
            db,
            conversation=conversation,
            identity=identity,
            user_text=body.content,
            provider=provider,
            budgets=Budgets(
                daily_usd=settings.llm_daily_budget_usd,
                conversation_usd=settings.llm_conversation_budget_usd,
            ),
            max_output_tokens=settings.llm_max_output_tokens,
            context_char_budget=settings.llm_context_char_budget,
        )
    except BudgetExceededError as exc:
        scope = "diário" if exc.scope == "daily" else "desta conversa"
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, f"Orçamento {scope} de LLM esgotado"
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Falha no provedor de LLM ({exc.kind}); sem resposta"
        ) from exc
    except EmptyReplyError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "O provedor de LLM devolveu resposta vazia"
        ) from exc

    usage = result.usage
    return TurnOut(
        user_message=_message_out(result.user_message),
        assistant_message=_message_out(result.assistant_message),
        usage=UsageOut(
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            latency_ms=usage.latency_ms,
        ),
    )
