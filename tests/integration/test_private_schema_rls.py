"""In the private cloud schema every table, old or new, must have row level security."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from infrastructure.database.session import build_engine

ROOT = Path(__file__).resolve().parents[2]


def _rls(connection) -> dict[str, bool]:
    rows = connection.execute(
        text(
            "SELECT c.relname, c.relrowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'visao' AND c.relkind = 'r' AND c.relname <> 'alembic_version'"
        )
    )
    return dict(rows.all())


@pytest.mark.postgres
def test_every_private_table_has_row_level_security() -> None:
    url = os.environ.get("VISION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("VISION_TEST_DATABASE_URL not set")
    admin = build_engine(url)
    with admin.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS visao CASCADE"))
        connection.execute(text("CREATE SCHEMA visao"))
    engine = build_engine(url, "visao")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with engine.connect() as connection:
            tables = _rls(connection)
        assert {"interests", "thoughts", "self_versions", "owner_notes"} <= set(tables)
        assert [name for name, enabled in tables.items() if not enabled] == []

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0013")
        with engine.connect() as connection:
            tables = _rls(connection)
        assert not any(tables[name] for name in ("interests", "thoughts", "owner_notes"))
        assert tables["users"]  # 0011 is untouched
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS visao CASCADE"))
        admin.dispose()
