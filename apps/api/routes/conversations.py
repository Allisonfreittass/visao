import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.browser import get_browser
from apps.api.deps import AppSettings, CurrentUser, DbSession, SessionFactory
from apps.api.limits import panel_limits
from apps.api.links import get_github, get_link_reader
from apps.api.llm import get_llm_provider, get_screen_provider, missing_llm_settings
from apps.api.routes.artifacts import ArtifactOut, artifact_out, build_in_background
from apps.api.routes.attachments import AttachmentOut, attachment_out
from apps.api.routes.projects import own_project
from apps.api.search import get_search_provider
from apps.api.settings import Settings
from apps.worker.handlers import autonomy_room
from core import brain, location, projects
from core.arm import local_llm
from core.conversation import artifacts, attachments, progress, segments, title, turn_lock
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
from infrastructure.database.models import (
    Artifact,
    BrowseVisit,
    Conversation,
    ConversationSegment,
    Message,
    ModelUsage,
    User,
)
from integrations.browser.base import Browser
from integrations.github.api import GitHubAPI
from integrations.llm.base import LLMError, LLMProvider
from integrations.search.base import SearchProvider

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)

# What the owner reads when no model answered. "http_413" told them nothing.
_PROVIDER_TROUBLE = {
    "too_large": (
        "A conversa ficou grande demais para o modelo que respondeu (o plano grátis do Groq "
        "aceita no máximo 8 mil tokens por minuto) e nenhum outro da lista conseguiu"
    ),
    "quota_exhausted": "Acabou o crédito ou a cota dos modelos configurados",
    "budget_denied": "O limite de gasto com modelos foi atingido",
    "http_429": "Os modelos estão limitando pedidos agora; tente de novo em um minuto",
    "timeout": "O modelo demorou demais para responder",
    "network": "Não consegui falar com o modelo (rede)",
}


def provider_trouble(exc: LLMError) -> str:
    # The provider's own words go to the log, where they explain a failure like a 400 for days.
    logger.warning(f"llm failed ({exc.kind}): {exc}", extra={"event": "llm_failed"})
    reason = _PROVIDER_TROUBLE.get(exc.kind)
    return f"{reason} ({exc.kind})" if reason else f"Falha no provedor de LLM ({exc.kind})"


OptionalProvider = Annotated[LLMProvider | None, Depends(get_llm_provider)]

MAX_MESSAGE_CHARS = 8000


class ConversationOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    # 3 to 6 words after the first exchange; None: show the date.
    title: str | None = None
    memory_status: str | None = None
    project_id: uuid.UUID | None = None
    # The owner's one continuous conversation (docs/CONVERSA_CONTINUA.md); the app opens it.
    continuous: bool = False


class SegmentOut(BaseModel):
    """A closed stretch of the continuous conversation, for the dividers in the chat."""

    id: uuid.UUID
    title: str
    started_at: datetime
    ended_at: datetime
    first_message_id: uuid.UUID
    last_message_id: uuid.UUID
    messages: int
    # "summarized", or "failed": then the title is empty and the app shows only the date.
    status: str


MESSAGES_PAGE_MAX = 500


def _conversation_out(c: Conversation) -> ConversationOut:
    return ConversationOut(
        id=c.id,
        created_at=c.created_at,
        project_id=c.project_id,
        title=c.title,
        continuous=c.continuous,
    )


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
    # The same text as `content` in 2 or 3 bubbles; None is one bubble (docs/decisions/0010).
    parts: list[str] | None = None
    # A table of options under a live quote (docs/COTACAO_TABELA.md). Its `text` is also the last
    # entry of `parts`: an app that does not know this field shows that text.
    quote_table: dict[str, Any] | None = None
    # The reply did something in this project: the app shows "abrir o projeto" (ADR-0021).
    project_id: uuid.UUID | None = None
    # Written by the local model on the owner's Mac (docs/MODELO_LOCAL.md): "Visão · local".
    local_model: bool = False


