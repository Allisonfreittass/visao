"""Migrations must reach head, match the models and roll back cleanly."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, delete, inspect, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from core.identity.genesis import run_genesis
from core.identity.naming import NamingDecision, record_naming_decision
from infrastructure.database.base import Base
from infrastructure.database.models import (
    IdentityNameEvent,
    IdentityVersion,
    MemoryCandidate,
    MemoryDecision,
    User,
)

ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = url
    return config


def _assert_identity_history_is_append_only(engine: Engine, head: str) -> None:
    with sessionmaker(bind=engine)() as session:
        result = run_genesis(session)
        assert result.genesis_record.components["schema_revision"] == head
        record_naming_decision(
            session,
            result.identity,
            NamingDecision(
                action="defer",
                context_summary="teste",
                rationale_summary="teste",
                model_provider="test-provider",
                model_version="test-model-1",
            ),
        )

        for statement in (
            update(IdentityVersion).values(config_hash="0" * 64),
            delete(IdentityVersion),
            update(IdentityNameEvent).values(rationale_summary="reescrito"),
            delete(IdentityNameEvent),
        ):
            with pytest.raises(DBAPIError):
                session.execute(statement)
                session.flush()
            session.rollback()


def _assert_memory_decisions_are_append_only(engine: Engine) -> None:
    with sessionmaker(bind=engine)() as session:
        user = User(email="migracao@exemplo.com", password_hash="!")
        session.add(user)
        session.flush()
        candidate = MemoryCandidate(
            owner_user_id=user.id,
            memory_type="semantic",
            content="teste",
            evidence_message_ids=[],
            proposed_decision="discard",
            scores={},
            flags={},
            rationale="",
        )
        session.add(candidate)
        session.flush()
        session.add(
            MemoryDecision(
                candidate_id=candidate.id,
                decision="DISCARDED",
                reason_code="model_discard",
                policy_version="test",
            )
        )
        session.commit()

        for statement in (
            update(MemoryDecision).values(reason_code="reescrito"),
            delete(MemoryDecision),
        ):
            with pytest.raises(DBAPIError):
                session.execute(statement)
                session.flush()
            session.rollback()

        # Scrubbing a candidate (privacy deletion) must stay possible.
        session.execute(update(MemoryCandidate).values(content=""))
        session.commit()


def _assert_migrations_roundtrip(url: str) -> None:
    config = _alembic_config(url)
    command.upgrade(config, "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], f"models and migrations diverge: {diff}"

    head = ScriptDirectory.from_config(config).get_current_head()
    _assert_identity_history_is_append_only(engine, head)
    _assert_memory_decisions_are_append_only(engine)

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
