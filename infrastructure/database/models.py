import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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


class Conversation(Base):
    """A conversation belongs to exactly one user; other users can never read it."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_identities.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    """Conversation transcript. This is history, not curated memory (docs/MEMORY.md)."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    model_usage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_usage.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelUsage(Base):
    """One row per LLM call, successful or not. Source of truth for cost and budgets."""

    __tablename__ = "model_usage"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    purpose: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))
    error_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
