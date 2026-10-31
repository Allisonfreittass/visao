"""decisions per turn/cycle and standing autonomy permissions

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "autonomy_permissions", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
            )
        )
    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_decisions_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_decisions_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_decisions_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decisions")),
    )
    op.create_index(op.f("ix_decisions_owner_user_id"), "decisions", ["owner_user_id"])
    op.create_index(op.f("ix_decisions_conversation_id"), "decisions", ["conversation_id"])
    op.create_index(op.f("ix_decisions_created_at"), "decisions", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_decisions_created_at"), table_name="decisions")
    op.drop_index(op.f("ix_decisions_conversation_id"), table_name="decisions")
    op.drop_index(op.f("ix_decisions_owner_user_id"), table_name="decisions")
    op.drop_table("decisions")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("autonomy_permissions")