class LocationIn(BaseModel):
    """The phone's position, sent only when the owner turned it on and the message looks like a
    question about somewhere nearby (docs/LOCALIZACAO.md). Never stored."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    # When the phone measured it; older than 30 min is not "here".
    at: datetime | None = None

    def here(self) -> location.Here | None:
        return location.parse(self.lat, self.lon, self.accuracy_m, self.at)


class MessageIn(BaseModel):
    content: str = Field(default="", max_length=MAX_MESSAGE_CHARS)
    # "voice" when the turn came from a voice session: the reply is spoken, so kept short.
    modality: Literal["text", "voice"] = "text"
    # Tapping Responder on an earlier message of this conversation.
    reply_to_id: uuid.UUID | None = None
    # Uploaded first through POST /attachments; a photo alone is a whole message.
    attachment_ids: list[uuid.UUID] = Field(default=[], max_length=attachments.MAX_PER_MESSAGE)
    location: LocationIn | None = None
    # Made by the app once per message: sent again (a retry), it gets the turn already made.
    client_message_id: uuid.UUID | None = None

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
    message: Message,
    files: list | None = None,
    page=None,
    quoted: Message | None = None,
    local: bool = False,
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
        parts=message.parts,
        quote_table=message.quote_table,
        project_id=message.project_id,
        local_model=local,
    )


def _local_replies(db: DbSession, history: list[Message]) -> set[uuid.UUID]:
    """The replies of this page written by the local model on the Mac."""
    usage_ids = {m.model_usage_id for m in history if m.model_usage_id}
    if not usage_ids:
        return set()
    local_usage = set(
        db.scalars(
            select(ModelUsage.id).where(
                ModelUsage.id.in_(usage_ids), ModelUsage.provider == local_llm.PROVIDER_NAME
            )
        )
    )
    return {m.id for m in history if m.model_usage_id in local_usage}


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
        apps_key=(
            settings.composio_api_key.get_secret_value() if settings.composio_api_key else None
        ),
        apps_monthly_calls=settings.composio_monthly_calls,
        browse_max_pages=settings.browser_max_pages,
        panel_limits=panel_limits(settings),
    )


def _budgets(settings: Settings) -> Budgets:
    # The chat has no daily cap (llm_daily_budget_usd stays the autonomy's): a long day of talk
    # must not stop. The money ceiling is the ledger's monthly cap.
    return Budgets(
        daily_usd=None,
        conversation_usd=settings.llm_conversation_budget_usd,
        call_input_bytes=settings.llm_budget_input_tokens_per_call,
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
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, provider_trouble(exc)) from exc
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
    """The continuous conversation first, then the others, newest first."""
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.continuous.desc(), Conversation.created_at.desc())
    )
    return [_conversation_out(c) for c in conversations]


@router.get("/project/{project_id}")
def project_chat(project_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ConversationOut:
    """The project's own chat: its latest conversation, made the first time (docs/ACOES.md).
    The project page opens this instead of a new conversation each time."""
    project = own_project(db, user.id, project_id)
    try:
        found = projects.chat_for(db, user, project)
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado") from exc
    db.commit()
    return _conversation_out(found)


@router.get("/continuous")
def continuous_conversation(db: DbSession, user: CurrentUser) -> ConversationOut:
    """The owner's continuous conversation, made the first time (docs/decisions/0014)."""
    try:
        return _conversation_out(segments.continuous_for(db, user))
    except LookupError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Genesis ainda não foi executado") from None


