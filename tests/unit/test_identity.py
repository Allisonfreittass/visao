"""Acceptance tests for genesis and naming (master prompt sections 2, 8.1 and 8.3)."""

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.identity.genesis import GENESIS_VERSION, get_identity, run_genesis
from core.identity.naming import NamingDecision, name_history, record_naming_decision
from infrastructure.database.base import Base
from infrastructure.database.models import AgentIdentity, IdentityNameEvent, IdentityVersion

# Tables genesis is allowed to write to. Any other table (memories, episodes, preferences,
# goals...) must be empty right after genesis; new tables are covered automatically.
OPERATIONAL_TABLES = {"agent_identities", "identity_versions", "audit_logs"}


def _decision(**overrides: object) -> NamingDecision:
    fields: dict[str, object] = {
        "action": "choose",
        "name": "Nome Teste",
        "alternatives_considered": ["Nome Teste", "Outro Nome"],
        "context_summary": "situação de teste",
        "sources": ["https://exemplo.com/etimologia"],
        "rationale_summary": "justificativa de teste",
        "model_provider": "test-provider",
        "model_version": "test-model-1",
    }
    fields.update(overrides)
    return NamingDecision(**fields)  # type: ignore[arg-type]


def test_genesis_starts_without_name_or_persona(db: Session) -> None:
    result = run_genesis(db)

    assert result.created
    assert result.identity.chosen_name is None
    assert result.identity.genesis_version == GENESIS_VERSION == "2.1"
    record = result.genesis_record
    assert record.version == 1
    assert len(record.config_hash) == 64
    assert record.components["llm_provider"] is None
    assert record.components["memory"] is None
    assert record.permissions["tools"] == []
    assert name_history(db, result.identity) == []


def test_genesis_creates_only_operational_records(db: Session) -> None:
    run_genesis(db)

    for table in Base.metadata.sorted_tables:
        if table.name in OPERATIONAL_TABLES:
            continue
        count = db.scalar(select(func.count()).select_from(table))
        assert count == 0, f"genesis wrote to non-operational table {table.name}"


def test_genesis_is_idempotent(db: Session) -> None:
    first = run_genesis(db)
    second = run_genesis(db)

    assert not second.created
    assert second.identity.id == first.identity.id
    assert db.scalar(select(func.count()).select_from(AgentIdentity)) == 1
    assert db.scalar(select(func.count()).select_from(IdentityVersion)) == 1


def test_get_identity_rejects_multiple_identities(db: Session) -> None:
    db.add_all(
        [
            AgentIdentity(genesis_version=GENESIS_VERSION),
            AgentIdentity(genesis_version=GENESIS_VERSION),
        ]
    )
    db.commit()
    with pytest.raises(RuntimeError):
        get_identity(db)


def test_voluntary_choice_is_audited(db: Session) -> None:
    identity = run_genesis(db).identity

    event = record_naming_decision(db, identity, _decision())

    assert identity.chosen_name == "Nome Teste"
    assert event.event_type == "CHOSEN"
    assert event.previous_name is None
    assert event.alternatives_considered == ["Nome Teste", "Outro Nome"]
    assert event.sources == ["https://exemplo.com/etimologia"]
    assert event.model_version == "test-model-1"


def test_name_change_preserves_uuid_and_history(db: Session) -> None:
    identity = run_genesis(db).identity
    original_id = identity.id

    record_naming_decision(db, identity, _decision(name="Primeiro"))
    event = record_naming_decision(db, identity, _decision(name="Segundo"))

    assert identity.id == original_id
    assert event.event_type == "CHANGED"
    assert event.previous_name == "Primeiro"
    assert [e.new_name for e in name_history(db, identity)] == ["Primeiro", "Segundo"]


def test_chosen_name_survives_restart(engine: Engine, db: Session) -> None:
    identity = run_genesis(db).identity
    record_naming_decision(db, identity, _decision(name="Persistente"))

    with sessionmaker(bind=engine)() as fresh_session:
        reloaded = get_identity(fresh_session)
        assert reloaded is not None
        assert reloaded.id == identity.id
        assert reloaded.chosen_name == "Persistente"


@pytest.mark.parametrize("action", ["defer", "decline"])
def test_defer_and_decline_keep_name_null(db: Session, action: str) -> None:
    identity = run_genesis(db).identity

    event = record_naming_decision(db, identity, _decision(action=action, name=None))

    assert identity.chosen_name is None
    assert event.event_type == {"defer": "DEFERRED", "decline": "DECLINED"}[action]
    assert name_history(db, identity) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "   "},
        {"name": "x" * 65},
        {"name": "com\ncontrole"},
        {"name": None},
        {"rationale_summary": " "},
        {"model_version": ""},
        {"action": "defer", "name": "Nome"},
    ],
)
def test_invalid_decisions_are_rejected(db: Session, overrides: dict[str, object]) -> None:
    identity = run_genesis(db).identity
    with pytest.raises(ValueError):
        record_naming_decision(db, identity, _decision(**overrides))
    db.rollback()
    assert db.scalar(select(func.count()).select_from(IdentityNameEvent)) == 0


def test_unchanged_name_is_rejected(db: Session) -> None:
    identity = run_genesis(db).identity
    record_naming_decision(db, identity, _decision(name="Igual"))
    with pytest.raises(ValueError):
        record_naming_decision(db, identity, _decision(name=" Igual "))
