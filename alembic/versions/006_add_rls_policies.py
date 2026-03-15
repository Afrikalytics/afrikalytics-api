"""Add Row Level Security policies for multi-tenancy.

RLS isolates tenant data at the PostgreSQL level:
- subscriptions, payments: filtered by user_id (user can only see their own rows)
- studies, insights, reports: shared content, read by all authenticated users,
  write restricted to admins (no user_id column on these tables)
- Admin bypass: super_admin can see/modify all rows regardless of policies

Revision ID: 006
Revises: 005
Create Date: 2026-03-15
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


# Tables with user_id column — true tenant isolation
TENANT_TABLES = ["subscriptions", "payments"]

# Tables without user_id — shared content, admin-only writes
SHARED_TABLES = ["studies", "insights", "reports"]


def upgrade():
    # ──────────────────────────────────────────────────────────────
    # 1. Tenant-scoped tables (have user_id): full RLS isolation
    # ──────────────────────────────────────────────────────────────
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # SELECT/UPDATE/DELETE: users can only see/modify their own rows
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            FOR ALL
            USING (user_id = current_setting('app.current_user_id')::integer)
        """)

        # INSERT: users can only insert rows for themselves
        op.execute(f"""
            CREATE POLICY {table}_tenant_insert ON {table}
            FOR INSERT
            WITH CHECK (user_id = current_setting('app.current_user_id')::integer)
        """)

        # Admin bypass: super_admin can see all rows
        op.execute(f"""
            CREATE POLICY {table}_admin_bypass ON {table}
            FOR ALL
            USING (current_setting('app.current_user_role', true) = 'super_admin')
        """)

    # ──────────────────────────────────────────────────────────────
    # 2. Shared content tables (no user_id): read-all, admin-write
    # ──────────────────────────────────────────────────────────────
    for table in SHARED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # All authenticated users can read (SELECT)
        op.execute(f"""
            CREATE POLICY {table}_read_all ON {table}
            FOR SELECT
            USING (current_setting('app.current_user_id', true) IS NOT NULL
                   AND current_setting('app.current_user_id', true) != '')
        """)

        # Only admins can INSERT
        op.execute(f"""
            CREATE POLICY {table}_admin_insert ON {table}
            FOR INSERT
            WITH CHECK (current_setting('app.current_user_role', true) IN
                        ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)

        # Only admins can UPDATE
        op.execute(f"""
            CREATE POLICY {table}_admin_update ON {table}
            FOR UPDATE
            USING (current_setting('app.current_user_role', true) IN
                   ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)

        # Only admins can DELETE
        op.execute(f"""
            CREATE POLICY {table}_admin_delete ON {table}
            FOR DELETE
            USING (current_setting('app.current_user_role', true) IN
                   ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)


def downgrade():
    # Drop policies and disable RLS on tenant-scoped tables
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_bypass ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Drop policies and disable RLS on shared content tables
    for table in SHARED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_read_all ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_delete ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
