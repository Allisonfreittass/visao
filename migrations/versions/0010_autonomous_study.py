"""Autonomous study notebook.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("previous_entry_id", sa.Uuid(), nullable=True),
        sa.Column("window_key", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("search_query", sa.String(200), nullable=False),
        sa.Column("seed_refs", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("outcome_reason", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["previous_entry_id"], ["study_entries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "window_key"),
    )
    op.create_index("ix_study_entries_owner_user_id", "study_entries", ["owner_user_id"])
    op.create_index("ix_study_entries_status", "study_entries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_study_entries_status", table_name="study_entries")
    op.drop_index("ix_study_entries_owner_user_id", table_name="study_entries")
    op.drop_table("study_entries")
