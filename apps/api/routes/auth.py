import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select

from apps.api.deps import AppSettings, CurrentUser, DbSession
from apps.api.security import create_access_token, verify_password
from infrastructure.database.audit import record_audit
from infrastructure.database.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


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
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
    settings: AppSettings,
) -> TokenResponse:
    email = form.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(form.password, user.password_hash if user else None)
    if not valid or user is None or not user.is_active:
        record_audit(db, "auth.login", "denied", actor_user_id=user.id if user else None)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    record_audit(db, "auth.login", "success", actor_user_id=user.id)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.get("/me")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)
