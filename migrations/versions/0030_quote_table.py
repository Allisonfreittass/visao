"""The table of options under a live quote, and what the quote assumed (docs/decisions/0015).

Revision ID: 0030
Revises: 0029
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("quote_table", sa.JSON(), nullable=True))
    with op.batch_alter_table("panel_offers") as batch:
        batch.add_column(sa.Column("assumed", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("panel_offers") as batch:
        batch.drop_column("assumed")
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("quote_table")
