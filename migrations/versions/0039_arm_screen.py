"""The screen (docs/TELA.md): when the arm last offered to look, and the looks the owner asked.

Revision ID: 0039
Revises: 0038
"""

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
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
        batch.add_column(sa.Column("screen_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "arm_screen_requests",
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
        sa.Column(
            "attachment_id",
            sa.Uuid(),
            sa.ForeignKey("attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_arm_screen_requests_owner_status", "arm_screen_requests", ["owner_user_id", "status"]
    )
    if _private_postgres():
        # Like every private table (test_private_schema_rls): only the backend's role reads it.
        op.execute("ALTER TABLE visao.arm_screen_requests ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.arm_screen_requests TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    op.drop_index("ix_arm_screen_requests_owner_status", table_name="arm_screen_requests")
    op.drop_table("arm_screen_requests")
    with op.batch_alter_table("arm_devices") as batch:
        batch.drop_column("screen_seen_at")
