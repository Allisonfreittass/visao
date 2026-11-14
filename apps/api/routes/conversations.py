import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.browser import get_browser
from apps.api.deps import AppSettings, CurrentUser, DbSession, SessionFactory
from apps.api.links import get_link_reader
from apps.api.llm import get_llm_provider, missing_llm_settings
from apps.api.routes.artifacts import ArtifactOut, artifact_out, build_in_background
from apps.api.routes.attachments import AttachmentOut, attachment_out
from apps.api.routes.projects import own_project
from apps.api.search import get_search_provider
from apps.api.settings import Settings
from apps.worker.handlers import autonomy_room
from core.conversation import artifacts, attachments, progress
from core.conversation.links import LinkReader
from core.conversation.service import (
    BudgetExceededError,
    Budgets,
    EmptyReplyError,
    conversation_history,
)
from core.curiosity.engine import CuriosityLimits
from core.decision import record as deed_record
from core.decision.pipeline import TurnConfig, run_turn
from core.identity.genesis import get_identity
from core.initiatives import push
from core.memory.curator import (
    CurationOutputError,
    curate_conversation,
    latest_uncurated_conversation,
)
from core.policies.autonomy import is_paused
from core.reflection.reflect import ReflectionResult, reflect
from infrastructure.database.models import Artifact, BrowseVisit, Conversation, Message, User
from integrations.browser.base import Browser
from integrations.llm.base import LLMError, LLMProvider
from integrations.search.base import SearchProvider

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)

OptionalProvider = Annotated[LLMProvider | None, Depends(get_llm_provider)]

MAX_MESSAGE_CHARS = 8000


class ConversationOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    memory_status: str | None = None
    project_id: uuid.UUID | None = None


class ConversationProjectIn(BaseModel):
    project_id: uuid.UUID | None = None


class QuotedOut(BaseModel):
    id: uuid.UUID
    role: str
    excerpt: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    origin: str = "turn"
    attachments: list[AttachmentOut] = []
    # A page this reply said it would write (docs/ARTEFATOS.md).
    artifact: ArtifactOut | None = None
    # The earlier message this one answers (Responder).
    reply_to: QuotedOut | None = None


class MessageIn(BaseModel):
    content: str = Field(default="", max_length=MAX_MESSAGE_CHARS)
    # "voice" when the turn came from a voice session: the reply is spoken, so kept short.
    modality: Literal["text", "voice"] = "text"
    # Tapping Responder on an earlier message of this conversation.
    reply_to_id: uuid.UUID | None = None
    # Uploaded first through POST /attachments; a photo alone is a whole message.
    attachment_ids: list[uuid.UUID] = Field(default=[], max_length=attachments.MAX_PER_MESSAGE)

    @model_validator(mode="after")
    def _says_something(self) -> "MessageIn":
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("mensagem vazia")
        return self


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


def _quoted(message: Message | None) -> QuotedOut | None:
    if message is None:
        return None
    text = " ".join(message.content.split())
    return QuotedOut(
        id=message.id, role=message.role, excerpt=text[:160] + ("…" if len(text) > 160 else "")
    )


def _message_out(
    message: Message, files: list | None = None, page=None, quoted: Message | None = None
) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        origin=message.origin or "turn",
        attachments=[attachment_out(a) for a in files or []],
        artifact=artifact_out(page) if page is not None else None,
        reply_to=_quoted(quoted),
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
    project_id: uuid.UUID | None = None,
) -> ConversationOut:
    identity = get_identity(db)
    if identity is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado")
    if project_id is not None:
        own_project(db, user.id, project_id)
    conversation = Conversation(user_id=user.id, identity_id=identity.id, project_id=project_id)
    db.add(conversation)
    db.commit()
    # The first turn must not race curation of the conversation it is asking to remember.
    memory_status = "disabled" if not user.memory_consent else "unavailable"
    if user.memory_consent and provider is not None:
        memory_status = _curate_previous(factory, user.id, conversation.id, provider, settings)
    # ...and the event that lets the agent reflect on it, if there is evidence to reflect on.
    if provider is not None:
        background.add_task(
            _reflect_previous, factory, user.id, conversation.id, provider, settings
        )
    return ConversationOut(
        id=conversation.id,
        created_at=conversation.created_at,
        memory_status=memory_status,
        project_id=conversation.project_id,
    )


