"""Connects the owner's Google from the browser on the hosted server (docs/GOOGLE.md), on a
computer or a phone.

The owner's own "Web application" client sends Google's answer back to this server, at
`<the Visão address>/api/google/web/callback`. A sign-in lives here, in memory, for 10 minutes
and is used once: `state` (sent to Google) finds it, PKCE ties the code to it, and a cookie set
when it began must come back with the answer, so it ends in the same browser that started it.
The server runs one process; with more than one, this has to move to the database.
"""

import hashlib
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

from apps.api import google_connect as oauth

# What the browser sees: the proxy in front strips /api before the request reaches the API.
CALLBACK_PATH = "/api/google/web/callback"
COOKIE = "visao_google"
COOKIE_PATH = "/api/google/web"
FLOW_SECONDS = 600
MAX_FLOWS = 3  # per owner; a fourth start forgets the oldest


class FlowError(Exception):
    """`reason` is a short code the app turns into words (GoogleSettings.tsx)."""

    def __init__(self, reason: str, owner_id: uuid.UUID | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.owner_id = owner_id


@dataclass(frozen=True)
class Flow:
    owner_id: uuid.UUID
    client_id: str
    client_secret: str
    redirect: str
    verifier: str
    nonce_hash: str
    expires: float


_flows: dict[str, Flow] = {}  # sha256(state) -> the sign-in it began
_lock = threading.Lock()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def redirect_uri(origin: str) -> str:
    """The callback on the address the owner is using: https, or http on this machine only."""
    parts = urlsplit(origin.strip())
    local = parts.hostname in {"localhost", "127.0.0.1"}
    if (
        not parts.hostname
        or (parts.scheme != "https" and not (parts.scheme == "http" and local))
        or parts.username
        or parts.password
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise ValueError("O endereço do Visão não é válido para o login do Google.")
    return f"{parts.scheme}://{parts.netloc}{CALLBACK_PATH}"


def start(
    owner_id: uuid.UUID,
    client_id: str,
    client_secret: str,
    origin: str,
    *,
    now: float | None = None,
) -> tuple[str, str]:
    """The Google sign-in address, and the nonce that goes in this browser's cookie."""
    redirect = redirect_uri(origin)
    now = time.time() if now is None else now
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, challenge = oauth.pkce()
    flow = Flow(
        owner_id, client_id, client_secret, redirect, verifier, _hash(nonce), now + FLOW_SECONDS
    )
    with _lock:
        for key in [k for k, f in _flows.items() if f.expires <= now]:
            del _flows[key]
        mine = sorted((f.expires, k) for k, f in _flows.items() if f.owner_id == owner_id)
        for _, key in mine[: max(0, len(mine) - MAX_FLOWS + 1)]:
            del _flows[key]
        _flows[_hash(state)] = flow
    return oauth.auth_url(client_id, redirect, challenge, state), nonce


def take(state: str, nonce: str | None, *, now: float | None = None) -> Flow:
    """The sign-in this answer belongs to, removed at the first try whatever happens next."""
    now = time.time() if now is None else now
    with _lock:
        flow = _flows.pop(_hash(state), None) if state else None
    if flow is None or flow.expires <= now:
        raise FlowError("vencido", flow.owner_id if flow else None)
    if not nonce or not secrets.compare_digest(_hash(nonce), flow.nonce_hash):
        raise FlowError("navegador", flow.owner_id)
    return flow


def forget_all() -> None:
    """For tests."""
    with _lock:
        _flows.clear()
