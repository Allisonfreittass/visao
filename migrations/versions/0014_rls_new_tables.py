"""Row level security for the tables created after the private schema was locked down (0011).

0011 enabled RLS on every table that existed then; the inner-life tables (0012) and the owner's
notes (0013) were created later without it. Same pattern, same scope: only in the dedicated
private PostgreSQL schema, a no-op anywhere else.

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

TABLES = ("interests", "thoughts", "self_versions", "owner_notes")


def _private_postgres() -> bool:
    connection = op.get_bind()
    return (
        connection.dialect.name == "postgresql"
        and connection.exec_driver_sql("SELECT current_schema()").scalar_one() == "visao"
    )


def upgrade() -> None:
    if not _private_postgres():
        return
    for table in TABLES:
        op.execute(f"ALTER TABLE visao.{table} ENABLE ROW LEVEL SECURITY")
        # As in 0011: only the backend's own role; the Supabase API roles get no policy.
        op.execute(f"""
            DO $$ BEGIN
              EXECUTE format(
                'CREATE POLICY backend_only ON visao.{table} TO %I USING (true) WITH CHECK (true)',
                current_user
              );
            END $$;
        """)


def downgrade() -> None:
    if not _private_postgres():
        return
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS backend_only ON visao.{table}")
        op.execute(f"ALTER TABLE visao.{table} DISABLE ROW LEVEL SECURITY")
