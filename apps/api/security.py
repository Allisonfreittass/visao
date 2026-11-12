import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from apps.api.settings import Settings

_hasher = PasswordHasher()
_ALGORITHM = "HS256"
# Verified against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = _hasher.hash("timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> uuid.UUID | None:
    claims = decode_access_claims(token, settings)
    return claims[0] if claims else None


def decode_access_claims(token: str, settings: Settings) -> tuple[uuid.UUID, int] | None:
    """(user id, issued-at in epoch seconds), or None for any invalid token."""
    try:
        # Pinned algorithm (no "none", no key confusion) and mandatory expiry and subject.
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "sub"], "verify_exp": True, "verify_signature": True},
        )
        return uuid.UUID(claims["sub"]), int(claims.get("iat", 0))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def issued_before_change(issued_at: int, changed_at: datetime | None) -> bool:
    """A token older than the last credential change no longer counts."""
    if changed_at is None:
        return False
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=UTC)
    return issued_at < int(changed_at.timestamp())
