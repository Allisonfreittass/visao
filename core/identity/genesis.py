"""Creation of the agent's minimal operational identity.

Genesis writes only operational records (identity row, version snapshot, audit entry). It never
creates autobiographical memories, preferences, a personal name or personality traits.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from infrastructure.database.audit import record_audit
from infrastructure.database.models import AgentIdentity, IdentityVersion

GENESIS_VERSION = "2.1"

# Capabilities the agent actually has at genesis. None means "not available"; a component is
# only filled in when it exists and works, never as a placeholder.
INITIAL_PERMISSIONS: dict[str, Any] = {
    "tools": [],
    "web_research": "disabled",
    "autonomous_initiatives": "disabled",
    "external_actions": "require_approval",
}


@dataclass(frozen=True)
class GenesisResult:
    identity: AgentIdentity
    genesis_record: IdentityVersion
    created: bool


def _package_version() -> str:
    try:
        return version("visao")
    except PackageNotFoundError:
        return "unknown"


def _schema_revision(session: Session) -> str | None:
    if not inspect(session.connection()).has_table("alembic_version"):
        return None
    return session.scalar(text("SELECT version_num FROM alembic_version"))


def current_components(session: Session) -> dict[str, Any]:
    return {
        "api_version": _package_version(),
        "schema_revision": _schema_revision(session),
        "llm_provider": None,
        "speech": None,
        "web_research": None,
        "memory": None,
    }


def config_hash(components: dict[str, Any], permissions: dict[str, Any]) -> str:
    """Hash of the normalized configuration. Contains no secrets by construction."""
    normalized = json.dumps(
        {"genesis_version": GENESIS_VERSION, "components": components, "permissions": permissions},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def get_identity(session: Session) -> AgentIdentity | None:
    identities = session.scalars(select(AgentIdentity).limit(2)).all()
    if len(identities) > 1:
        raise RuntimeError("invariant violated: more than one agent identity exists")
    return identities[0] if identities else None


def get_genesis_record(session: Session, identity: AgentIdentity) -> IdentityVersion:
    record = session.scalar(
        select(IdentityVersion).where(
            IdentityVersion.identity_id == identity.id, IdentityVersion.version == 1
        )
    )
    if record is None:
        raise RuntimeError(f"identity {identity.id} has no genesis record")
    return record


def run_genesis(session: Session, actor_user_id: uuid.UUID | None = None) -> GenesisResult:
    """Creates the identity if none exists. Idempotent: never replaces or resets an existing one."""
    existing = get_identity(session)
    if existing is not None:
        return GenesisResult(existing, get_genesis_record(session, existing), created=False)

    components = current_components(session)
    permissions = dict(INITIAL_PERMISSIONS)
    identity = AgentIdentity(chosen_name=None, genesis_version=GENESIS_VERSION)
    session.add(identity)
    session.flush()
    record = IdentityVersion(
        identity_id=identity.id,
        version=1,
        genesis_version=GENESIS_VERSION,
        config_hash=config_hash(components, permissions),
        components=components,
        permissions=permissions,
    )
    session.add(record)
    record_audit(
        session,
        "identity.genesis",
        "success",
        actor_user_id=actor_user_id,
        details={"identity_id": str(identity.id), "genesis_version": GENESIS_VERSION},
    )
    session.commit()
    return GenesisResult(identity, record, created=True)
