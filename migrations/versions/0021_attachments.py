"""Photos and files the owner sends with a message (docs/ANEXOS.md).

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
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
        "attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    if _private_postgres():
        op.execute("ALTER TABLE visao.attachments ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.attachments TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    op.drop_table("attachments")