def turn_config(settings: Settings) -> TurnConfig:
    return TurnConfig(
        budgets=_budgets(settings),
        curiosity_enabled=settings.curiosity_enabled,
        curiosity_limits=CuriosityLimits(
            research_per_day=settings.research_per_day,
            research_per_conversation=settings.research_per_conversation,
            max_results=settings.research_max_results,
        ),
        assessment_max_tokens=settings.llm_curation_max_output_tokens,
        reply_max_tokens=settings.llm_max_output_tokens,
        context_char_budget=settings.llm_context_char_budget,
        tts_approved_voices=settings.tts_approved_voices,
        stt_model=settings.stt_model,
        code_autonomy_enabled=settings.code_autonomy_enabled,
        mind_enabled=settings.mind_enabled,
        review_every_turns=settings.mind_review_turns,
        web_search=settings.tavily_api_key is not None,
        google_secret=settings.secret_key,
        browse_max_pages=settings.browser_max_pages,
    )


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
) -> str:
    """Prepare curated memory before the first turn; failure leaves the source pending."""
    try:
        with factory() as session:
            owner = session.get(User, user_id)
            new = session.get(Conversation, new_conversation_id)
            if owner is None or not owner.memory_consent:
                return "disabled"
            previous = latest_uncurated_conversation(session, owner, exclude=new)
            if previous is None:
                return "ready"
            curate_conversation(
                session,
                conversation=previous,
                owner=owner,
                provider=provider,
                budgets=_budgets(settings),
                max_output_tokens=settings.llm_curation_max_output_tokens,
            )
            return "ready"
    except Exception:
        logger.exception("memory curation failed", extra={"event": "curation_failed"})
        return "failed"


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
            if not autonomy_room(session, settings):
                logger.info(
                    "background reflection deferred: autonomy budget",
                    extra={"event": "reflection_budget"},
                )
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
    # Reflection is recorded as the agent's own spending, so it obeys the autonomy budget.
    if not autonomy_room(db, settings):
        return ReflectionResult(skipped_reason="autonomy_budget").__dict__
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
    return [
        ConversationOut(id=c.id, created_at=c.created_at, project_id=c.project_id)
        for c in conversations
    ]


@router.put("/{conversation_id}/project")
def move_to_project(
    conversation_id: uuid.UUID, body: ConversationProjectIn, db: DbSession, user: CurrentUser
) -> ConversationOut:
    """Puts the conversation in a project, or takes it out (null)."""
    conversation = _own_conversation(db, user, conversation_id)
    if body.project_id is not None:
        own_project(db, user.id, body.project_id)
    conversation.project_id = body.project_id
    db.commit()
    return ConversationOut(
        id=conversation.id, created_at=conversation.created_at, project_id=conversation.project_id
    )


class ProgressStepOut(BaseModel):
    label: str
    detail: str | None = None


class ProgressOut(BaseModel):
    active: bool
    elapsed_ms: int = 0
    steps: list[ProgressStepOut] = []
    # In a voice call, the reply written so far (the phone speaks it sentence by sentence).
    draft: str | None = None


class DeedOut(BaseModel):
    at: datetime
    text: str


class VisitOut(BaseModel):
    title: str
    url: str
    at: datetime


class BenchOut(BaseModel):
    """The Bancada: what it really did in this conversation, its pages and the live sites."""

    deeds: list[DeedOut] = []
    pages: list[ArtifactOut] = []
    visits: list[VisitOut] = []


