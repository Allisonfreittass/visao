"""Live panels on the home screen (docs/decisions/0012-paineis-vivos.md).

Revision ID: 0029
Revises: 0028
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

TABLES = ("panels", "panel_snapshots", "panel_versions")


def _private_postgres() -> bool:
    connection = op.get_bind()
    return (
        connection.dialect.name == "postgresql"
        and connection.exec_driver_sql("SELECT current_schema()").scalar_one() == "visao"
    )


def upgrade() -> None:
    op.create_table(
        "panels",
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
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "offer_id",
            sa.Uuid(),
            sa.ForeignKey("panel_offers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("check_note", sa.String(200), nullable=False),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_panels_owner_status", "panels", ["owner_user_id", "status"])
    op.create_table(
        "panel_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "panel_id", sa.Uuid(), sa.ForeignKey("panels.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_panel_snapshots_panel_checked", "panel_snapshots", ["panel_id", "checked_at"]
    )
    op.create_table(
        "panel_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "panel_id",
            sa.Uuid(),
            sa.ForeignKey("panels.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    if _private_postgres():
        for table in TABLES:
            op.execute(f"ALTER TABLE visao.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                "DO $$ BEGIN EXECUTE format("
                f"'CREATE POLICY backend_only ON visao.{table} TO %I "
                "USING (true) WITH CHECK (true)', current_user); END $$;"
            )


def downgrade() -> None:
    op.drop_table("panel_versions")
    op.drop_index("ix_panel_snapshots_panel_checked", table_name="panel_snapshots")
    op.drop_table("panel_snapshots")
    op.drop_index("ix_panels_owner_status", table_name="panels")
    op.drop_table("panels")
