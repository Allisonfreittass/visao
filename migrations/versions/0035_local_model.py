"""The local model on the owner's Mac (docs/MODELO_LOCAL.md): what model the arm offers, when it
last asked for work, and the questions that wait for it.

Revision ID: 0035
Revises: 0034
"""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def _private_postgres() -> bool:
    connection = op.get_bind()
    return (
        connection.dialect.name == "postgresql"
        and connection.exec_driver_sql("SELECT current_schema()").scalar_one() == "visao"
    )


def upgrade() -> None:
    with op.batch_alter_table("arm_devices") as batch:
        batch.add_column(sa.Column("local_model", sa.String(64), nullable=True))
        batch.add_column(sa.Column("local_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "arm_llm_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("arm_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(64), nullable=False, server_default=""),
        sa.Column("result", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.String(500), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_arm_llm_calls_owner_status", "arm_llm_calls", ["owner_user_id", "status"])
    if _private_postgres():
        # Like every private table (test_private_schema_rls): only the backend's role reads it.
        op.execute("ALTER TABLE visao.arm_llm_calls ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.arm_llm_calls TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    op.drop_index("ix_arm_llm_calls_owner_status", table_name="arm_llm_calls")
    op.drop_table("arm_llm_calls")
    with op.batch_alter_table("arm_devices") as batch:
        batch.drop_column("local_seen_at")
        batch.drop_column("local_model")
