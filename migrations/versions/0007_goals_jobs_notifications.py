"""goals, goal events, scheduled jobs, notifications, system flags, quiet hours

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("quiet_start", sa.String(length=5), server_default="22:00", nullable=False)
        )
        batch.add_column(
            sa.Column("quiet_end", sa.String(length=5), server_default="08:00", nullable=False)
        )
        batch.add_column(
            sa.Column(
                "timezone",
                sa.String(length=64),
                server_default="America/Sao_Paulo",
                nullable=False,
            )
        )

    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_scheduled_jobs_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_jobs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_scheduled_jobs_idempotency_key")),
    )
    op.create_index("ix_scheduled_jobs_status_run_after", "scheduled_jobs", ["status", "run_after"])
    op.create_index(op.f("ix_scheduled_jobs_owner_user_id"), "scheduled_jobs", ["owner_user_id"])

    op.create_table(
        "goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("success_criteria", sa.Text(), nullable=False),
        sa.Column("required_permissions", sa.JSON(), nullable=False),
        sa.Column("budget", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_gap_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_goals_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_gap_id"],
            ["knowledge_gaps.id"],
            name=op.f("fk_goals_source_gap_id_knowledge_gaps"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goals")),
    )
    op.create_index(op.f("ix_goals_owner_user_id"), "goals", ["owner_user_id"])
    op.create_index(op.f("ix_goals_status"), "goals", ["status"])

    op.create_table(
        "goal_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name=op.f("fk_goal_events_goal_id_goals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goal_events")),
    )
    op.create_index(op.f("ix_goal_events_goal_id"), "goal_events", ["goal_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=True),
        sa.Column("deliver_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_notifications_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name=op.f("fk_notifications_goal_id_goals"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_owner_user_id"), "notifications", ["owner_user_id"])
    op.create_index(op.f("ix_notifications_deliver_after"), "notifications", ["deliver_after"])

    op.create_table(
        "system_flags",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_system_flags")),
    )

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        # reject_append_only_change() was created in revision 0002.
        op.execute(
            "CREATE TRIGGER trg_goal_events_append_only BEFORE UPDATE OR DELETE ON goal_events "
            "FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
        )
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_goal_events_no_{operation.lower()} BEFORE {operation} "
                "ON goal_events BEGIN SELECT RAISE(ABORT, 'goal_events is append-only'); END"
            )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_goal_events_append_only ON goal_events")
    elif dialect == "sqlite":
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_goal_events_no_{operation}")
    op.drop_table("system_flags")
    op.drop_index(op.f("ix_notifications_deliver_after"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_owner_user_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_goal_events_goal_id"), table_name="goal_events")
    op.drop_table("goal_events")
    op.drop_index(op.f("ix_goals_status"), table_name="goals")
    op.drop_index(op.f("ix_goals_owner_user_id"), table_name="goals")
    op.drop_table("goals")
    op.drop_index(op.f("ix_scheduled_jobs_owner_user_id"), table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_status_run_after", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("timezone")
        batch.drop_column("quiet_end")
        batch.drop_column("quiet_start")
