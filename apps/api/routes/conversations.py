import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.deps import AppSettings, CurrentUser, DbSession, SessionFactory
from apps.api.llm import get_llm_provider, missing_llm_settings
from apps.api.search import get_search_provider
from apps.api.settings import Settings
from core.conversation.service import (
    BudgetExceededError,
    Budgets,
    EmptyReplyError,
    conversation_history,
    reply,
)
from core.curiosity.engine import NO_OUTCOME, CuriosityLimits, consider
from core.identity.genesis import get_identity
from core.memory.curator import (
    CurationOutputError,
    curate_conversation,
    latest_uncurated_conversation,
)
from core.policies.autonomy import is_paused
from core.reflection.reflect import reflect
from infrastructure.database.models import Conversation, Message, User
from integrations.llm.base import LLMError, LLMProvider
from integrations.search.base import SearchProvider

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)

OptionalProvider = Annotated[LLMProvider | None, Depends(get_llm_provider)]

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


class CurationOut(BaseModel):
    skipped_reason: str | None
    stored: int
    discarded: int
    rejected: int


class SourceOut(BaseModel):
    title: str
    url: str
    source: str


class CuriosityOut(BaseModel):
    action: str
    reason: str
    status: str
    question: str
    # Set when an unanswered question became a goal proposal waiting for approval.
    proposed_goal_id: uuid.UUID | None = None


class TurnOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    usage: UsageOut
    curiosity: CuriosityOut | None = None
    sources: list[SourceOut] = []


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
def create_conversation(
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    factory: SessionFactory,
    provider: OptionalProvider,
    background: BackgroundTasks,
) -> ConversationOut:
    identity = get_identity(db)
    if identity is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado")
    conversation = Conversation(user_id=user.id, identity_id=identity.id)
    db.add(conversation)
    db.commit()
    # Starting a new conversation is the event that closes the previous one for curation.
    if user.memory_consent and provider is not None:
        background.add_task(_curate_previous, factory, user.id, conversation.id, provider, settings)
    # ...and the event that lets the agent reflect on it, if there is evidence to reflect on.
    if provider is not None:
        background.add_task(
            _reflect_previous, factory, user.id, conversation.id, provider, settings
        )
    return ConversationOut(id=conversation.id, created_at=conversation.created_at)


def _budgets(settings: Settings) -> Budgets:
    return Budgets(
        daily_usd=settings.llm_daily_budget_usd,
        conversation_usd=settings.llm_conversation_budget_usd,
    )


def _curate_previous(
    factory: sessionmaker[Session],
    user_id: uuid.UUID,
    new_conversation_id: uuid.UUID,
    provider: LLMProvider,
    settings: Settings,
) -> None:
    """Background task: failures are logged, never surfaced, and leave messages pending."""
    try:
        with factory() as session:
            owner = session.get(User, user_id)
            new = session.get(Conversation, new_conversation_id)
            if owner is None or not owner.memory_consent:
                return
            previous = latest_uncurated_conversation(session, owner, exclude=new)
            if previous is None:
                return
            curate_conversation(
                session,
                conversation=previous,
                owner=owner,
                provider=provider,
                budgets=_budgets(settings),
                max_output_tokens=settings.llm_curation_max_output_tokens,
            )
    except Exception:
        logger.exception("background memory curation failed", extra={"event": "curation_failed"})


def _reflect_previous(
    factory: sessionmaker[Session],
    user_id: uuid.UUID,
    new_conversation_id: uuid.UUID,
    provider: LLMProvider,
    settings: Settings,
) -> None:
    """Background task: reflects once on the owner's previous conversation. Respects the
    autonomy pause (it is spending on the agent's own initiative). Failures are only logged."""
    try:
        with factory() as session:
            if is_paused(session):
                return
            owner = session.get(User, user_id)
            previous = session.scalar(
                select(Conversation)
                .where(
                    Conversation.user_id == user_id,
                    Conversation.id != new_conversation_id,
                    Conversation.last_reflected_at.is_(None),
                )
                .order_by(Conversation.created_at.desc())
                .limit(1)
            )
            if owner is None or previous is None:
                return
            reflect(
                session,
                conversation=previous,
                owner=owner,
                provider=provider,
                max_output_tokens=settings.llm_curation_max_output_tokens,
            )
    except Exception:
        logger.exception("background reflection failed", extra={"event": "reflection_failed"})


@router.post("/{conversation_id}/reflect")
def reflect_now(
    conversation_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: OptionalProvider,
) -> dict[str, object]:
    conversation = _own_conversation(db, user, conversation_id)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM não configurado")
    try:
        result = reflect(
            db,
            conversation=conversation,
            owner=user,
            provider=provider,
            max_output_tokens=settings.llm_curation_max_output_tokens,
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Falha no provedor ({exc.kind})") from exc
    return result.__dict__


@router.post("/{conversation_id}/curate")
def curate(
    conversation_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: OptionalProvider,
) -> CurationOut:
    conversation = _own_conversation(db, user, conversation_id)
    if provider is None:
        missing = ", ".join(missing_llm_settings(settings))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"LLM não configurado. Faltam: {missing}"
        )
    try:
        result = curate_conversation(
            db,
            conversation=conversation,
            owner=user,
            provider=provider,
            budgets=_budgets(settings),
            max_output_tokens=settings.llm_curation_max_output_tokens,
        )
    except BudgetExceededError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Orçamento de LLM esgotado") from exc
    except LLMError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Falha no provedor de LLM ({exc.kind})"
        ) from exc
    except CurationOutputError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "O modelo devolveu uma curadoria ilegível; nada foi guardado",
        ) from exc
    return CurationOut(
        skipped_reason=result.skipped_reason,
        stored=result.stored,
        discarded=result.discarded,
        rejected=result.rejected,
    )


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
    provider: OptionalProvider,
    search: Annotated[SearchProvider, Depends(get_search_provider)],
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
        outcome = NO_OUTCOME
        if settings.curiosity_enabled:
            outcome = consider(
                db,
                conversation=conversation,
                owner=user,
                user_text=body.content,
                provider=provider,
                search=search,
                budgets=_budgets(settings),
                limits=CuriosityLimits(
                    research_per_day=settings.research_per_day,
                    research_per_conversation=settings.research_per_conversation,
                    max_results=settings.research_max_results,
                ),
                max_output_tokens=settings.llm_curation_max_output_tokens,
            )
        result = reply(
            db,
            conversation=conversation,
            identity=identity,
            owner=user,
            user_text=body.content,
            provider=provider,
            budgets=_budgets(settings),
            max_output_tokens=settings.llm_max_output_tokens,
            context_char_budget=settings.llm_context_char_budget,
            extra_system=outcome.system_context,
        )
        if outcome.gap is not None:
            outcome.gap.trigger_message_id = result.user_message.id
            db.commit()
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
    gap = outcome.gap
    return TurnOut(
        curiosity=CuriosityOut(
            action=gap.chosen_action,
            reason=gap.decision_reason,
            status=gap.status,
            question=gap.question,
            proposed_goal_id=outcome.proposed_goal.id
            if outcome.proposed_goal is not None and outcome.proposed_goal.status == "EVALUATED"
            else None,
        )
        if gap is not None
        else None,
        sources=[SourceOut(title=s.title, url=s.url, source=s.source) for s in outcome.sources],
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
