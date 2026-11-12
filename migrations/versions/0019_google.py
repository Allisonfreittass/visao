"""The owner's Google connection (encrypted) and the email or events waiting for approval.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
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
        "google_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("background", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_error", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "google_actions",
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
    )
    op.create_index("ix_google_actions_owner_status", "google_actions", ["owner_user_id", "status"])
    if _private_postgres():
        for table in ("google_accounts", "google_actions"):
            op.execute(f"ALTER TABLE visao.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                "DO $$ BEGIN EXECUTE format("
                f"'CREATE POLICY backend_only ON visao.{table} TO %I "
                "USING (true) WITH CHECK (true)', current_user); END $$;"
            )


def downgrade() -> None:
    op.drop_index("ix_google_actions_owner_status", table_name="google_actions")
    op.drop_table("google_actions")
    op.drop_table("google_accounts")
