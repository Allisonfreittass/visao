"""Changes in the owner's other apps (through Composio) waiting for approval (ADR-0028).

The same columns as google_actions, plus the app, the tool and its version. Approved by the owner
on 2026-11-25.

Revision ID: 0042
Revises: 0041
"""

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def _private_postgres() -> bool:
    connection = op.get_bind()
    return (
        connection.dialect.name == "postgresql"
        and connection.exec_driver_sql("SELECT current_schema()").scalar_one() == "visao"
    )


def upgrade() -> None:
    op.create_table(
        "tool_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("toolkit", sa.String(60), nullable=False),
        sa.Column("tool_slug", sa.String(120), nullable=False),
        sa.Column("tool_version", sa.String(40), nullable=False),
    )
    op.create_index("ix_tool_actions_owner_status", "tool_actions", ["owner_user_id", "status"])
    if _private_postgres():
        op.execute("ALTER TABLE visao.tool_actions ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.tool_actions TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    op.drop_index("ix_tool_actions_owner_status", table_name="tool_actions")
    op.drop_table("tool_actions")
