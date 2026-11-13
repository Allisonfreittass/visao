"""Pages it writes for the owner (docs/ARTEFATOS.md): their status for the app, and the page itself
at a secret link, isolated from the app."""

import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from apps.api.deps import CurrentUser, DbSession
from apps.api.settings import Settings
from core.conversation import artifacts
from core.conversation.service import Budgets
from core.initiatives import push
from infrastructure.database.models import Artifact
from integrations.llm.base import LLMProvider

router = APIRouter(tags=["artifacts"])
logger = logging.getLogger(__name__)

# The app asks about a page being written every few seconds; longer than this without asking
# means nobody is looking, so "ready" also goes as a notification.
WATCH_GRACE_SECONDS = 12.0
_last_seen: dict[uuid.UUID, float] = {}


class ArtifactOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    # Relative to the API ("/p/<token>"); the app puts its own API prefix in front.
    path: str | None = None
    error: str | None = None
    conversation_id: uuid.UUID | None = None
    created_at: datetime


def artifact_out(artifact: Artifact) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        title=artifact.title,
        status=artifact.status,
        path=f"/p/{artifact.token}" if artifact.status == "ready" else None,
        error=artifact.error,
        conversation_id=artifact.conversation_id,
        created_at=artifact.created_at,
    )


def _own(db: Session, user_id: uuid.UUID, artifact_id: uuid.UUID) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if artifact is None or artifact.owner_user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Página não encontrada")
    return artifact


@router.get("/artifacts")
def list_artifacts(db: DbSession, user: CurrentUser) -> list[ArtifactOut]:
    rows = db.scalars(
        select(Artifact)
        .where(Artifact.owner_user_id == user.id)
        .order_by(Artifact.created_at.desc())
        .limit(100)
    )
    return [artifact_out(a) for a in rows]


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ArtifactOut:
    artifact = _own(db, user.id, artifact_id)
    _last_seen[artifact.id] = time.monotonic()
    return artifact_out(artifact)


@router.delete("/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artifact(artifact_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """The link stops working at once."""
    db.delete(_own(db, user.id, artifact_id))
    db.commit()


_NOT_FOUND_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Página não encontrada</title>"
    "<p style='font:16px system-ui;margin:40px'>Esta página não existe mais.</p>"
)


@router.get("/p/{token}", include_in_schema=False)
def public_page(token: str, db: DbSession) -> Response:
    """The page, for whoever has the link. No scripts run, nothing but fonts and pictures from
    known hosts loads, and the page gets an opaque origin: it cannot read the app's session."""
    headers = {
        "Content-Security-Policy": artifacts.CONTENT_SECURITY_POLICY,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "noindex, nofollow",
        "Cache-Control": "private, no-cache",
        "Cross-Origin-Resource-Policy": "same-origin",
    }
    artifact = None
    if 16 <= len(token) <= 64:
        artifact = db.scalar(select(Artifact).where(Artifact.token == token))
    if artifact is None or artifact.status != "ready" or not artifact.html:
        return Response(_NOT_FOUND_PAGE, status_code=404, media_type="text/html", headers=headers)
    return Response(artifact.html, media_type="text/html; charset=utf-8", headers=headers)


def build_in_background(
    factory: sessionmaker[Session],
    artifact_id: uuid.UUID,
    provider: LLMProvider,
    settings: Settings,
    budgets: Budgets,
    agent_name: str | None,
    extra: str,
) -> None:
    """Background task after the reply: writes the page, then tells the owner if they left."""
    try:
        with factory() as session:
            artifact = artifacts.build(
                session,
                artifact_id,
                provider=provider,
                budgets=budgets,
                max_output_tokens=settings.artifact_max_output_tokens,
                extra=extra,
            )
            seen = _last_seen.pop(artifact.id, None)
            if artifact.status == "ready" and (
                seen is None or time.monotonic() - seen > WATCH_GRACE_SECONDS
            ):
                push.send_to_owner(
                    session,
                    artifact.owner_user_id,
                    title=agent_name or "Visão",
                    body=f"A página “{artifact.title}” está pronta.",
                    url=f"/?c={artifact.conversation_id}",
                    tag=f"visao-page-{artifact.id}",
                )
                session.commit()
    except Exception:
        logger.exception("artifact build failed", extra={"event": "artifact_failed"})
