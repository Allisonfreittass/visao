"""The owner's Google (docs/GOOGLE.md): connect from the computer, see the state, disconnect,
and approve or reject the email and events it prepared."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.deps import AppSettings, CurrentUser, DbSession
from core.google import account as accounts
from core.google import actions
from infrastructure.database.audit import record_audit
from infrastructure.database.models import GoogleAction
from integrations.google.client import Credentials, GoogleError

router = APIRouter(prefix="/google", tags=["google"])


class ConnectIn(BaseModel):
    client_id: str = Field(min_length=10, max_length=300)
    client_secret: str = Field(min_length=6, max_length=300)
    refresh_token: str = Field(min_length=10, max_length=2000)


class ActionOut(BaseModel):
    id: uuid.UUID
    kind: str
    summary: str
    payload: dict
    status: str
    result: str
    conversation_id: uuid.UUID | None
    created_at: datetime


class GoogleOut(BaseModel):
    connected: bool
    email: str = ""
    background: bool = False
    problem: str = ""
    pending: list[ActionOut] = []


class BackgroundIn(BaseModel):
    enabled: bool


def _action(a: GoogleAction) -> ActionOut:
    return ActionOut(
        id=a.id,
        kind=a.kind,
        summary=actions.describe(a),
        payload=a.payload,
        status=a.status,
        result=a.result,
        conversation_id=a.conversation_id,
        created_at=a.created_at,
    )


@router.get("")
def read_google(db: DbSession, user: CurrentUser, settings: AppSettings) -> GoogleOut:
    account = accounts.get(db, user.id)
    if account is None:
        return GoogleOut(connected=False)
    unreadable = accounts.client_for(account, settings.secret_key) is None
    return GoogleOut(
        connected=True,
        email=account.email,
        background=account.background,
        problem="Conecte de novo: a chave do servidor mudou." if unreadable else account.last_error,
        pending=[_action(a) for a in actions.pending(db, user.id)],
    )


@router.post("/connect")
def connect(body: ConnectIn, db: DbSession, user: CurrentUser, settings: AppSettings) -> GoogleOut:
    """Called by `python -m apps.api.cli google-connect` after the owner signs in to Google."""
    credentials = Credentials(
        body.client_id.strip(), body.client_secret.strip(), body.refresh_token.strip()
    )
    try:
        accounts.connect(db, user.id, credentials, settings.secret_key)
    except GoogleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"O Google recusou: {exc}") from exc
    db.commit()
    return read_google(db, user, settings)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(db: DbSession, user: CurrentUser, settings: AppSettings) -> None:
    accounts.disconnect(db, user.id, settings.secret_key)
    db.commit()


@router.put("/background")
def set_background(
    body: BackgroundIn, db: DbSession, user: CurrentUser, settings: AppSettings
) -> GoogleOut:
    account = accounts.get(db, user.id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google não conectado")
    account.background = body.enabled
    db.commit()
    return read_google(db, user, settings)


@router.get("/actions")
def list_actions(db: DbSession, user: CurrentUser) -> list[ActionOut]:
    return [_action(a) for a in actions.pending(db, user.id)]


@router.post("/actions/{action_id}/{decision}")
def decide(
    action_id: uuid.UUID,
    decision: str,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    via: Literal["toque", "voz"] = "toque",
) -> ActionOut:
    """`via=voz`: said in a call after it read the action aloud (docs/VOICE.md); recorded."""
    try:
        if decision == "approve":
            action = actions.approve(db, user, action_id, settings.secret_key)
        elif decision == "reject":
            action = actions.reject(db, user.id, action_id)
        else:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "decisão desconhecida")
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pedido não encontrado") from exc
    record_audit(
        db,
        f"google.{decision}",
        "success",
        actor_user_id=user.id,
        details={"via": via, "kind": action.kind},
    )
    db.commit()
    return _action(action)
