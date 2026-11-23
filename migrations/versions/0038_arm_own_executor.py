"""Arm version 4: the arm's own code executor, steps and cost counted by the server (ADR-0023).

Revision ID: 0038
Revises: 0037
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("arm_tasks") as batch:
        batch.add_column(sa.Column("executor", sa.String(16), nullable=True))
        batch.add_column(sa.Column("steps", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("model_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("arm_tasks") as batch:
        for column in ("model_cost_usd", "steps", "executor"):
            batch.drop_column(column)
