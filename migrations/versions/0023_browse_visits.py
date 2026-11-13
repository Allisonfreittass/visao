"""Pages it opened in a real browser for the owner (docs/NAVEGADOR.md).

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
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
        "browse_visits",
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
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("failure", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    if _private_postgres():
        op.execute("ALTER TABLE visao.browse_visits ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.browse_visits TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    op.drop_table("browse_visits")
