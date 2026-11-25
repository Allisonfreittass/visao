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


# SQLite on the owner's machine (docs/research/execucao_local.md): the API and the worker write to
# the same file. Without WAL a reader blocks a writer, and without a busy timeout the second writer
# fails at once with "database is locked" instead of waiting its turn. Foreign keys are off by
# default in SQLite; PostgreSQL always checks them, so the local copy behaves like production.
SQLITE_PRAGMAS = (
    ("journal_mode", "WAL"),
    ("busy_timeout", "5000"),
    ("synchronous", "NORMAL"),
    ("foreign_keys", "ON"),
)


def configure_sqlite(engine: Engine) -> None:
    """Sets the pragmas on every new SQLite connection. WAL needs a file: an in-memory database
    keeps its own journal and ignores it."""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def set_pragmas(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for name, value in SQLITE_PRAGMAS:
                cursor.execute(f"PRAGMA {name}={value}")
        finally:
            cursor.close()


def build_engine(database_url: str, schema: str | None = None) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    configure_sqlite(engine)
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
