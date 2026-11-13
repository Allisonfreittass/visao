"""A message can answer a specific earlier one (Responder).

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("reply_to_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_messages_reply_to_id_messages",
            "messages",
            ["reply_to_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_constraint("fk_messages_reply_to_id_messages", type_="foreignkey")
        batch.drop_column("reply_to_id")
