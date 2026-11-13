"""Pages it writes for the owner, served at a secret link (docs/ARTEFATOS.md).

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
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
        "artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("error", sa.String(200), nullable=True),
        sa.Column(
            "model_usage_id",
            sa.Uuid(),
            sa.ForeignKey("model_usage.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
    )
    if _private_postgres():
        op.execute("ALTER TABLE visao.artifacts ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.artifacts TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    op.drop_table("artifacts")
