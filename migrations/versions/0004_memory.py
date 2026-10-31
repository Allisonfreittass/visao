"""memory: consent, candidates, decisions, records, sources, retrievals

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _guard_decisions() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        # reject_append_only_change() was created in revision 0002.
        op.execute(
            "CREATE TRIGGER trg_memory_decisions_append_only BEFORE UPDATE OR DELETE "
            "ON memory_decisions FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
        )
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_memory_decisions_no_{operation.lower()} BEFORE {operation} "
                "ON memory_decisions BEGIN SELECT RAISE(ABORT, 'memory_decisions is append-only'); END"
            )


def _unguard_decisions() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_memory_decisions_append_only ON memory_decisions")
    elif dialect == "sqlite":
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_memory_decisions_no_{operation}")


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("memory_consent", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("last_curated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "memory_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("model_usage_id", sa.Uuid(), nullable=True),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence_message_ids", sa.JSON(), nullable=False),
        sa.Column("proposed_decision", sa.String(length=16), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("flags", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("scrubbed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_memory_candidates_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_memory_candidates_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_usage_id"],
            ["model_usage.id"],
            name=op.f("fk_memory_candidates_model_usage_id_model_usage"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_candidates")),
    )
    op.create_index(
        op.f("ix_memory_candidates_owner_user_id"), "memory_candidates", ["owner_user_id"]
    )
    op.create_index(
        op.f("ix_memory_candidates_conversation_id"), "memory_candidates", ["conversation_id"]
    )

    op.create_table(
        "memory_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["memory_candidates.id"],
            name=op.f("fk_memory_decisions_candidate_id_memory_candidates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_decisions")),
    )
    op.create_index(op.f("ix_memory_decisions_candidate_id"), "memory_decisions", ["candidate_id"])

    op.create_table(
        "memory_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("source_conversation_id", sa.Uuid(), nullable=True),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_memory_records_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["memory_candidates.id"],
            name=op.f("fk_memory_records_candidate_id_memory_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_conversation_id"],
            ["conversations.id"],
            name=op.f("fk_memory_records_source_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_records")),
    )
    op.create_index(op.f("ix_memory_records_owner_user_id"), "memory_records", ["owner_user_id"])
    op.create_index(op.f("ix_memory_records_created_at"), "memory_records", ["created_at"])

    op.create_table(
        "memory_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["memory_records.id"],
            name=op.f("fk_memory_sources_record_id_memory_records"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_memory_sources_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_sources")),
    )
    op.create_index(op.f("ix_memory_sources_record_id"), "memory_sources", ["record_id"])
    op.create_index(op.f("ix_memory_sources_message_id"), "memory_sources", ["message_id"])

    op.create_table(
        "memory_retrievals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_memory_retrievals_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["memory_records.id"],
            name=op.f("fk_memory_retrievals_record_id_memory_records"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_retrievals")),
    )
    op.create_index(op.f("ix_memory_retrievals_message_id"), "memory_retrievals", ["message_id"])
    op.create_index(op.f("ix_memory_retrievals_record_id"), "memory_retrievals", ["record_id"])

    _guard_decisions()


def downgrade() -> None:
    _unguard_decisions()
    op.drop_index(op.f("ix_memory_retrievals_record_id"), table_name="memory_retrievals")
    op.drop_index(op.f("ix_memory_retrievals_message_id"), table_name="memory_retrievals")
    op.drop_table("memory_retrievals")
    op.drop_index(op.f("ix_memory_sources_message_id"), table_name="memory_sources")
    op.drop_index(op.f("ix_memory_sources_record_id"), table_name="memory_sources")
    op.drop_table("memory_sources")
    op.drop_index(op.f("ix_memory_records_created_at"), table_name="memory_records")
    op.drop_index(op.f("ix_memory_records_owner_user_id"), table_name="memory_records")
    op.drop_table("memory_records")
    op.drop_index(op.f("ix_memory_decisions_candidate_id"), table_name="memory_decisions")
    op.drop_table("memory_decisions")
    op.drop_index(op.f("ix_memory_candidates_conversation_id"), table_name="memory_candidates")
    op.drop_index(op.f("ix_memory_candidates_owner_user_id"), table_name="memory_candidates")
    op.drop_table("memory_candidates")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("last_curated_at")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("memory_consent")
