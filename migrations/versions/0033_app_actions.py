"""What it does in the app from the conversation (docs/decisions/0021): notes in a project, a
page that belongs to a project, and an action waiting for the owner's yes.

Revision ID: 0033
Revises: 0032
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def _private_postgres() -> bool:
    connection = op.get_bind()
    return (
        connection.dialect.name == "postgresql"
        and connection.exec_driver_sql("SELECT current_schema()").scalar_one() == "visao"
    )


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("notes", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("notes_updated_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("artifacts") as batch:
        batch.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_artifacts_project_id", "projects", ["project_id"], ["id"], ondelete="SET NULL"
        )
    op.create_table(
        "pending_actions",
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
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(300), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    if _private_postgres():
        op.execute("ALTER TABLE visao.pending_actions ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.pending_actions TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    op.drop_table("pending_actions")
    with op.batch_alter_table("artifacts") as batch:
        batch.drop_constraint("fk_artifacts_project_id", type_="foreignkey")
        batch.drop_column("project_id")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("notes_updated_at")
        batch.drop_column("notes")
