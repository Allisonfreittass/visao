import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import false, text

from infrastructure.database.base import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Explicit opt-in. Without it nothing from this user's conversations is curated or recalled.
    memory_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Quiet hours for notifications, local wall-clock "HH:MM" in `timezone`; equal = none.
    quiet_start: Mapped[str] = mapped_column(String(5), default="22:00", server_default="22:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="08:00", server_default="08:00")
    timezone: Mapped[str] = mapped_column(
        String(64), default="America/Sao_Paulo", server_default="America/Sao_Paulo"
    )
    # Standing permissions for autonomous actions, e.g. {"auto_research": true}. Absent = off.
    autonomy_permissions: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Set when the email or password changes: tokens issued before it stop working everywhere.
    credentials_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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
    # Voice id from integrations/tts/catalog.py, chosen by the agent; None until it decides.
    chosen_voice: Mapped[str | None] = mapped_column(String(64), nullable=True)
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


class IdentityVoiceEvent(Base):
    """Append-only log of voice decisions, mirroring IdentityNameEvent."""

    __tablename__ = "identity_voice_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_identities.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(16))
    previous_voice: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_voice: Mapped[str | None] = mapped_column(String(64), nullable=True)
    options_offered: Mapped[list[str]] = mapped_column(JSON)
    rationale_summary: Mapped[str] = mapped_column(Text)
    model_provider: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Project(Base):
    """A subject the owner keeps conversations, pages and files under (Projetos)."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    # What it noted for the owner here, from the conversation (docs/decisions/0021).
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    notes_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    # Messages created up to this instant have already gone through memory curation.
    last_curated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Reflection runs at most once per finished conversation.
    last_reflected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # 3 to 6 words written after the first exchange (core/conversation/title.py); None: the menu
    # shows the date.
    title: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # The project it belongs to; deleting the project keeps the conversation.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The owner's one continuous conversation (ADR-0014): the app opens it, and its past goes to
    # the model as segment summaries. At most one per owner (unique partial index).
    continuous: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    __table_args__ = (
        Index(
            "uq_conversations_one_continuous",
            "user_id",
            unique=True,
            sqlite_where=text("continuous"),
            postgresql_where=text("continuous"),
        ),
    )


class ConversationSegment(Base):
    """A closed stretch of the continuous conversation, summarized by the worker (ADR-0014)."""

    __tablename__ = "conversation_segments"
    __table_args__ = (
        Index("ix_conversation_segments_conversation_ended", "conversation_id", "ended_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE")
    )
    first_message_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    last_message_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    messages: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON)
    # "summarized", or "failed" (no budget, unusable answer): then title and summary are empty and
    # the segment's messages are read raw while they fit.
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    """Conversation transcript. This is history, not curated memory (docs/MEMORY.md)."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
        Index(
            "uq_messages_conversation_client_id",
            "conversation_id",
            "client_message_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE")
    )
    # Made by the app once per message it sends: the same message sent again (a retry on a bad
    # network) is answered with the turn already made, never run twice (migration 0035).
    client_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # "turn" answers a message; "initiative" was started by the agent on its own.
    origin: Mapped[str] = mapped_column(String(16), default="turn", server_default="turn")
    # The earlier message this one answers, when the owner tapped Responder on it.
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    model_usage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_usage.id", ondelete="SET NULL"), nullable=True
    )
    # A reply in 2 or 3 bubbles (core/conversation/parts.py): the same text as `content`, cut
    # where the bubbles break. None is one bubble. `content` stays whole for memory, quoting,
    # feedback and voice.
    parts: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # A table of options under a live quote (docs/decisions/0015); its text is also in content.
    quote_table: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # A reply that did something in a project points to it ("abrir o projeto", ADR-0021).
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Attachment(Base):
    """A photo or file the owner sent with a message. Transcript, not curated memory: it goes
    away with its message, and an upload never sent is dropped by its owner's next upload."""

    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Empty until the message it came with is sent.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # "image" goes to the model as a picture; "document" as the text read out of it.
    kind: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    # Loaded only when read: listing a conversation's files never pulls their bytes.
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    # For documents: what could be read out of the file (None when nothing could).
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artifact(Base):
    """A page it wrote for the owner (a trip plan, a comparison), served at a secret link with no
    scripts and an opaque origin (docs/ARTEFATOS.md)."""

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The reply that said it would make this page; the chat shows the card there.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Put in a project from the conversation, apart from where it was made (ADR-0021).
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(120))
    # The unguessable part of the link; whoever has it can open the page.
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # "pending" while it is written, then "ready" or "failed".
    status: Mapped[str] = mapped_column(String(16), default="pending")
    html: Mapped[str | None] = mapped_column(Text, nullable=True, deferred=True)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_usage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_usage.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BrowseVisit(Base):
    """A page it opened in a real browser for the owner, with what the page showed then
    (docs/NAVEGADOR.md). Kept so a page it writes later can use it, with the time it was read."""

    __tablename__ = "browse_visits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(200), default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    text: Mapped[str] = mapped_column(Text, default="", deferred=True)
    failure: Mapped[str] = mapped_column(String(200), default="")
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