@router.get("/{conversation_id}/segments")
def list_segments(conversation_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[SegmentOut]:
    """The closed stretches of a continuous conversation, oldest first (empty for the others)."""
    conversation = _own_conversation(db, user, conversation_id)
    rows = db.scalars(
        select(ConversationSegment)
        .where(ConversationSegment.conversation_id == conversation.id)
        .order_by(ConversationSegment.ended_at)
    )
    return [
        SegmentOut(
            id=s.id,
            title=s.title,
            started_at=s.started_at,
            ended_at=s.ended_at,
            first_message_id=s.first_message_id,
            last_message_id=s.last_message_id,
            messages=s.messages,
            status=s.status,
        )
        for s in rows
    ]


@router.put("/{conversation_id}/project")
def move_to_project(
    conversation_id: uuid.UUID, body: ConversationProjectIn, db: DbSession, user: CurrentUser
) -> ConversationOut:
    """Puts the conversation in a project, or takes it out (null)."""
    conversation = _own_conversation(db, user, conversation_id)
    if conversation.continuous and body.project_id is not None:
        # A project keeps a subject apart; the continuous conversation is everything else.
        raise HTTPException(status.HTTP_409_CONFLICT, "A conversa contínua não entra em projeto")
    if body.project_id is not None:
        own_project(db, user.id, body.project_id)
    conversation.project_id = body.project_id
    db.commit()
    return _conversation_out(conversation)


class ProgressStepOut(BaseModel):
    label: str
    detail: str | None = None
    # The tool the step uses (core/conversation/progress.py KINDS): the call's Muninn takes its
    # shape. None is the crow.
    kind: str | None = None


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


STREAM_WAIT_SECONDS = 15.0
STREAM_BEAT_SECONDS = 15.0
STREAM_TICK_SECONDS = 0.05


def sse(event: progress.Event) -> str:
    """One event in text/event-stream form; the data is one JSON line."""
    data = json.dumps(event.data, ensure_ascii=False)
    return f"id: {event.id}\nevent: {event.kind}\ndata: {data}\n\n"


@router.get("/{conversation_id}/stream")
def turn_stream(
    conversation_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """The turn in flight as server-sent events (docs/decisions/0011): its steps, the text as it is
    written, a `replace` when the kept text differs, `sources`, `action` and the closing `done`
    (the same reply the POST returns) or `error`. Waits up to 15 s for a turn to start."""
    conversation = _own_conversation(db, user, conversation_id)
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else None

    async def events():
        opened = time.monotonic()
        last = after
        beat = opened
        yield "retry: 2000\n\n"
        while True:
            if await request.is_disconnected():
                return
            batch, state = progress.follow(conversation.id, last, opened)
            for event in batch:
                last = event.id
                yield sse(event)
            now = time.monotonic()
            if state == "over" or (state == "waiting" and now - opened > STREAM_WAIT_SECONDS):
                return
            if now - beat > STREAM_BEAT_SECONDS:
                beat = now
                yield ": aqui\n\n"
            await asyncio.sleep(STREAM_TICK_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
def list_messages(
    conversation_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    before: uuid.UUID | None = None,
    limit: Annotated[int | None, Query(ge=1, le=MESSAGES_PAGE_MAX)] = None,
) -> list[MessageOut]:
    """The whole conversation, oldest first. With `limit` (and `before`, a message id), only the
    `limit` messages before that one: the continuous conversation loads backwards in pages. Without
    them, everything, as before (an app that does not page keeps working)."""
    conversation = _own_conversation(db, user, conversation_id)
    if limit is None and before is None:
        history = conversation_history(db, conversation)
    else:
        query = select(Message).where(Message.conversation_id == conversation.id)
        if before is not None:
            anchor = db.get(Message, before)
            if anchor is None or anchor.conversation_id != conversation.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada")
            query = query.where(
                or_(
                    Message.created_at < anchor.created_at,
                    and_(Message.created_at == anchor.created_at, Message.id < anchor.id),
                )
            )
        page = db.scalars(
            query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit or 100)
        )
        history = list(reversed(list(page)))
    files = attachments.for_messages(db, [m.id for m in history if m.role == "user"])
    pages = artifacts.for_messages(db, [m.id for m in history if m.role == "assistant"])
    by_id = {m.id: m for m in history}
    # A reply quoting a message outside this page still shows what it answers.
    missing = {m.reply_to_id for m in history if m.reply_to_id and m.reply_to_id not in by_id}
    if missing:
        by_id.update({m.id: m for m in db.scalars(select(Message).where(Message.id.in_(missing)))})
    local = _local_replies(db, history)
    return [
        _message_out(m, files.get(m.id), pages.get(m.id), by_id.get(m.reply_to_id), m.id in local)
        for m in history
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
    github: Annotated[GitHubAPI | None, Depends(get_github)],
    background: BackgroundTasks,
    factory: SessionFactory,
    browser: Annotated[Browser | None, Depends(get_browser)],
    screen_provider: Annotated[LLMProvider | None, Depends(get_screen_provider)],
) -> TurnOut:
    conversation = _own_conversation(db, user, conversation_id)
    command = None if body.attachment_ids else brain.parse_command(body.content)
    if command is not None:
        return _switch_brain(db, user, conversation, body.content, command)
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
        with turn_lock.held(db, conversation.id):
            if body.client_message_id is not None:
                made = _turn_already_made(db, conversation, body.client_message_id)
                if made is not None:
                    return made
            with progress.tracking(conversation.id, body.modality):
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
                    github=github,
                    files=files,
                    browser=browser,
                    reply_to_id=body.reply_to_id,
                    position=body.location.here() if body.location else None,
                    client_message_id=body.client_message_id,
                    screen_provider=screen_provider,
                )
            result, outcome = turn.result, turn.curiosity
    except turn_lock.Busy as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ainda respondendo a mensagem anterior; tente de novo"
        ) from exc
    except progress.TurnCancelled as exc:
        db.rollback()
        raise _stream_error(conversation.id, status.HTTP_409_CONFLICT, "Parado por você") from exc
    except BudgetExceededError as exc:
        scope = "diário" if exc.scope == "daily" else "desta conversa"
        raise _stream_error(
            conversation.id,
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Orçamento {scope} de LLM esgotado",
        ) from exc
    except LLMError as exc:
        raise _stream_error(
            conversation.id,
            status.HTTP_502_BAD_GATEWAY,
            f"{provider_trouble(exc)}; sem resposta",
        ) from exc
    except EmptyReplyError as exc:
        raise _stream_error(
            conversation.id,
            status.HTTP_502_BAD_GATEWAY,
            "O provedor de LLM devolveu resposta vazia",
        ) from exc
    except Exception:
        progress.publish(conversation.id, "error", {"status": 500, "message": "Erro no servidor"})
        raise

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

    # After the reply, never before it: the worker writes it (a small call of its own).
    title.request(db, conversation)
    # In the continuous conversation, the worker closes and summarizes what is due (ADR-0014).
    segments.request(db, conversation, result.assistant_message.id)

    if progress.owner_left(conversation.id):
        # The app stopped watching while this ran (phone locked, app closed): the reply also goes
        # as a notification, like a message from a friend. It answers something just asked, so
        # it is not an opening and the opening limits do not apply.
        notify_reply(
            db, user, conversation.id, identity.chosen_name, result.assistant_message.content
        )

    usage = result.usage
    gap = outcome.gap
    out = TurnOut(
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
        assistant_message=_message_out(
            result.assistant_message, page=page, local=usage.provider == local_llm.PROVIDER_NAME
        ),
        usage=UsageOut(
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            latency_ms=usage.latency_ms,
        ),
    )
    # The stream ends with the same reply the POST returns (docs/decisions/0011).
    if out.sources:
        progress.publish(
            conversation.id, "sources", {"sources": [s.model_dump() for s in out.sources]}
        )
    if set(turn.plan.executed()) & WAITING_FOR_A_TAP:
        progress.publish(conversation.id, "action", {})
    progress.publish(conversation.id, "done", out.model_dump(mode="json"))
    return out


