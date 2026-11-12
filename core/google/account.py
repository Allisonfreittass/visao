"""The owner's Google connection: kept encrypted, checked when made, and easy to undo."""

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import GoogleAccount, GoogleAction
from integrations.google.client import SCOPES, Credentials, GoogleClient, GoogleError

# One client per connection, so the hour-long access token is reused between requests.
_CLIENTS: dict[str, GoogleClient] = {}


def _fernet(secret_key: str) -> Fernet:
    digest = hashlib.sha256(b"visao-google-v1:" + secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _seal(credentials: Credentials, secret_key: str) -> str:
    raw = json.dumps(credentials.__dict__).encode()
    return _fernet(secret_key).encrypt(raw).decode()


def _open(account: GoogleAccount, secret_key: str) -> Credentials | None:
    try:
        data = json.loads(_fernet(secret_key).decrypt(account.secret.encode()))
    except (InvalidToken, ValueError):
        return None  # VISION_SECRET_KEY changed: the owner reconnects
    return Credentials(**data)


def get(session: Session, owner_id: uuid.UUID) -> GoogleAccount | None:
    return session.scalar(select(GoogleAccount).where(GoogleAccount.owner_user_id == owner_id))


def client_for(account: GoogleAccount, secret_key: str) -> GoogleClient | None:
    credentials = _open(account, secret_key)
    if credentials is None:
        return None
    key = hashlib.sha256(f"{account.id}:{credentials.refresh_token}".encode()).hexdigest()
    if key not in _CLIENTS:
        _CLIENTS[key] = GoogleClient(credentials)
    return _CLIENTS[key]


def client(session: Session, owner_id: uuid.UUID, secret_key: str) -> GoogleClient | None:
    account = get(session, owner_id)
    return client_for(account, secret_key) if account is not None else None


def connect(
    session: Session,
    owner_id: uuid.UUID,
    credentials: Credentials,
    secret_key: str,
    *,
    google: GoogleClient | None = None,
) -> GoogleAccount:
    """Checks the grant works (one real call) before keeping it; replaces an older one."""
    probe = google or GoogleClient(credentials)
    email = probe.address()  # raises GoogleError when the grant is bad
    account = get(session, owner_id)
    if account is None:
        account = GoogleAccount(owner_user_id=owner_id, background=True)
        session.add(account)
    account.email = email[:320]
    account.secret = _seal(credentials, secret_key)
    account.scopes = list(SCOPES)
    account.last_error = ""
    account.created_at = datetime.now(UTC)
    record_audit(session, "google.connect", "success", actor_user_id=owner_id, details={})
    session.flush()
    return account


def disconnect(session: Session, owner_id: uuid.UUID, secret_key: str) -> bool:
    account = get(session, owner_id)
    if account is None:
        return False
    google = client_for(account, secret_key)
    if google is not None:
        google.revoke()
    for action in session.scalars(
        select(GoogleAction).where(
            GoogleAction.owner_user_id == owner_id, GoogleAction.status == "proposed"
        )
    ):
        action.status = "rejected"
        action.result = "Google desconectado."
    session.delete(account)
    record_audit(session, "google.disconnect", "success", actor_user_id=owner_id, details={})
    session.flush()
    return True


def note_failure(session: Session, account: GoogleAccount, exc: GoogleError) -> None:
    account.last_error = f"{exc.kind}: {exc}"[:200]
    session.flush()
