"""The owner's Google (docs/GOOGLE.md): connect from the computer, see the state, disconnect,
and approve or reject the email and events it prepared.

On the owner's own machine (the Mac app, `visao iniciar`) there is a button: the server, which runs
right there, opens Google's sign-in in the browser, and Google comes back to it at
http://127.0.0.1:<port>/google/callback, the loopback address a "Desktop app" client allows. On the
hosted server the button is "Conectar" instead: the owner types the ID and the secret of their
own "Web application" client once, and Google comes back to this server at
/api/google/web/callback (apps/api/google_web.py). The terminal command still connects too.
"""

import html
import secrets
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from apps.api import google_connect as oauth
from apps.api import google_web as web
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
    # The "Conectar com o Google" button works here (a request from this very machine), and
    # whether the client is already configured (VISION_GOOGLE_CLIENT_*) or its file is needed.
    connect_here: bool = False
    client_ready: bool = False
    # Connected, but the kept connection no longer opens (the server key changed).
    reconnect: bool = False


class StartIn(BaseModel):
    # The downloaded JSON of a Google "Desktop app" client; not needed when the server has one.
    client: dict | None = None


class StartOut(BaseModel):
    url: str
    opened: bool


class WebStartIn(BaseModel):
    """The page's own address (Google comes back to it) and the owner's "Web application"
    client. The secret is kept only encrypted with the connection and never sent back."""

    origin: str = Field(min_length=8, max_length=300)
    client_id: str = Field(min_length=10, max_length=300)
    client_secret: str = Field(min_length=6, max_length=300)


class WebStartOut(BaseModel):
    url: str


# A sign-in started here and not finished: kept in memory for a few minutes, by its state.
SIGN_IN_MINUTES = 10
_LOOPBACK = {"127.0.0.1", "::1"}
_PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded", "cf-connecting-ip")


@dataclass(frozen=True)
class _SignIn:
    owner_id: uuid.UUID
    client_id: str
    client_secret: str
    verifier: str
    redirect: str
    started: float


_signing_in: dict[str, _SignIn] = {}
_lock = threading.Lock()


def _on_this_machine(request: Request) -> bool:
    """The request comes from the machine the server runs on, with no proxy in between: only
    then can the server open a browser the owner will see, and Google come back to 127.0.0.1."""
    if request.client is None or request.client.host not in _LOOPBACK:
        return False
    if (request.url.hostname or "") not in {"127.0.0.1", "localhost", "::1"}:
        return False
    return not any(request.headers.get(name) for name in _PROXY_HEADERS)


def _client_from_settings(settings) -> tuple[str, str] | None:
    if settings.google_client_id and settings.google_client_secret:
        return settings.google_client_id.strip(), settings.google_client_secret.get_secret_value()
    return None


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
def read_google(
    db: DbSession, user: CurrentUser, settings: AppSettings, request: Request = None
) -> GoogleOut:
    account = accounts.get(db, user.id)
    if account is None:
        return GoogleOut(
            connected=False,
            connect_here=request is not None and _on_this_machine(request),
            client_ready=_client_from_settings(settings) is not None,
        )
    unreadable = accounts.client_for(account, settings.secret_key) is None
    return GoogleOut(
        connected=True,
        email=account.email,
        background=account.background,
        reconnect=unreadable,
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


@router.post("/start")
def start_sign_in(
    body: StartIn, request: Request, user: CurrentUser, settings: AppSettings
) -> StartOut:
    """The "Conectar com o Google" button: opens Google's sign-in in this machine's browser."""
    if not _on_this_machine(request):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "O botão só funciona no app do Mac. Aqui, conecte pelo comando do terminal.",
        )
    client = _client_from_settings(settings)
    if client is None:
        if body.client is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Falta o arquivo do cliente do Google."
            )
        try:
            client = oauth.client_from_json(body.client)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    verifier, challenge = oauth.pkce()
    state = secrets.token_urlsafe(24)
    redirect = f"{request.url.scheme}://127.0.0.1:{request.url.port or 80}/google/callback"
    now = time.monotonic()
    with _lock:
        for key in [k for k, v in _signing_in.items() if now - v.started > SIGN_IN_MINUTES * 60]:
            del _signing_in[key]
        _signing_in[state] = _SignIn(user.id, client[0], client[1], verifier, redirect, now)
    url = oauth.auth_url(client[0], redirect, challenge, state)
    return StartOut(url=url, opened=webbrowser.open(url))


