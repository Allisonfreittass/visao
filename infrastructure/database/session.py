from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.settings import get_settings


def configure_schema(engine: Engine, schema: str | None) -> None:
    if schema is None:
        return
    if engine.dialect.name != "postgresql":
        raise ValueError("A dedicated database schema requires PostgreSQL")

    @event.listens_for(engine, "connect")
    def set_schema(dbapi_connection, _record) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.set_config('search_path', %s, false)", (schema,))
        dbapi_connection.commit()


def build_engine(database_url: str, schema: str | None = None) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    configure_schema(engine, schema)
    return engine


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return build_engine(settings.database_url, settings.database_schema)


def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def ping(session: Session) -> None:
    session.execute(text("SELECT 1"))
