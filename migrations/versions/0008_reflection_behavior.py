"""reflection and behavior: feedback, observations, state versions, lessons

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fk(cols, table, name, ondelete):
    return sa.ForeignKeyConstraint(cols, [f"{table}.id"], name=op.f(name), ondelete=ondelete)


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("last_reflected_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "message_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _fk(["message_id"], "messages", "fk_message_feedback_message_id_messages", "CASCADE"),
        _fk(["owner_user_id"], "users", "fk_message_feedback_owner_user_id_users", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_feedback")),
    )
    op.create_index(op.f("ix_message_feedback_message_id"), "message_feedback", ["message_id"])
    op.create_index(
        op.f("ix_message_feedback_owner_user_id"), "message_feedback", ["owner_user_id"]
    )
    op.create_index(op.f("ix_message_feedback_created_at"), "message_feedback", ["created_at"])

    op.create_table(
        "behavior_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _fk(["message_id"], "messages", "fk_behavior_observations_message_id_messages", "CASCADE"),
        _fk(["owner_user_id"], "users", "fk_behavior_observations_owner_user_id_users", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_behavior_observations")),
        sa.UniqueConstraint("message_id", name=op.f("uq_behavior_observations_message_id")),
    )
    op.create_index(
        op.f("ix_behavior_observations_owner_user_id"), "behavior_observations", ["owner_user_id"]
    )
    op.create_index(
        op.f("ix_behavior_observations_created_at"), "behavior_observations", ["created_at"]
    )

    op.create_table(
        "behavior_state_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("rules_version", sa.String(length=32), nullable=False),
        sa.Column("cause", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _fk(
            ["owner_user_id"], "users", "fk_behavior_state_versions_owner_user_id_users", "CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_behavior_state_versions")),
        sa.UniqueConstraint(
            "owner_user_id", "version", name=op.f("uq_behavior_state_versions_owner_user_id")
        ),
    )
    op.create_index(
        op.f("ix_behavior_state_versions_owner_user_id"),
        "behavior_state_versions",
        ["owner_user_id"],
    )

    op.create_table(
        "lessons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("lesson", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model_usage_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        _fk(["owner_user_id"], "users", "fk_lessons_owner_user_id_users", "CASCADE"),
        _fk(["model_usage_id"], "model_usage", "fk_lessons_model_usage_id_model_usage", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
    )
    op.create_index(op.f("ix_lessons_owner_user_id"), "lessons", ["owner_user_id"])
    op.create_index(op.f("ix_lessons_status"), "lessons", ["status"])

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            "CREATE TRIGGER trg_behavior_state_versions_append_only BEFORE UPDATE OR DELETE "
            "ON behavior_state_versions FOR EACH ROW EXECUTE FUNCTION reject_append_only_change()"
        )
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER trg_behavior_state_versions_no_{operation.lower()} BEFORE "
                f"{operation} ON behavior_state_versions BEGIN "
                "SELECT RAISE(ABORT, 'behavior_state_versions is append-only'); END"
            )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_behavior_state_versions_append_only "
            "ON behavior_state_versions"
        )
    elif dialect == "sqlite":
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_behavior_state_versions_no_{operation}")
    op.drop_index(op.f("ix_lessons_status"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_owner_user_id"), table_name="lessons")
    op.drop_table("lessons")
    op.drop_index(
        op.f("ix_behavior_state_versions_owner_user_id"), table_name="behavior_state_versions"
    )
    op.drop_table("behavior_state_versions")
    op.drop_index(op.f("ix_behavior_observations_created_at"), table_name="behavior_observations")
    op.drop_index(
        op.f("ix_behavior_observations_owner_user_id"), table_name="behavior_observations"
    )
    op.drop_table("behavior_observations")
    op.drop_index(op.f("ix_message_feedback_created_at"), table_name="message_feedback")
    op.drop_index(op.f("ix_message_feedback_owner_user_id"), table_name="message_feedback")
    op.drop_index(op.f("ix_message_feedback_message_id"), table_name="message_feedback")
    op.drop_table("message_feedback")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("last_reflected_at")
