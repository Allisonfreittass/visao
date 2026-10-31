"""agent identity, identity versions and name events

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables whose rows are history: the database itself rejects UPDATE and DELETE on them.
APPEND_ONLY_TABLES = ("identity_versions", "identity_name_events")


def _create_append_only_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_append_only_change() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'table % is append-only', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in APPEND_ONLY_TABLES:
            op.execute(
                f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
            )
    elif dialect == "sqlite":
        for table in APPEND_ONLY_TABLES:
            for operation in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER trg_{table}_no_{operation.lower()} BEFORE {operation} "
                    f"ON {table} BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
                )


def _drop_append_only_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for table in APPEND_ONLY_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
        op.execute("DROP FUNCTION IF EXISTS reject_append_only_change()")
    elif dialect == "sqlite":
        for table in APPEND_ONLY_TABLES:
            for operation in ("update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_{operation}")


def upgrade() -> None:
    op.create_table(
        "agent_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chosen_name", sa.String(length=64), nullable=True),
        sa.Column("genesis_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_identities")),
    )

    op.create_table(
        "identity_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("genesis_version", sa.String(length=16), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["agent_identities.id"],
            name=op.f("fk_identity_versions_identity_id_agent_identities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_versions")),
        sa.UniqueConstraint(
            "identity_id", "version", name=op.f("uq_identity_versions_identity_id")
        ),
    )
    op.create_index(op.f("ix_identity_versions_identity_id"), "identity_versions", ["identity_id"])

    op.create_table(
        "identity_name_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("previous_name", sa.String(length=64), nullable=True),
        sa.Column("new_name", sa.String(length=64), nullable=True),
        sa.Column("alternatives_considered", sa.JSON(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("rationale_summary", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["agent_identities.id"],
            name=op.f("fk_identity_name_events_identity_id_agent_identities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_name_events")),
    )
    op.create_index(
        op.f("ix_identity_name_events_identity_id"), "identity_name_events", ["identity_id"]
    )
    op.create_index(
        op.f("ix_identity_name_events_created_at"), "identity_name_events", ["created_at"]
    )

    _create_append_only_guards()


def downgrade() -> None:
    _drop_append_only_guards()
    op.drop_index(op.f("ix_identity_name_events_created_at"), table_name="identity_name_events")
    op.drop_index(op.f("ix_identity_name_events_identity_id"), table_name="identity_name_events")
    op.drop_table("identity_name_events")
    op.drop_index(op.f("ix_identity_versions_identity_id"), table_name="identity_versions")
    op.drop_table("identity_versions")
    op.drop_table("agent_identities")
