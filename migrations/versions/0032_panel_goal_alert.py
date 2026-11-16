"""When the owner was told a panel is below their goal (docs/decisions/0016).

Revision ID: 0032
Revises: 0031
"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("panels") as batch:
        batch.add_column(sa.Column("goal_alerted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("panels") as batch:
        batch.drop_column("goal_alerted_at")
