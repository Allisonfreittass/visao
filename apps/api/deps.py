from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, sessionmaker

from apps.api.security import decode_access_token
from apps.api.settings import Settings, get_settings
from infrastructure.database.models import User
from infrastructure.database.session import get_sessionmaker


def get_session_factory() -> sessionmaker[Session]:
    """Single override point for the database, also used by background tasks."""
    return get_sessionmaker()


SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]


def get_db(factory: SessionFactory) -> Iterator[Session]:
    with factory() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: Annotated[str, Depends(_oauth2)], db: DbSession, settings: AppSettings
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token, settings)
    if user_id is None:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
