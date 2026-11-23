"""Arm version 3: what a task changed (measured on the Mac), undo, and "until the tests pass"
(docs/BRACO.md).

Revision ID: 0037
Revises: 0036
"""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("arm_tasks") as batch:
        batch.add_column(sa.Column("kind", sa.String(16), nullable=False, server_default="work"))
        batch.add_column(sa.Column("undo_of", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("until_tests", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("changed_files", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("snapshot", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("tests", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_arm_tasks_undo_of", "arm_tasks", ["undo_of"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("arm_tasks") as batch:
        batch.drop_constraint("fk_arm_tasks_undo_of", type_="foreignkey")
        for column in ("undone_at", "tests", "snapshot", "changed_files", "until_tests"):
            batch.drop_column(column)
        batch.drop_column("undo_of")
        batch.drop_column("kind")
