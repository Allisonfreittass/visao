"""conversations, messages and model_usage

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["agent_identities.id"],
            name=op.f("fk_conversations_identity_id_agent_identities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"])
    op.create_index(op.f("ix_conversations_identity_id"), "conversations", ["identity_id"])

    op.create_table(
        "model_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("error_kind", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_model_usage_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_usage")),
    )
    op.create_index(op.f("ix_model_usage_conversation_id"), "model_usage", ["conversation_id"])
    op.create_index(op.f("ix_model_usage_created_at"), "model_usage", ["created_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_usage_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_usage_id"],
            ["model_usage.id"],
            name=op.f("fk_messages_model_usage_id_model_usage"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_model_usage_created_at"), table_name="model_usage")
    op.drop_index(op.f("ix_model_usage_conversation_id"), table_name="model_usage")
    op.drop_table("model_usage")
    op.drop_index(op.f("ix_conversations_identity_id"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_table("conversations")
