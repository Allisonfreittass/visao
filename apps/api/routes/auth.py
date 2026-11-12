import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select

from apps.api.deps import AppSettings, CurrentUser, DbSession
from apps.api.security import create_access_token, hash_password, verify_password
from infrastructure.database.audit import record_audit
from infrastructure.database.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_MAX_FAILURES = 8
LOGIN_WINDOW_SECONDS = 300
_MAX_TRACKED_KEYS = 10_000


class LoginThrottle:
    """In-process sliding window of failed logins, per client address and per email.

    The Cloudflare edge has its own limiter; this one also protects plain docker-compose
    deployments. A success clears the counters of that address and email."""

    def __init__(
        self,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_seconds: float = LOGIN_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures, self.window, self.clock = max_failures, window_seconds, clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        entries = self._failures.get(key, deque())
        while entries and entries[0] <= now - self.window:
            entries.popleft()
        if not entries:
            self._failures.pop(key, None)
        return entries

    def retry_after(self, keys: list[str]) -> int | None:
        """Seconds until a new attempt is allowed, or None when not throttled."""
        now = self.clock()
        with self._lock:
            waits = [
                entries[-self.max_failures] + self.window - now
                for entries in (self._recent(key, now) for key in keys)
                if len(entries) >= self.max_failures
            ]
        return max(1, math.ceil(max(waits))) if waits else None

    def failure(self, keys: list[str]) -> None:
        now = self.clock()
        with self._lock:
            if len(self._failures) >= _MAX_TRACKED_KEYS:
                for key in list(self._failures):
                    self._recent(key, now)
                while len(self._failures) >= _MAX_TRACKED_KEYS:
                    self._failures.pop(next(iter(self._failures)))
            for key in keys:
                entries = self._recent(key, now)
                entries.append(now)
                self._failures[key] = entries

    def success(self, keys: list[str]) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)


def _login_throttle(request: Request) -> LoginThrottle:
    # One per application instance, so separate apps (and tests) never share counters.
    throttle = getattr(request.app.state, "login_throttle", None)
    if throttle is None:
        throttle = request.app.state.login_throttle = LoginThrottle()
    return throttle


def _throttle_keys(request: Request, email: str) -> list[str]:
    # Behind Cloudflare every request reaches the container from the same peer, so the edge's
    # client address is part of the key; a forged header only splits a peer's own bucket, and
    # the per-email window still bounds guessing against any one account.
    peer = request.client.host if request.client else "unknown"
    edge = request.headers.get("CF-Connecting-IP", "")[:64]
    return [f"ip:{peer}|{edge}", f"email:{email}"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth2 token type, not a secret)
    expires_in: int


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime


@router.post("/login")
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
    settings: AppSettings,
) -> TokenResponse:
    email = form.username.strip().lower()
    throttle = _login_throttle(request)
    keys = _throttle_keys(request, email)
    wait = throttle.retry_after(keys)
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Aguarde alguns minutos.",
            headers={"Retry-After": str(wait)},
        )
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(form.password, user.password_hash if user else None)
    if not valid or user is None or not user.is_active:
        throttle.failure(keys)
        record_audit(db, "auth.login", "denied", actor_user_id=user.id if user else None)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    throttle.success(keys)
    record_audit(db, "auth.login", "success", actor_user_id=user.id)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.get("/me")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)


MIN_PASSWORD_LENGTH = 12


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class EmailChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_email: str = Field(max_length=320)


def _confirm_password(request: Request, db: DbSession, user: User, password: str) -> None:
    """Changing credentials asks for the current password, under the same throttle as login."""
    throttle = _login_throttle(request)
    keys = _throttle_keys(request, user.email)
    wait = throttle.retry_after(keys)
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Aguarde alguns minutos.",
            headers={"Retry-After": str(wait)},
        )
    if not verify_password(password, user.password_hash):
        throttle.failure(keys)
        record_audit(db, "auth.credentials", "denied", actor_user_id=user.id)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Senha atual incorreta")
    throttle.success(keys)


def _fresh_token(db: DbSession, user: User, settings: AppSettings, action: str) -> TokenResponse:
    # Every other session (phone, laptop, a leaked token) is signed out; this one continues.
    user.credentials_changed_at = datetime.now(UTC)
    record_audit(db, action, "success", actor_user_id=user.id)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/password")
def change_password(
    body: PasswordChange, request: Request, user: CurrentUser, db: DbSession, settings: AppSettings
) -> TokenResponse:
    _confirm_password(request, db, user, body.current_password)
    if len(body.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"A senha nova precisa de pelo menos {MIN_PASSWORD_LENGTH} caracteres",
        )
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A senha nova é igual à atual")
    user.password_hash = hash_password(body.new_password)
    return _fresh_token(db, user, settings, "auth.password_change")


@router.post("/email")
def change_email(
    body: EmailChange, request: Request, user: CurrentUser, db: DbSession, settings: AppSettings
) -> TokenResponse:
    _confirm_password(request, db, user, body.current_password)
    try:
        email = validate_email(body.new_email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Email inválido") from exc
    taken = db.scalar(select(User).where(User.email == email, User.id != user.id))
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esse email já está em uso")
    user.email = email
    return _fresh_token(db, user, settings, "auth.email_change")
