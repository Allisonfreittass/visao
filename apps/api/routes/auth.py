import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select

from apps.api.deps import AppSettings, CurrentUser, DbSession
from apps.api.security import create_access_token, verify_password
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
