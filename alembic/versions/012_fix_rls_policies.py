"""Fix RLS policies: add missing-ok parameter and subquery wrapper.

Fixes two issues in the original RLS policies (migration 006):
1. Tenant isolation policies used current_setting('app.current_user_id')
   without the missing-ok parameter (second arg = true), causing crashes
   when the session variable is not set.
2. All policies evaluated current_setting() per row instead of once via a
   subquery, which blocked index usage and degraded performance.

This migration drops all existing policies and recreates them with:
- current_setting('app.current_user_id', true) — returns NULL instead of error
- (SELECT ...) subquery wrapper — evaluated once, enabling index scans

Revision ID: 012
Revises: 011
Create Date: 2026-03-29
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


# Tables with user_id column — true tenant isolation
TENANT_TABLES = ["subscriptions", "payments"]

# Tables without user_id — shared content, admin-only writes
SHARED_TABLES = ["studies", "insights", "reports"]


def upgrade():
    # ──────────────────────────────────────────────────────────────
    # 1. Drop all existing policies from migration 006
    # ──────────────────────────────────────────────────────────────
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_bypass ON {table}")

    for table in SHARED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_read_all ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_delete ON {table}")

    # ──────────────────────────────────────────────────────────────
    # 2. Recreate tenant-scoped policies with fixes:
    #    - current_setting(..., true) for missing-ok
    #    - (SELECT ...) subquery for single evaluation
    # ──────────────────────────────────────────────────────────────
    for table in TENANT_TABLES:
        # SELECT/UPDATE/DELETE: users can only see/modify their own rows
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            FOR ALL
            USING (user_id = (SELECT current_setting('app.current_user_id', true)::integer))
        """)

        # INSERT: users can only insert rows for themselves
        op.execute(f"""
            CREATE POLICY {table}_tenant_insert ON {table}
            FOR INSERT
            WITH CHECK (user_id = (SELECT current_setting('app.current_user_id', true)::integer))
        """)

        # Admin bypass: super_admin can see all rows
        op.execute(f"""
            CREATE POLICY {table}_admin_bypass ON {table}
            FOR ALL
            USING ((SELECT current_setting('app.current_user_role', true)) = 'super_admin')
        """)

    # ──────────────────────────────────────────────────────────────
    # 3. Recreate shared content policies with subquery wrapper
    # ──────────────────────────────────────────────────────────────
    for table in SHARED_TABLES:
        # All authenticated users can read (SELECT)
        op.execute(f"""
            CREATE POLICY {table}_read_all ON {table}
            FOR SELECT
            USING ((SELECT current_setting('app.current_user_id', true)) IS NOT NULL
                   AND (SELECT current_setting('app.current_user_id', true)) != '')
        """)

        # Only admins can INSERT
        op.execute(f"""
            CREATE POLICY {table}_admin_insert ON {table}
            FOR INSERT
            WITH CHECK ((SELECT current_setting('app.current_user_role', true)) IN
                        ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)

        # Only admins can UPDATE
        op.execute(f"""
            CREATE POLICY {table}_admin_update ON {table}
            FOR UPDATE
            USING ((SELECT current_setting('app.current_user_role', true)) IN
                   ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)

        # Only admins can DELETE
        op.execute(f"""
            CREATE POLICY {table}_admin_delete ON {table}
            FOR DELETE
            USING ((SELECT current_setting('app.current_user_role', true)) IN
                   ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)


def downgrade():
    """Revert to original (broken) policies from migration 006."""
    # Drop fixed policies
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_bypass ON {table}")

    for table in SHARED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_read_all ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_delete ON {table}")

    # Recreate original policies (without missing-ok on tenant tables, no subquery)
    for table in TENANT_TABLES:
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            FOR ALL
            USING (user_id = current_setting('app.current_user_id')::integer)
        """)

        op.execute(f"""
            CREATE POLICY {table}_tenant_insert ON {table}
            FOR INSERT
            WITH CHECK (user_id = current_setting('app.current_user_id')::integer)
        """)

        op.execute(f"""
            CREATE POLICY {table}_admin_bypass ON {table}
            FOR ALL
            USING (current_setting('app.current_user_role', true) = 'super_admin')
        """)

    for table in SHARED_TABLES:
        op.execute(f"""
            CREATE POLICY {table}_read_all ON {table}
            FOR SELECT
            USING (current_setting('app.current_user_id', true) IS NOT NULL
                   AND current_setting('app.current_user_id', true) != '')
        """)

        op.execute(f"""
            CREATE POLICY {table}_admin_insert ON {table}
            FOR INSERT
            WITH CHECK (current_setting('app.current_user_role', true) IN
                        ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)

        op.execute(f"""
            CREATE POLICY {table}_admin_update ON {table}
            FOR UPDATE
            USING (current_setting('app.current_user_role', true) IN
                   ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)

        op.execute(f"""
            CREATE POLICY {table}_admin_delete ON {table}
            FOR DELETE
            USING (current_setting('app.current_user_role', true) IN
                   ('super_admin', 'admin_content', 'admin_studies', 'admin_insights', 'admin_reports'))
        """)
