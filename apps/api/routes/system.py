import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.deps import CurrentUser, DbSession
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
