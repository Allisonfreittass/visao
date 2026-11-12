"""The arm: the owner's machines and the work they run after approval (docs/BRACO.md).

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
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
        "arm_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("projects", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "arm_tasks",
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
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("arm_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("project", sa.String(64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(16), nullable=False),
        sa.Column("resume_session", sa.String(128), nullable=True),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("error", sa.String(500), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("claude_session_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_arm_tasks_owner_status", "arm_tasks", ["owner_user_id", "status"])
    if _private_postgres():
        for table in ("arm_devices", "arm_tasks"):
            op.execute(f"ALTER TABLE visao.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                "DO $$ BEGIN EXECUTE format("
                f"'CREATE POLICY backend_only ON visao.{table} TO %I "
                "USING (true) WITH CHECK (true)', current_user); END $$;"
            )


def downgrade() -> None:
    op.drop_index("ix_arm_tasks_owner_status", table_name="arm_tasks")
    op.drop_table("arm_tasks")
    op.drop_table("arm_devices")