def _page(title: str, text: str, ok: bool) -> HTMLResponse:
    color = "#7FD1A8" if ok else "#E8A0A0"
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>V.I.S.A.O.</title>"
        "<body style='font:16px system-ui;background:#090E10;color:#E6E9E6;padding:40px;"
        "max-width:560px'>"
        f"<h1 style='font-weight:500;font-size:22px;color:{color}'>{html.escape(title)}</h1>"
        f"<p>{html.escape(text)}</p><p>Pode fechar esta aba e voltar ao V.I.S.A.O.</p></body>",
        status_code=200 if ok else 400,
    )


@router.get("/callback", include_in_schema=False)
def sign_in_callback(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    state: str = "",
    code: str = "",
    error: str = "",
) -> HTMLResponse:
    """Where Google comes back after the sign-in the button started."""
    with _lock:
        pending = _signing_in.pop(state, None)
    if pending is None or time.monotonic() - pending.started > SIGN_IN_MINUTES * 60:
        return _page("Não deu", "Esse login expirou ou não começou aqui. Tente de novo.", False)
    if error or not code:
        return _page("O Google não autorizou", f"Motivo: {error or 'sem código'}.", False)
    refresh, why, missing = oauth.exchange(
        code, pending.client_id, pending.client_secret, pending.redirect, pending.verifier
    )
    if not refresh:
        return _page("Não deu para conectar", why[0].upper() + why[1:] + ".", False)
    try:
        accounts.connect(
            db,
            pending.owner_id,
            Credentials(pending.client_id, pending.client_secret, refresh),
            settings.secret_key,
        )
    except GoogleError as exc:
        return _page("O Google recusou", str(exc), False)
    db.commit()
    said = "Agora eu leio seu email e sua agenda quando você pedir."
    if missing:
        said += f" Você não marcou {', '.join(missing)}; essa parte não vai funcionar."
    return _page("Google conectado", said, True)


@router.post("/web/start")
def web_start(body: WebStartIn, response: Response, user: CurrentUser) -> WebStartOut:
    """The "Conectar" button on the hosted server: the page then goes to Google in this tab."""
    client_id, client_secret = body.client_id.strip(), body.client_secret.strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "O ID do cliente termina em .apps.googleusercontent.com. Confira o que foi colado.",
        )
    try:
        url, nonce = web.start(user.id, client_id, client_secret, body.origin)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    response.set_cookie(
        web.COOKIE,
        nonce,
        max_age=web.FLOW_SECONDS,
        path=web.COOKIE_PATH,
        secure=body.origin.strip().startswith("https://"),
        httponly=True,
        samesite="lax",
    )
    return WebStartOut(url=url)


@router.get("/web/callback", include_in_schema=False)
def web_callback(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    state: str = "",
    code: str = "",
    error: str = "",
) -> RedirectResponse:
    """Where Google sends the browser back. There is no Visão login on this request: the one-time
    `state`, the cookie from /web/start and PKCE stand for it. It always ends on the app, at
    `/?google=conectado` or `/?google=erro&motivo=<code>`, which Ajustes turns into words."""
    try:
        flow = web.take(state[:200], request.cookies.get(web.COOKIE))
        if error or not code:
            raise web.FlowError("recusado", flow.owner_id)
        refresh, _why, missing = oauth.exchange(
            code[:2000], flow.client_id, flow.client_secret, flow.redirect, flow.verifier
        )
        if not refresh:
            raise web.FlowError("troca", flow.owner_id)
        try:
            accounts.connect(
                db,
                flow.owner_id,
                Credentials(flow.client_id, flow.client_secret, refresh),
                settings.secret_key,
            )
        except GoogleError as exc:
            raise web.FlowError("google", flow.owner_id) from exc
        db.commit()
        query = {"google": "conectado"} | ({"faltou": ",".join(missing)} if missing else {})
    except web.FlowError as exc:
        db.rollback()
        if exc.owner_id is not None:
            record_audit(
                db,
                "google.connect",
                "failure",
                actor_user_id=exc.owner_id,
                details={"via": "web", "reason": exc.reason},
            )
            db.commit()
        query = {"google": "erro", "motivo": exc.reason}
    answer = RedirectResponse("/?" + urlencode(query), status_code=status.HTTP_303_SEE_OTHER)
    answer.delete_cookie(web.COOKIE, path=web.COOKIE_PATH)
    answer.headers["Cache-Control"] = "no-store"
    answer.headers["Referrer-Policy"] = "no-referrer"
    return answer


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
