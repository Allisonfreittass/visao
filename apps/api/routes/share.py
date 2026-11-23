"""Shared from another app on the phone (docs/COMPARTILHAR.md, ADR-0018).

The iPhone share extension has seconds and little memory, so this answers at once (202) and the
turn runs after the response: the message goes in the continuous conversation, the reply is
written like any other, and it always arrives as a notification, because whoever shared is no
longer in the app. Files go up first through POST /attachments, as in the chat.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, sessionmaker

from apps.api.browser import get_browser
from apps.api.deps import AppSettings, CurrentUser, DbSession, SessionFactory
from apps.api.links import get_link_reader
from apps.api.llm import missing_llm_settings
from apps.api.routes.artifacts import build_in_background
from apps.api.routes.conversations import (
    LocationIn,
    OptionalProvider,
    _budgets,
    notify_reply,
    turn_config,
)
from apps.api.search import get_search_provider
from apps.api.settings import Settings
from core import location
from core.conversation import (
    artifacts,
    attachments,
    progress,
    segments,
    share,
    title,
    turn_lock,
)
from core.conversation.links import LinkReader
from core.decision.pipeline import run_turn
from core.identity.genesis import get_identity
from core.initiatives import push
from infrastructure.database.models import Conversation, User
from integrations.browser.base import Browser
from integrations.llm.base import LLMProvider
from integrations.search.base import SearchProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/share", tags=["share"])

FAILED = "Não consegui responder o que você compartilhou agora. Está na conversa; tente de novo."


class ShareIn(BaseModel):
    # What the owner typed in the share sheet, if anything: it comes first and is what they want.
    note: str | None = Field(default=None, max_length=share.MAX_NOTE_CHARS)
    url: str | None = Field(default=None, max_length=2048)
    # The page title the sharing app gave, shown above the link.
    title: str | None = Field(default=None, max_length=share.MAX_TITLE_CHARS)
    # Selected text; longer text is cut to MAX_TEXT_CHARS.
    text: str | None = Field(default=None, max_length=20_000)
    attachment_ids: list[uuid.UUID] = Field(default=[], max_length=attachments.MAX_PER_MESSAGE)
    # "How do I get here?" with a screenshot: the phone's position, as in the chat.
    location: LocationIn | None = None

    @model_validator(mode="after")
    def _something(self) -> "ShareIn":
        shared = share.clean_url(self.url) or (self.text or "").strip() or self.attachment_ids
        if not shared and not (self.note or "").strip():
            raise ValueError("nada para compartilhar")
        return self


class ShareOut(BaseModel):
    conversation_id: uuid.UUID
    # The message as it went in the chat (comment, link, quoted text).
    content: str


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def share_in(
    body: ShareIn,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    provider: OptionalProvider,
    search: Annotated[SearchProvider, Depends(get_search_provider)],
    links: Annotated[LinkReader, Depends(get_link_reader)],
    browser: Annotated[Browser | None, Depends(get_browser)],
    background: BackgroundTasks,
    factory: SessionFactory,
) -> ShareOut:
    if provider is None:
        missing = ", ".join(missing_llm_settings(settings))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"LLM não configurado. Faltam: {missing}"
        )
    try:
        conversation = segments.continuous_for(db, user)
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Identidade indisponível") from exc
    try:
        attachments.pending(db, user.id, body.attachment_ids)  # checked now, used after
    except attachments.AttachmentRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    content = share.compose(note=body.note, url=body.url, title=body.title, text=body.text)
    db.commit()
    background.add_task(
        answer,
        factory,
        user.id,
        conversation.id,
        content,
        list(body.attachment_ids),
        body.location.here() if body.location else None,
        provider,
        search,
        links,
        browser,
        settings,
    )
    return ShareOut(conversation_id=conversation.id, content=content)


def answer(
    factory: sessionmaker[Session],
    owner_id: uuid.UUID,
    conversation_id: uuid.UUID,
    content: str,
    attachment_ids: list[uuid.UUID],
    position: location.Here | None,
    provider: LLMProvider,
    search: SearchProvider,
    links: LinkReader,
    browser: Browser | None,
    settings: Settings,
) -> None:
    """The turn, after the response: same pipeline as the chat, always told by a notification."""
    with factory() as db:
        owner = db.get(User, owner_id)
        conversation = db.get(Conversation, conversation_id)
        identity = get_identity(db)
        if owner is None or conversation is None or identity is None:
            return
        try:
            files = attachments.pending(db, owner.id, attachment_ids)
            with (
                turn_lock.held(db, conversation.id),
                progress.tracking(conversation.id, "text"),
            ):
                turn = run_turn(
                    db,
                    conversation=conversation,
                    identity=identity,
                    owner=owner,
                    text=content,
                    provider=provider,
                    search=search,
                    config=turn_config(settings),
                    links=links,
                    files=files,
                    browser=browser,
                    shared=True,
                    position=position,
                )
        except Exception:  # noqa: BLE001 - whoever shared is gone; tell them on the phone
            db.rollback()
            logger.warning("share turn failed", extra={"event": "share_failed"})
            try:
                push.send_to_owner(
                    db, owner.id, title="Visão", body=FAILED, url=f"/?c={conversation.id}"
                )
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            return
        result = turn.result
        result.user_message.origin = share.ORIGIN
        db.commit()
        title.request(db, conversation)
        segments.request(db, conversation, result.assistant_message.id)
        if result.page is not None:
            page = artifacts.create(
                db,
                owner=owner,
                conversation=conversation,
                message_id=result.assistant_message.id,
                request=result.page,
            )
            read_pages = "\n".join(
                f'<pagina url="{r.url}">\n{r.text[:8000]}\n</pagina>' for r in turn.links if r.ok
            )
            build_in_background(
                factory,
                page.id,
                provider,
                settings,
                _budgets(settings),
                identity.chosen_name,
                read_pages,
            )
        notify_reply(
            db, owner, conversation.id, identity.chosen_name, result.assistant_message.content
        )