@router.get("/{conversation_id}/bench")
def bench(conversation_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BenchOut:
    conversation = _own_conversation(db, user, conversation_id)
    pages = db.scalars(
        select(Artifact)
        .where(Artifact.conversation_id == conversation.id)
        .order_by(Artifact.created_at.desc())
        .limit(12)
    ).all()
    visits = db.scalars(
        select(BrowseVisit)
        .where(BrowseVisit.conversation_id == conversation.id, BrowseVisit.ok.is_(True))
        .order_by(BrowseVisit.created_at.desc())
        .limit(12)
    ).all()
    return BenchOut(
        deeds=[
            DeedOut(at=at, text=text) for at, text in deed_record.timeline(db, conversation, user)
        ][-20:],
        pages=[artifact_out(a) for a in pages],
        visits=[VisitOut(title=v.title or v.url, url=v.url, at=v.created_at) for v in visits],
    )


@router.post("/{conversation_id}/cancel")
def cancel_turn(conversation_id: uuid.UUID, db: DbSession, user: CurrentUser) -> dict[str, bool]:
    """Parar: the turn in flight stops at its next step (a reply being written is not kept)."""
    conversation = _own_conversation(db, user, conversation_id)
    return {"cancelled": progress.cancel(conversation.id)}


@router.get("/{conversation_id}/progress")
def turn_progress(conversation_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ProgressOut:
    """What the turn in flight is doing now, for the live status in the app."""
    conversation = _own_conversation(db, user, conversation_id)
    live = progress.snapshot(conversation.id)
    return ProgressOut(**live) if live else ProgressOut(active=False)


def notify_reply(
    db: Session, user: User, conversation_id: uuid.UUID, name: str | None, text: str
) -> None:
    try:
        push.send_to_owner(
            db,
            user.id,
            title=name or "Visão",
            body=text,
            url=f"/?c={conversation_id}",
            tag=f"visao-reply-{conversation_id}",
        )
        db.commit()
    except Exception:  # noqa: BLE001 - the reply is in the chat either way
        db.rollback()
        logger.warning("reply push failed", extra={"event": "reply_push_failed"})


@router.get("/{conversation_id}/messages")
def list_messages(conversation_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[MessageOut]:
    conversation = _own_conversation(db, user, conversation_id)
    history = conversation_history(db, conversation)
    files = attachments.for_messages(db, [m.id for m in history if m.role == "user"])
    pages = artifacts.for_messages(db, [m.id for m in history if m.role == "assistant"])
    by_id = {m.id: m for m in history}
    return [
        _message_out(m, files.get(m.id), pages.get(m.id), by_id.get(m.reply_to_id)) for m in history
    ]


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: uuid.UUID,
    body: MessageIn,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: OptionalProvider,
    search: Annotated[SearchProvider, Depends(get_search_provider)],
    links: Annotated[LinkReader, Depends(get_link_reader)],
    background: BackgroundTasks,
    factory: SessionFactory,
    browser: Annotated[Browser | None, Depends(get_browser)],
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
    quoted = db.get(Message, body.reply_to_id) if body.reply_to_id else None
    if body.reply_to_id and (quoted is None or quoted.conversation_id != conversation.id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A mensagem respondida não é desta conversa"
        )
    try:
        files = attachments.pending(db, user.id, body.attachment_ids)
    except attachments.AttachmentRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    try:
        with progress.tracking(conversation.id):
            turn = run_turn(
                db,
                conversation=conversation,
                identity=identity,
                owner=user,
                text=body.content,
                provider=provider,
                search=search,
                config=turn_config(settings),
                modality=body.modality,
                links=links,
                files=files,
                browser=browser,
                reply_to_id=body.reply_to_id,
            )
        result, outcome = turn.result, turn.curiosity
    except progress.TurnCancelled as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Parado por você") from exc
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

    page = None
    if result.page is not None:
        # Written after this reply, in the background: a page takes longer than an answer.
        page = artifacts.create(
            db,
            owner=user,
            conversation=conversation,
            message_id=result.assistant_message.id,
            request=result.page,
        )
        read_pages = "\n".join(
            f'<pagina url="{r.url}">\n{r.text[:8000]}\n</pagina>' for r in turn.links if r.ok
        )
        background.add_task(
            build_in_background,
            factory,
            page.id,
            provider,
            settings,
            _budgets(settings),
            identity.chosen_name,
            read_pages,
        )

    if progress.owner_left(conversation.id):
        # The app stopped watching while this ran (phone locked, app closed): the reply also goes
        # as a notification, like a message from a friend. It answers something just asked, so
        # it is not an opening and the opening limits do not apply.
        notify_reply(
            db, user, conversation.id, identity.chosen_name, result.assistant_message.content
        )

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
        sources=[SourceOut(title=s.title, url=s.url, source=s.source) for s in outcome.sources]
        + [
            SourceOut(title=r.title, url=r.url, source="GitHub" if r.kind == "github" else "link")
            for r in turn.links
            if r.ok
        ]
        + [
            SourceOut(
                title=v.title or v.final_url or v.url, url=v.final_url or v.url, source="ao vivo"
            )
            for v in turn.browsed
            if v.ok
        ],
        user_message=_message_out(result.user_message, files, quoted=quoted),
        assistant_message=_message_out(result.assistant_message, page=page),
        usage=UsageOut(
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            latency_ms=usage.latency_ms,
        ),
    )
