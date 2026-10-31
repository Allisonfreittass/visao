"""curiosity and research: knowledge_gaps, research_sessions, research_sources

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_gaps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_message_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_kind", sa.String(length=32), nullable=False),
        sa.Column("depends_on", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("chosen_action", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolution_summary", sa.Text(), nullable=False),
        sa.Column("model_usage_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_knowledge_gaps_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_knowledge_gaps_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trigger_message_id"],
            ["messages.id"],
            name=op.f("fk_knowledge_gaps_trigger_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_usage_id"],
            ["model_usage.id"],
            name=op.f("fk_knowledge_gaps_model_usage_id_model_usage"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_gaps")),
    )
    op.create_index(op.f("ix_knowledge_gaps_owner_user_id"), "knowledge_gaps", ["owner_user_id"])
    op.create_index(
        op.f("ix_knowledge_gaps_conversation_id"), "knowledge_gaps", ["conversation_id"]
    )
    op.create_index(op.f("ix_knowledge_gaps_status"), "knowledge_gaps", ["status"])
    op.create_index(op.f("ix_knowledge_gaps_created_at"), "knowledge_gaps", ["created_at"])

    op.create_table(
        "research_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gap_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_kind", sa.String(length=50), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["gap_id"],
            ["knowledge_gaps.id"],
            name=op.f("fk_research_sessions_gap_id_knowledge_gaps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_research_sessions_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_sessions")),
    )
    op.create_index(op.f("ix_research_sessions_gap_id"), "research_sessions", ["gap_id"])
    op.create_index(
        op.f("ix_research_sessions_owner_user_id"), "research_sessions", ["owner_user_id"]
    )
    op.create_index(op.f("ix_research_sessions_created_at"), "research_sessions", ["created_at"])

    op.create_table(
        "research_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["research_sessions.id"],
            name=op.f("fk_research_sources_session_id_research_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_sources")),
    )
    op.create_index(op.f("ix_research_sources_session_id"), "research_sources", ["session_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_research_sources_session_id"), table_name="research_sources")
    op.drop_table("research_sources")
    op.drop_index(op.f("ix_research_sessions_created_at"), table_name="research_sessions")
    op.drop_index(op.f("ix_research_sessions_owner_user_id"), table_name="research_sessions")
    op.drop_index(op.f("ix_research_sessions_gap_id"), table_name="research_sessions")
    op.drop_table("research_sessions")
    op.drop_index(op.f("ix_knowledge_gaps_created_at"), table_name="knowledge_gaps")
    op.drop_index(op.f("ix_knowledge_gaps_status"), table_name="knowledge_gaps")
    op.drop_index(op.f("ix_knowledge_gaps_conversation_id"), table_name="knowledge_gaps")
    op.drop_index(op.f("ix_knowledge_gaps_owner_user_id"), table_name="knowledge_gaps")
    op.drop_table("knowledge_gaps")
