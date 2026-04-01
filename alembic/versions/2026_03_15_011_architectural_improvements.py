"""Phase 3 architectural improvements: BigInteger PKs, SSO uniqueness, StudyDataset table.

Revision ID: 011
Revises: 010
Create Date: 2026-03-15

Changes
-------

1. Migrate all primary keys from INTEGER to BIGINT for scalability (P3).
2. Migrate all foreign key columns from INTEGER to BIGINT to match.
3. Fix SSO uniqueness: replace global unique on sso_id with composite
   unique constraint (sso_provider, sso_id) so the same sso_id can exist
   across different providers (P16).
4. Create study_datasets table and migrate imported_data from studies (P4).
5. AuditLog.resource_id upgraded to BIGINT for consistency.

NOTE on BigInteger migration:
  ALTER COLUMN ... TYPE BIGINT does NOT require a table rewrite on PostgreSQL
  when going from INTEGER (4 bytes) to BIGINT (8 bytes).  PostgreSQL can do
  this in-place.  However, indexes on these columns will be rebuilt, so this
  migration should be run during a low-traffic window.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


# All tables with INTEGER primary keys that need upgrading to BIGINT.
PK_TABLES = [
    "users",
    "studies",
    "subscriptions",
    "payments",
    "insights",
    "reports",
    "blog_posts",
    "newsletter_subscribers",
    "newsletter_campaigns",
    "contacts",
    "verification_codes",
    "token_blacklist",
    "audit_logs",
    "notifications",
    "api_keys",
    "marketplace_templates",
    "sso_exchange_codes",
]

# (table_name, column_name) for all foreign key columns that reference
# BigInteger primary keys and need to be upgraded from INTEGER.
FK_COLUMNS = [
    ("users", "parent_user_id"),
    ("subscriptions", "user_id"),
    ("payments", "user_id"),
    ("payments", "subscription_id"),
    ("insights", "study_id"),
    ("reports", "study_id"),
    ("blog_posts", "author_id"),
    ("newsletter_campaigns", "blog_post_id"),
    ("verification_codes", "user_id"),
    ("token_blacklist", "user_id"),
    ("audit_logs", "user_id"),
    ("audit_logs", "resource_id"),
    ("notifications", "user_id"),
    ("api_keys", "user_id"),
    ("marketplace_templates", "author_id"),
    ("sso_exchange_codes", "user_id"),
]


def upgrade():
    # ------------------------------------------------------------------
    # 1. Migrate primary keys to BIGINT
    # ------------------------------------------------------------------
    for table in PK_TABLES:
        op.alter_column(table, "id", type_=sa.BigInteger(), existing_type=sa.Integer())

    # ------------------------------------------------------------------
    # 2. Migrate foreign key columns to BIGINT
    # ------------------------------------------------------------------
    for table, column in FK_COLUMNS:
        op.alter_column(table, column, type_=sa.BigInteger(), existing_type=sa.Integer())

    # ------------------------------------------------------------------
    # 3. Fix SSO uniqueness (P16)
    # Drop the old global unique index/constraint on sso_id if it exists,
    # then create a composite unique constraint on (sso_provider, sso_id).
    # ------------------------------------------------------------------
    # The original model had: sso_id = Column(String(255), unique=True)
    # which created a constraint named something like "users_sso_id_key" or
    # "uq_users_sso_id". We try both possible names.
    try:
        op.drop_constraint("users_sso_id_key", "users", type_="unique")
    except Exception:
        pass
    try:
        op.drop_constraint("uq_users_sso_id", "users", type_="unique")
    except Exception:
        pass
    # Also try dropping the partial index from migration 008 if it exists
    try:
        op.drop_index("ix_users_sso_provider_id", table_name="users")
    except Exception:
        pass

    op.create_unique_constraint(
        "uq_users_sso_provider_id", "users", ["sso_provider", "sso_id"]
    )

    # ------------------------------------------------------------------
    # 4. Create study_datasets table (P4)
    # ------------------------------------------------------------------
    op.create_table(
        "study_datasets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "study_id",
            sa.BigInteger(),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("columns", JSONB(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_study_datasets_study_id", "study_datasets", ["study_id"])

    # ------------------------------------------------------------------
    # 4b. Migrate existing imported_data from studies to study_datasets
    # ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO study_datasets (study_id, data, columns, row_count, source_filename, created_at)
        SELECT id, imported_data, imported_columns, imported_row_count, import_source, created_at
        FROM studies
        WHERE imported_data IS NOT NULL
        """
    )

    # ------------------------------------------------------------------
    # 4c. Drop the old imported_data columns from studies
    # ------------------------------------------------------------------
    op.drop_column("studies", "imported_data")
    op.drop_column("studies", "imported_columns")
    op.drop_column("studies", "imported_row_count")
    op.drop_column("studies", "import_source")


def downgrade():
    # ------------------------------------------------------------------
    # 4c. Re-add imported_data columns to studies
    # ------------------------------------------------------------------
    op.add_column("studies", sa.Column("imported_data", JSONB(), nullable=True))
    op.add_column("studies", sa.Column("imported_columns", JSONB(), nullable=True))
    op.add_column("studies", sa.Column("imported_row_count", sa.Integer(), nullable=True))
    op.add_column("studies", sa.Column("import_source", sa.String(255), nullable=True))

    # 4b. Migrate data back from study_datasets to studies
    op.execute(
        """
        UPDATE studies s
        SET imported_data = sd.data,
            imported_columns = sd.columns,
            imported_row_count = sd.row_count,
            import_source = sd.source_filename
        FROM study_datasets sd
        WHERE s.id = sd.study_id
        """
    )

    # 4. Drop study_datasets table
    op.drop_index("ix_study_datasets_study_id", table_name="study_datasets")
    op.drop_table("study_datasets")

    # 3. Restore global unique on sso_id
    op.drop_constraint("uq_users_sso_provider_id", "users", type_="unique")
    op.create_unique_constraint("users_sso_id_key", "users", ["sso_id"])

    # 2. Downgrade foreign key columns back to INTEGER
    for table, column in reversed(FK_COLUMNS):
        op.alter_column(table, column, type_=sa.Integer(), existing_type=sa.BigInteger())

    # 1. Downgrade primary keys back to INTEGER
    for table in reversed(PK_TABLES):
        op.alter_column(table, "id", type_=sa.Integer(), existing_type=sa.BigInteger())
