"""The id the app gives each message it sends, so the same message sent twice runs one turn
(docs/research/comparativo_agentes.md, F2).

Revision ID: 0036
Revises: 0035
"""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("client_message_id", sa.Uuid(), nullable=True))
        batch.create_index(
            "uq_messages_conversation_client_id",
            ["conversation_id", "client_message_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_index("uq_messages_conversation_client_id")
        batch.drop_column("client_message_id")
