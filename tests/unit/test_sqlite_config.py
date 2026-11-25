"""SQLite on the owner's machine: WAL, a busy timeout and foreign keys, like PostgreSQL
(docs/research/execucao_local.md)."""

import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from infrastructure.database.session import build_engine


def test_a_file_database_gets_the_pragmas(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'visao.db'}")
    with engine.connect() as connection:
        pragma = lambda name: connection.execute(text(f"PRAGMA {name}")).scalar()  # noqa: E731
        assert pragma("journal_mode") == "wal"
        assert pragma("busy_timeout") == 5000
        assert pragma("synchronous") == 1  # NORMAL
        assert pragma("foreign_keys") == 1
    engine.dispose()


def test_a_second_writer_waits_instead_of_failing(tmp_path):
    """The API and the worker write to the same file: the second one waits for the lock."""
    url = f"sqlite:///{tmp_path / 'visao.db'}"
    first, second = build_engine(url), build_engine(url)
    with first.begin() as connection:
        connection.execute(text("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)"))

    held = threading.Event()

    def hold_the_lock():
        with first.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            connection.execute(text("INSERT INTO notes (body) VALUES ('api')"))
            held.set()
            time.sleep(0.6)
            connection.exec_driver_sql("COMMIT")

    holder = threading.Thread(target=hold_the_lock)
    holder.start()
    held.wait(2)
    started = time.monotonic()
    with second.begin() as connection:  # would raise "database is locked" without the timeout
        connection.execute(text("INSERT INTO notes (body) VALUES ('worker')"))
    waited = time.monotonic() - started
    holder.join()

    with second.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM notes")).scalar() == 2
    assert waited > 0.3
    first.dispose()
    second.dispose()


def test_foreign_keys_are_checked(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'visao.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE parents (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE children (id INTEGER PRIMARY KEY, "
                "parent_id INTEGER REFERENCES parents(id))"
            )
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO children (parent_id) VALUES (42)"))
    engine.dispose()


def test_a_supabase_url_gets_the_installed_driver():
    from apps.api.settings import Settings

    for raw in ("postgresql://u:p@db.example.supabase.co:5432/postgres", "postgres://u:p@h/db"):
        assert Settings(database_url=raw).database_url.startswith("postgresql+psycopg://")
    kept = "postgresql+psycopg://u:p@h/db"
    assert Settings(database_url=kept).database_url == kept
    assert Settings(database_url="sqlite:///./x.db").database_url == "sqlite:///./x.db"
