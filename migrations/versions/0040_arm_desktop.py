"""The Visão at the owner's mouse and keyboard (docs/MEXER.md): a session can be stopped.

Revision ID: 0040
Revises: 0039
"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("arm_tasks") as batch:
        batch.add_column(
            sa.Column("stop_requested", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("arm_tasks") as batch:
        batch.drop_column("stop_requested")
