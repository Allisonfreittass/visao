"""A reply that did something in a project points to it, for the "abrir o projeto" button
(docs/ACOES.md).

Revision ID: 0034
Revises: 0033
"""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_messages_project_id", "projects", ["project_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("fk_messages_project_id", type_="foreignkey")
        batch.drop_column("project_id")
