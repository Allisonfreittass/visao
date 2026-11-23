import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.deps import AppSettings, CurrentUser, DbSession
from apps.api.llm import configured_kinds
from core import llm_routing
from core.identity.genesis import get_genesis_record, get_identity
from core.identity.naming import name_history

router = APIRouter(prefix="/system", tags=["system"])


class NameHistoryEntry(BaseModel):
    name: str
    chosen_at: datetime


class GenesisRecord(BaseModel):
    genesis_version: str
    config_hash: str
    components: dict[str, Any]
    permissions: dict[str, Any]
    created_at: datetime


class IdentityStatus(BaseModel):
    internal_id: uuid.UUID
    # None until the agent itself chooses a name; may stay None indefinitely.
    chosen_name: str | None
    name_history: list[NameHistoryEntry]
    genesis: GenesisRecord


class SystemStatus(BaseModel):
    genesis_completed: bool
    identity: IdentityStatus | None


@router.get("/status")
def status(db: DbSession, _user: CurrentUser) -> SystemStatus:
    identity = get_identity(db)
    if identity is None:
        return SystemStatus(genesis_completed=False, identity=None)
    record = get_genesis_record(db, identity)
    return SystemStatus(
        genesis_completed=True,
        identity=IdentityStatus(
            internal_id=identity.id,
            chosen_name=identity.chosen_name,
            name_history=[
                NameHistoryEntry(name=event.new_name, chosen_at=event.created_at)
                for event in name_history(db, identity)
                if event.new_name is not None
            ],
            genesis=GenesisRecord(
                genesis_version=record.genesis_version,
                config_hash=record.config_hash,
                components=record.components,
                permissions=record.permissions,
                created_at=record.created_at,
            ),
        ),
    )


class RoutingOut(BaseModel):
    mode: llm_routing.Mode
    # The configured providers, in the order of the .env (VISION_LLM_*, FALLBACK, FALLBACK2).
    configured: list[str]
    # The order each kind of task gets right now, by the mode above.
    personal: list[str]
    public: list[str]


class RoutingIn(BaseModel):
    mode: llm_routing.Mode


def _labels(kinds: list[llm_routing.Kind], indexes: list[int]) -> list[str]:
    return [llm_routing.LABELS[kinds[i]] for i in indexes]


@router.get("/llm-routing", response_model=RoutingOut)
def routing_status(user: CurrentUser, db: DbSession, settings: AppSettings) -> RoutingOut:
    """Which cloud provider goes first for each task (ADR-0022)."""
    mode = llm_routing.get_mode(db)
    kinds = configured_kinds(settings)
    public = sorted(llm_routing.PUBLIC_PURPOSES)[0]
    return RoutingOut(
        mode=mode,
        configured=_labels(kinds, list(range(len(kinds)))),
        personal=_labels(kinds, llm_routing.order(kinds, None, mode)),
        public=_labels(kinds, llm_routing.order(kinds, public, mode)),
    )


@router.put("/llm-routing", response_model=RoutingOut)
def routing_switch(
    body: RoutingIn, user: CurrentUser, db: DbSession, settings: AppSettings
) -> RoutingOut:
    llm_routing.set_mode(db, body.mode, actor_user_id=user.id, via="ajustes")
    db.commit()
    return routing_status(user, db, settings)