class MemoryCandidate(Base):
    """Something the model proposed to store or discard. Content is scrubbed on deletion."""

    __tablename__ = "memory_candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_usage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_usage.id", ondelete="SET NULL"), nullable=True
    )
    memory_type: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    evidence_message_ids: Mapped[list[str]] = mapped_column(JSON)
    proposed_decision: Mapped[str] = mapped_column(String(16))
    scores: Mapped[dict[str, Any]] = mapped_column(JSON)
    flags: Mapped[dict[str, Any]] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text)
    scrubbed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryDecision(Base):
    """Append-only verdict on a candidate. Holds only codes, never memory content."""

    __tablename__ = "memory_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("memory_candidates.id", ondelete="RESTRICT"), index=True
    )
    decision: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(50))
    policy_version: Mapped[str] = mapped_column(String(32))
    # Plain column, no FK: deleting a memory must not require touching this append-only row.
    record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryRecord(Base):
    __tablename__ = "memory_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("memory_candidates.id", ondelete="RESTRICT")
    )
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    memory_type: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class MemorySource(Base):
    """Provenance: the messages that support a memory."""

    __tablename__ = "memory_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("memory_records.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )


class MemoryRetrieval(Base):
    """Which memories were put in the prompt for which user message, and their score."""

    __tablename__ = "memory_retrievals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("memory_records.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeGap(Base):
    """An information gap the CuriosityEngine detected, how it was scored and what was done."""

    __tablename__ = "knowledge_gaps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trigger_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    trigger_kind: Mapped[str] = mapped_column(String(32))
    depends_on: Mapped[str] = mapped_column(String(32))
    question: Mapped[str] = mapped_column(Text)
    hypothesis: Mapped[str] = mapped_column(Text)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON)
    chosen_action: Mapped[str] = mapped_column(String(32))
    decision_reason: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    resolution_summary: Mapped[str] = mapped_column(Text, default="")
    model_usage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_usage.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gap_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_gaps.id", ondelete="CASCADE"), index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    error_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class ResearchSource(Base):
    """A result as retrieved: URL, title, excerpt and when it was fetched (provenance)."""

    __tablename__ = "research_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_sessions.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScheduledJob(Base):
    """Persistent work item, deduplicated at enqueue and fenced at queue completion.

    Expired work can be retried; external/domain effects still require their own idempotency.
    """

    __tablename__ = "scheduled_jobs"
    __table_args__ = (Index("ix_scheduled_jobs_status_run_after", "status", "run_after"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    # Why this job exists, in plain words (master prompt §9: record why initiatives happen).
    reason: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Goal(Base):
    """A goal with an explicit lifecycle. A proposal grants nothing: only approval does, and only
    the permissions the goal declared."""

    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    origin: Mapped[str] = mapped_column(String(16))  # agent | user
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    success_criteria: Mapped[str] = mapped_column(Text)
    required_permissions: Mapped[list[str]] = mapped_column(JSON)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_gap_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("knowledge_gaps.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), index=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GoalEvent(Base):
    """Append-only history of every goal transition, with who caused it and why."""

    __tablename__ = "goal_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="RESTRICT"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(32))  # agent | user | policy | worker | system
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    # Created during quiet hours: held until this instant.
    deliver_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Intention(Base):
    """Something the agent decided to bring up later, at a time it chose itself."""

    __tablename__ = "intentions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    about: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING|DONE|DROPPED
    outcome: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SystemFlag(Base):
    """Operational switches, e.g. the global autonomy pause."""

    __tablename__ = "system_flags"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageFeedback(Base):
    """The interlocutor's judgement of one reply: provenance for any adaptation it causes."""

    __tablename__ = "message_feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(Integer)  # +1 / -1
    tags: Mapped[list[str]] = mapped_column(JSON)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class BehaviorObservation(Base):
    """Metrics computed in code from one assistant reply. Never the model's self-description."""

    __tablename__ = "behavior_observations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE"), unique=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    state_version: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class BehaviorStateVersion(Base):
    """Append-only versions of the adaptive communication state of one interlocutor relation.
    Reverting creates a new version; nothing is rewritten."""

    __tablename__ = "behavior_state_versions"
    __table_args__ = (UniqueConstraint("owner_user_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    rules_version: Mapped[str] = mapped_column(String(32))
    cause: Mapped[str] = mapped_column(String(32))  # baseline | feedback | lesson | revert
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lesson(Base):
    """A revisable lesson from reflection. PROVISIONAL until independent evidence repeats."""

    __tablename__ = "lessons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(32))
    observation: Mapped[str] = mapped_column(Text)
    lesson: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    model_usage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_usage.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Decision(Base):
    """What the system decided and actually executed, per turn or per autonomous cycle (§15).
    The reply is told exactly these executed actions, so it cannot claim others."""

    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    origin: Mapped[str] = mapped_column(String(16))  # turn | autonomous
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class StudyEntry(Base):
    """One bounded autonomous study round; sources are evidence, never system instructions."""

    __tablename__ = "study_entries"
    __table_args__ = (UniqueConstraint("owner_user_id", "window_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    previous_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("study_entries.id", ondelete="SET NULL"), nullable=True
    )
    window_key: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), index=True)
    topic: Mapped[str] = mapped_column(String(200), default="")
    question: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    search_query: Mapped[str] = mapped_column(String(200), default="")
    seed_refs: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outcome_reason: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Interest(Base):
    """A topic the agent cares about, with why. Fades unless something feeds it."""

    __tablename__ = "interests"
    __table_args__ = (UniqueConstraint("owner_user_id", "key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(200))
    why: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="self")
    strength: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Thought(Base):
    """One round of thinking with no message; each round continues from the previous ones."""

    __tablename__ = "thoughts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class SelfVersion(Base):
    """How the agent describes itself. Append-only: reverting adds a version."""

    __tablename__ = "self_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    content: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="self")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OwnerNote(Base):
    """One version of a permanent note about the owner; the newest for each kind is current."""

    __tablename__ = "owner_notes"
    __table_args__ = (UniqueConstraint("owner_user_id", "kind", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # profile | rules
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PushSubscription(Base):
    """A browser that agreed to receive the agent's openings with the app closed (Web Push).

    The endpoint is the push service's URL for that browser; p256dh and auth are its public
    encryption keys, so the payload is end-to-end encrypted and the push service cannot read it.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    failures: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArmDevice(Base):
    """A machine of the owner running the arm (docs/BRACO.md). Only the token's hash is kept."""

    __tablename__ = "arm_devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # What the arm says it allows (its own config decides; this is for the interface).
    projects: Mapped[list[Any]] = mapped_column(JSON, default=list)
    version: Mapped[str] = mapped_column(String(32), default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArmTask(Base):
    """Work for the arm. Runs only after the owner approves it; the agent can only propose."""

    __tablename__ = "arm_tasks"
    __table_args__ = (Index("ix_arm_tasks_owner_status", "owner_user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("arm_devices.id", ondelete="SET NULL"), nullable=True
    )
    project: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    # proposed | approved | running | done | failed | rejected | cancelled
    status: Mapped[str] = mapped_column(String(16), default="approved")
    requested_by: Mapped[str] = mapped_column(String(16), default="owner")  # owner | agent
    resume_session: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(String(500), default="")
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    claude_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OwnerQuestion(Base):
    """Something the agent wants to ask the owner: asked once, at a fitting moment, and kept with
    the answer so it never asks the same thing twice (core/mind/questions.py)."""

    __tablename__ = "owner_questions"
    __table_args__ = (Index("ix_owner_questions_owner_status", "owner_user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text)
    # waiting | asked | answered | dropped
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    asked_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    answer: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoogleAccount(Base):
    """The owner's Google connection (docs/GOOGLE.md). The OAuth client and refresh token are kept
    encrypted with a key derived from VISION_SECRET_KEY; nothing here is readable without it."""

    __tablename__ = "google_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    email: Mapped[str] = mapped_column(String(320))
    secret: Mapped[str] = mapped_column(Text)
    scopes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # Whether the mind may look at upcoming events and unread subjects on its own.
    background: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GoogleAction(Base):
    """Something to send or schedule for the owner. Only proposed: it runs when they approve."""

    __tablename__ = "google_actions"
    __table_args__ = (Index("ix_google_actions_owner_status", "owner_user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # send_email | create_event
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    # proposed | sending | done | failed | rejected | expired | unknown (core/google/actions.py)
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    result: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PanelOffer(Base):
    """An offer, after a live quote, to keep it on the home screen and check the price daily.
    Only proposed: nothing is created until the owner says yes (docs/PAINEIS.md)."""

    __tablename__ = "panel_offers"
    __table_args__ = (Index("ix_panel_offers_owner_status", "owner_user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE")
    )
    # The reply that made the offer.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(120))
    # "até R$ 6 mil": the owner's own number, read in code, never a model's guess.
    goal_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # What the quote assumed instead of asking ({"origem": "Guarulhos (GRU)…"}).
    assumed: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    # The pages read live that the quote stands on (browse_visits).
    visit_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    # proposed | accepted | rejected | superseded
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Panel(Base):
    """A live card on the home screen (docs/PAINEIS.md, ADR-0012): what to quote (`spec`), the
    last structured result (`snapshot`) and when it was checked. Approved once, checked daily."""

    __tablename__ = "panels"
    __table_args__ = (Index("ix_panels_owner_status", "owner_user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("panel_offers.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), default="travel_quote")
    title: Mapped[str] = mapped_column(String(120))
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # active | paused | error | expired
    status: Mapped[str] = mapped_column(String(16), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    # What the card says when the last check could not be done ("o site pediu verificação").
    check_note: Mapped[str] = mapped_column(String(200), default="")
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the owner was told it is below their goal; cleared when it goes back above, so the
    # urgent notice comes once each time it drops below (docs/decisions/0016).
    goal_alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PanelSnapshot(Base):
    """Every check of a panel, for the change since the last one and the history."""

    __tablename__ = "panel_snapshots"
    __table_args__ = (Index("ix_panel_snapshots_panel_checked", "panel_id", "checked_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    panel_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("panels.id", ondelete="CASCADE"))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PanelVersion(Base):
    """What a panel was before an edit in the conversation: kept, never lost."""

    __tablename__ = "panel_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    panel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("panels.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PendingAction(Base):
    """Something it was asked to do in the app that waits for the owner's yes: deleting a project
    or a panel (docs/decisions/0021)."""

    __tablename__ = "pending_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    # What it will do, in the owner's words ("apagar o projeto «Viagem para o Chile»").
    summary: Mapped[str] = mapped_column(String(300))
    # pending | done | dropped
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
