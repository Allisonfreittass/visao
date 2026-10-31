import uuid

import pytest
from pydantic import ValidationError

from apps.api.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from apps.api.settings import DEFAULT_SECRET_KEY, Settings


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("uma senha bem longa")
    assert hashed != "uma senha bem longa"
    assert verify_password("uma senha bem longa", hashed)
    assert not verify_password("outra senha", hashed)


def test_verify_password_without_hash_is_false() -> None:
    assert not verify_password("qualquer", None)
    assert not verify_password("timing-equalizer", None)


def test_token_roundtrip() -> None:
    settings = Settings(secret_key="k" * 40)
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id, settings), settings) == user_id


def test_token_with_wrong_key_is_rejected() -> None:
    token = create_access_token(uuid.uuid4(), Settings(secret_key="a" * 40))
    assert decode_access_token(token, Settings(secret_key="b" * 40)) is None


def test_expired_token_is_rejected() -> None:
    settings = Settings(secret_key="k" * 40, access_token_ttl_minutes=1)
    token = create_access_token(uuid.uuid4(), settings)
    import jwt

    claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    claims["exp"] = claims["iat"] - 10
    expired = jwt.encode(claims, settings.secret_key, algorithm="HS256")
    assert decode_access_token(expired, settings) is None


def test_production_refuses_default_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key=DEFAULT_SECRET_KEY)
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="short")
    Settings(environment="production", secret_key="x" * 32)
