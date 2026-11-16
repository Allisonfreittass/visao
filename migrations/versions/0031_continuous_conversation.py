"""One continuous conversation per owner, its past summarized in segments (ADR-0014).

Revision ID: 0031
Revises: 0030
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def _private_postgres() -> bool:
    connection = op.get_bind()
    return (
        connection.dialect.name == "postgresql"
        and connection.exec_driver_sql("SELECT current_schema()").scalar_one() == "visao"
    )


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(
            sa.Column("continuous", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    # At most one continuous conversation per owner.
    op.create_index(
        "uq_conversations_one_continuous",
        "conversations",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("continuous"),
        postgresql_where=sa.text("continuous"),
    )
    op.create_table(
        "conversation_segments",
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
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_message_id", sa.Uuid(), nullable=False),
        sa.Column("last_message_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("messages", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversation_segments_conversation_ended",
        "conversation_segments",
        ["conversation_id", "ended_at"],
    )
    if _private_postgres():
        op.execute("ALTER TABLE visao.conversation_segments ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.conversation_segments TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    op.drop_index("ix_conversation_segments_conversation_ended", table_name="conversation_segments")
    op.drop_table("conversation_segments")
    op.drop_index("uq_conversations_one_continuous", table_name="conversations")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("continuous")