def _turn_already_made(
    db: Session, conversation: Conversation, client_message_id: uuid.UUID
) -> TurnOut | None:
    """The same message, sent again: its turn as it was stored, nothing run again. A copy left
    without a reply (the turn failed before answering) gives up its id to this new attempt."""
    asked = db.scalar(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.client_message_id == client_message_id,
        )
    )
    if asked is None:
        return None
    answer = db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.role == "assistant",
            Message.origin.in_(("turn", "fallback")),
            Message.created_at >= asked.created_at,
            Message.id != asked.id,
        )
        .order_by(Message.created_at)
        .limit(1)
    )
    if answer is None:
        asked.client_message_id = None
        db.flush()
        return None
    usage = db.get(ModelUsage, answer.model_usage_id) if answer.model_usage_id else None
    quoted = db.get(Message, asked.reply_to_id) if asked.reply_to_id else None
    return TurnOut(
        user_message=_message_out(
            asked, attachments.for_messages(db, [asked.id]).get(asked.id, []), quoted=quoted
        ),
        assistant_message=_message_out(answer),
        usage=UsageOut(
            provider=usage.provider if usage else "",
            model=usage.model if usage else "",
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            cost_usd=usage.cost_usd if usage else Decimal(0),
            latency_ms=usage.latency_ms if usage else None,
        ),
    )


def _switch_brain(
    db: DbSession, user: User, conversation: Conversation, text: str, command: brain.Command
) -> TurnOut:
    """ "usa o modelo local", "volta pro Claude": recognized in code, so it works even with the
    cloud quota gone. The order and the answer stay in the conversation like any turn."""
    before = brain.get_mode(db)
    if command.mode is not None and command.mode != before:
        brain.set_mode(db, command.mode, actor_user_id=user.id, via="chat")
    device = local_llm.available(db, user.id)
    answer = brain.reply(command, before, device.local_model if device is not None else None)
    now = datetime.now(UTC)
    asked = Message(conversation_id=conversation.id, role="user", content=text, created_at=now)
    said = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        created_at=now + timedelta(milliseconds=1),
    )
    db.add_all([asked, said])
    db.commit()
    out = TurnOut(
        user_message=_message_out(asked),
        assistant_message=_message_out(said),
        usage=UsageOut(
            provider="visao",
            model="",
            input_tokens=0,
            output_tokens=0,
            cost_usd=Decimal(0),
            latency_ms=0,
        ),
    )
    progress.publish(conversation.id, "done", out.model_dump(mode="json"))
    return out


# A turn that leaves something waiting for the owner's tap: the app refreshes its cards.
WAITING_FOR_A_TAP = {
    "mac_proposed",
    "google_proposed",
    "apps_proposed",
    "panel_offered",
    "panel_accepted",
    "panel_edited",
}


def _stream_error(conversation_id: uuid.UUID, code: int, message: str) -> HTTPException:
    """The turn failed: the stream says so and closes; the POST answers with the same error."""
    progress.publish(conversation_id, "error", {"status": code, "message": message})
    return HTTPException(code, message)
