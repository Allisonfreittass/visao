import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.base import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Append-only trail of relevant actions. Never stores secrets or message content."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    outcome: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class AgentIdentity(Base):
    """Minimal operational identity. The id is the agent's stable internal UUID."""

    __tablename__ = "agent_identities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    chosen_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    genesis_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdentityVersion(Base):
    """Immutable snapshot of configuration and real components. Version 1 is the genesis record."""

    __tablename__ = "identity_versions"
    __table_args__ = (UniqueConstraint("identity_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_identities.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    genesis_version: Mapped[str] = mapped_column(String(16))
    config_hash: Mapped[str] = mapped_column(String(64))
    components: Mapped[dict[str, Any]] = mapped_column(JSON)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdentityNameEvent(Base):
    """Append-only log of naming decisions. Never updated or deleted."""

    __tablename__ = "identity_name_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_identities.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(16))
    previous_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    alternatives_considered: Mapped[list[str]] = mapped_column(JSON)
    context_summary: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[str]] = mapped_column(JSON)
    rationale_summary: Mapped[str] = mapped_column(Text)
    model_provider: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
