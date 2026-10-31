"""identity voice: chosen_voice and append-only voice events

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_identities") as batch:
        batch.add_column(sa.Column("chosen_voice", sa.String(length=64), nullable=True))

    op.create_table(
        "identity_voice_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("previous_voice", sa.String(length=64), nullable=True),
        sa.Column("new_voice", sa.String(length=64), nullable=True),
        sa.Column("options_offered", sa.JSON(), nullable=False),
        sa.Column("rationale_summary", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["agent_identities.id"],
            name=op.f("fk_identity_voice_events_identity_id_agent_identities"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_voice_events")),
    )
    op.create_index(
        op.f("ix_identity_voice_events_identity_id"), "identity_voice_events", ["identity_id"]
    )
    op.create_index(
        op.f("ix_identity_voice_events_created_at"), "identity_voice_events", ["created_at"]
    )

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        # reject_append_only_change() was created in revision 0002.
        op.execute(
            "CREATE TRIGGER trg_identity_voice_events_append_only BEFORE UPDATE OR DELETE "
            "ON identity_voice_events FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
        )
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_identity_voice_events_no_{operation.lower()} BEFORE "
                f"{operation} ON identity_voice_events BEGIN "
                "SELECT RAISE(ABORT, 'identity_voice_events is append-only'); END"
            )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_identity_voice_events_append_only ON identity_voice_events"
        )
    elif dialect == "sqlite":
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_identity_voice_events_no_{operation}")
    op.drop_index(op.f("ix_identity_voice_events_created_at"), table_name="identity_voice_events")
    op.drop_index(op.f("ix_identity_voice_events_identity_id"), table_name="identity_voice_events")
    op.drop_table("identity_voice_events")
    with op.batch_alter_table("agent_identities") as batch:
        batch.drop_column("chosen_voice")
