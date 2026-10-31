"""Migrations must reach head, match the models and roll back cleanly."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from infrastructure.database.base import Base

ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = url
    return config


def _assert_migrations_roundtrip(url: str) -> None:
    config = _alembic_config(url)
    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], f"models and migrations diverge: {diff}"

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()


def test_migrations_sqlite(tmp_path: Path) -> None:
    _assert_migrations_roundtrip(f"sqlite:///{tmp_path / 'migrations.db'}")


@pytest.mark.postgres
def test_migrations_postgres() -> None:
    url = os.environ.get("VISION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("VISION_TEST_DATABASE_URL not set")
    _assert_migrations_roundtrip(url)
