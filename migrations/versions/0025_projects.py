"""Projects: a subject with its conversations, pages and files (Projetos).

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
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
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch.create_index("ix_conversations_project_id", ["project_id"])
        batch.create_foreign_key(
            "fk_conversations_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if _private_postgres():
        op.execute("ALTER TABLE visao.projects ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN EXECUTE format("
            "'CREATE POLICY backend_only ON visao.projects TO %I "
            "USING (true) WITH CHECK (true)', current_user); END $$;"
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("fk_conversations_project_id_projects", type_="foreignkey")
        batch.drop_index("ix_conversations_project_id")
        batch.drop_column("project_id")
    op.drop_table("projects")
