"""Defense in depth for the dedicated private Supabase schema only.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _private_postgres() -> bool:
    connection = op.get_bind()
    return (
        connection.dialect.name == "postgresql"
        and connection.exec_driver_sql("SELECT current_schema()").scalar_one() == "visao"
    )


def upgrade() -> None:
    if not _private_postgres():
        return
    # The trusted backend keeps its own JWT ownership checks. The Supabase anon and
    # authenticated API roles have no schema grants or policies for these private tables.
    op.execute("""
        DO $$ DECLARE t record; BEGIN
          FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='visao' LOOP
            EXECUTE format('ALTER TABLE visao.%I ENABLE ROW LEVEL SECURITY', t.tablename);
            EXECUTE format(
              'CREATE POLICY backend_only ON visao.%I TO %I USING (true) WITH CHECK (true)',
              t.tablename, current_user
            );
          END LOOP;
        END $$;
    """)
    op.execute("ALTER FUNCTION reject_append_only_change() SET search_path = visao")


def downgrade() -> None:
    if not _private_postgres():
        return
    op.execute("""
        DO $$ DECLARE t record; BEGIN
          FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='visao' LOOP
            EXECUTE format('DROP POLICY IF EXISTS backend_only ON visao.%I', t.tablename);
            EXECUTE format('ALTER TABLE visao.%I DISABLE ROW LEVEL SECURITY', t.tablename);
          END LOOP;
        END $$;
    """)
    op.execute("ALTER FUNCTION reject_append_only_change() RESET search_path")
