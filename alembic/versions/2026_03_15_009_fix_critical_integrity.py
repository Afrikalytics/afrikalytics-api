"""Fix critical integrity issues: mutable defaults, server_defaults, CHECK constraints,
ondelete clauses, missing indexes, and new tables (api_keys, marketplace_templates,
sso_exchange_codes).

Changes applied to existing tables:
  P1  — Add server_default on all remaining Python-side default= columns
  P2  — Add CHECK constraints: studies.status, newsletter_subscribers.status,
         payments.amount > 0, marketplace_templates guardrails
  P5  — Align ondelete clauses in models (already correct in migrations 001-008
         for most FKs; this migration fixes remaining gaps)
  P7  — lazy="selectin" replaces lazy="dynamic" (code-only, no DDL)
  P8  — ApiKey.permissions server_default fixes mutable default=["read"]
  P9  — MarketplaceTemplate.tags server_default fixes mutable default=[]
  P10 — Add index ix_insights_study_id (guard: may already exist from migration 001)
  P11 — Add ix_verification_codes_user_id + composite user_active index
  P13 — CHECK payments.amount > 0
  P16 — Replace global sso_id UNIQUE with per-provider partial index (done in 008)
  P21 — Migrate notifications.metadata_json from JSON to JSONB

New tables created:
  api_keys               — P8 fix: key stored as hash (key_hash + key_prefix)
  marketplace_templates  — P9 fix: tags uses server_default
  sso_exchange_codes     — Secure SSO JWT exchange (code-based, avoids URL tokens)

Additional indexes:
  ix_payments_created_at
  ix_newsletter_confirmed_active (partial index)
  ix_studies_active

Revision ID: 009
Revises: 008
Create Date: 2026-03-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================================================================
    # 1. STUDY — add CHECK constraint on status (P2)
    #    Add server_default on duration, icon, is_active (P1)
    #    Add composite index on is_active + deleted_at
    # ==================================================================
    op.create_check_constraint(
        "ck_studies_status",
        "studies",
        "status IN ('Ouvert', 'Ferme', 'Bientot')",
    )
    op.alter_column(
        "studies", "duration",
        server_default=sa.text("'15-20 min'"),
        existing_type=sa.String(50),
        existing_nullable=True,
    )
    op.alter_column(
        "studies", "icon",
        server_default=sa.text("'users'"),
        existing_type=sa.String(50),
        existing_nullable=True,
    )
    op.alter_column(
        "studies", "is_active",
        server_default=sa.text("true"),
        nullable=False,
        existing_type=sa.Boolean(),
    )
    op.create_index("ix_studies_active", "studies", ["is_active", "deleted_at"])

    # ==================================================================
    # 2. SUBSCRIPTION — add server_default on status (P1)
    # ==================================================================
    op.alter_column(
        "subscriptions", "status",
        server_default=sa.text("'active'"),
        nullable=False,
        existing_type=sa.String(50),
    )

    # ==================================================================
    # 3. PAYMENTS — add CHECK amount > 0 (P13) + index on created_at
    # ==================================================================
    op.create_check_constraint(
        "ck_payments_amount_positive",
        "payments",
        "amount > 0",
    )
    op.create_index("ix_payments_created_at", "payments", ["created_at"])

    # ==================================================================
    # 4. INSIGHT — server_default on is_published (P1)
    #    Standalone index on study_id (P10 — guard with if_not_exists)
    # ==================================================================
    op.alter_column(
        "insights", "is_published",
        server_default=sa.text("false"),
        nullable=False,
        existing_type=sa.Boolean(),
    )
    # Migration 001 may have created ix_insights_study_id via index=True on
    # the column inside create_table(). if_not_exists prevents a duplicate error.
    op.create_index(
        "ix_insights_study_id", "insights", ["study_id"],
        if_not_exists=True,
    )

    # ==================================================================
    # 5. REPORT — server_defaults on report_type, download_count,
    #    is_available (P1); standalone index on study_id (P10)
    # ==================================================================
    op.alter_column(
        "reports", "report_type",
        server_default=sa.text("'premium'"),
        nullable=False,
        existing_type=sa.String(50),
    )
    op.alter_column(
        "reports", "download_count",
        server_default=sa.text("0"),
        nullable=False,
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "reports", "is_available",
        server_default=sa.text("true"),
        nullable=False,
        existing_type=sa.Boolean(),
    )
    op.create_index(
        "ix_reports_study_id", "reports", ["study_id"],
        if_not_exists=True,
    )

    # ==================================================================
    # 6. BLOG_POSTS — enforce NOT NULL on views and status (already have
    #    server_defaults from migration 002, just tighten nullability)
    # ==================================================================
    op.alter_column(
        "blog_posts", "views",
        nullable=False,
        existing_type=sa.Integer(),
        existing_server_default=sa.text("0"),
    )
    op.alter_column(
        "blog_posts", "status",
        nullable=False,
        existing_type=sa.String(20),
        existing_server_default=sa.text("'draft'"),
    )

    # ==================================================================
    # 7. NEWSLETTER_SUBSCRIBERS — CHECK constraint on status (P2)
    #    server_defaults on status, source, is_confirmed (P1)
    #    Partial index for confirmed+active subscribers
    # ==================================================================
    op.create_check_constraint(
        "ck_newsletter_subscribers_status",
        "newsletter_subscribers",
        "status IN ('active', 'unsubscribed', 'bounced')",
    )
    op.alter_column(
        "newsletter_subscribers", "status",
        server_default=sa.text("'active'"),
        nullable=False,
        existing_type=sa.String(50),
    )
    op.alter_column(
        "newsletter_subscribers", "source",
        server_default=sa.text("'blog_footer'"),
        nullable=False,
        existing_type=sa.String(100),
    )
    op.alter_column(
        "newsletter_subscribers", "is_confirmed",
        server_default=sa.text("false"),
        nullable=False,
        existing_type=sa.Boolean(),
    )
    op.create_index(
        "ix_newsletter_confirmed_active",
        "newsletter_subscribers",
        ["id"],
        postgresql_where=sa.text("is_confirmed = true AND status = 'active'"),
    )

    # ==================================================================
    # 8. NEWSLETTER_CAMPAIGNS — server_defaults on counters and status (P1)
    # ==================================================================
    op.alter_column(
        "newsletter_campaigns", "status",
        server_default=sa.text("'draft'"),
        nullable=False,
        existing_type=sa.String(20),
    )
    op.alter_column(
        "newsletter_campaigns", "recipients_count",
        server_default=sa.text("0"),
        nullable=False,
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "newsletter_campaigns", "opened_count",
        server_default=sa.text("0"),
        nullable=False,
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "newsletter_campaigns", "clicked_count",
        server_default=sa.text("0"),
        nullable=False,
        existing_type=sa.Integer(),
    )

    # ==================================================================
    # 9. CONTACTS — server_default on is_read (P1)
    # ==================================================================
    op.alter_column(
        "contacts", "is_read",
        server_default=sa.text("false"),
        nullable=False,
        existing_type=sa.Boolean(),
    )

    # ==================================================================
    # 10. VERIFICATION_CODES — server_default on is_used (P1)
    #     Standalone index on user_id (P11 — guard with if_not_exists)
    #     Composite index for "find active code for user" query
    # ==================================================================
    op.alter_column(
        "verification_codes", "is_used",
        server_default=sa.text("false"),
        nullable=False,
        existing_type=sa.Boolean(),
    )
    op.create_index(
        "ix_verification_codes_user_id",
        "verification_codes",
        ["user_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_verification_codes_user_active",
        "verification_codes",
        ["user_id", "is_used", "expires_at"],
    )

    # ==================================================================
    # 11. NOTIFICATIONS — server_default on is_read (P1)
    #     Migrate metadata_json from JSON -> JSONB (P21)
    # ==================================================================
    op.alter_column(
        "notifications", "is_read",
        server_default=sa.text("false"),
        nullable=False,
        existing_type=sa.Boolean(),
    )
    op.alter_column(
        "notifications", "metadata_json",
        existing_type=sa.JSON(),
        type_=JSONB,
        existing_nullable=True,
        postgresql_using="metadata_json::jsonb",
    )

    # ==================================================================
    # 12. CREATE TABLE: api_keys
    #
    # Security improvement (P4 from audit): the raw API key is shown once
    # at creation time and never stored. We store key_hash (SHA-256) for
    # validation and key_prefix (first 8 chars) for identification in the UI.
    # ==================================================================
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SHA-256 hash of the raw key — used for lookups / validation
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        # First 8 chars of the raw key — safe to display, identifies the key
        sa.Column("key_prefix", sa.String(8), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allowed_origins", JSONB, nullable=True),
        # FIX P8: was mutable Python default=["read"]; now DB-side default
        sa.Column(
            "permissions",
            JSONB,
            nullable=False,
            server_default=sa.text('\'["read"]\'::jsonb'),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    # ==================================================================
    # 13. CREATE TABLE: marketplace_templates
    # ==================================================================
    op.create_table(
        "marketplace_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        # FIX P9: was mutable Python default=[]; now DB-side default
        sa.Column(
            "tags",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("preview_image_url", sa.String(500), nullable=True),
        sa.Column("layout_json", JSONB, nullable=False),
        sa.Column("demo_data", JSONB, nullable=True),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_free", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("price", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("plan_required", sa.String(20), nullable=False, server_default=sa.text("'basic'")),
        sa.Column("install_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rating", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("widget_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "plan_required IN ('basic', 'professionnel', 'entreprise')",
            name="ck_marketplace_templates_plan_required",
        ),
        sa.CheckConstraint(
            "price >= 0",
            name="ck_marketplace_templates_price_non_negative",
        ),
        sa.CheckConstraint(
            "rating >= 0.0 AND rating <= 5.0",
            name="ck_marketplace_templates_rating_range",
        ),
    )
    op.create_index("ix_marketplace_templates_category", "marketplace_templates", ["category"])
    op.create_index("ix_marketplace_templates_is_published", "marketplace_templates", ["is_published"])
    op.create_index("ix_marketplace_templates_author_id", "marketplace_templates", ["author_id"])

    # ==================================================================
    # 14. CREATE TABLE: sso_exchange_codes
    #
    # Secure SSO JWT exchange: avoids embedding JWTs in redirect URLs.
    # Flow: SSO callback generates a short-lived code (60 s), stores the JWT
    # server-side, then redirects to /login?sso_code=<code>. Frontend POSTs
    # the code to /api/auth/sso/exchange to receive the JWT in the response body.
    # ==================================================================
    op.create_table(
        "sso_exchange_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sso_exchange_codes_code", "sso_exchange_codes", ["code"], unique=True)
    op.create_index("ix_sso_exchange_codes_user_id", "sso_exchange_codes", ["user_id"])
    op.create_index("ix_sso_exchange_codes_expires_at", "sso_exchange_codes", ["expires_at"])


def downgrade() -> None:
    # ==================================================================
    # 14. DROP sso_exchange_codes
    # ==================================================================
    op.drop_index("ix_sso_exchange_codes_expires_at", table_name="sso_exchange_codes")
    op.drop_index("ix_sso_exchange_codes_user_id", table_name="sso_exchange_codes")
    op.drop_index("ix_sso_exchange_codes_code", table_name="sso_exchange_codes")
    op.drop_table("sso_exchange_codes")

    # ==================================================================
    # 13. DROP marketplace_templates
    # ==================================================================
    op.drop_index("ix_marketplace_templates_author_id", table_name="marketplace_templates")
    op.drop_index("ix_marketplace_templates_is_published", table_name="marketplace_templates")
    op.drop_index("ix_marketplace_templates_category", table_name="marketplace_templates")
    op.drop_table("marketplace_templates")

    # ==================================================================
    # 12. DROP api_keys
    # ==================================================================
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")

    # ==================================================================
    # 11. NOTIFICATIONS — revert JSONB -> JSON, remove server_default
    # ==================================================================
    op.alter_column(
        "notifications", "metadata_json",
        existing_type=JSONB,
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="metadata_json::text::json",
    )
    op.alter_column(
        "notifications", "is_read",
        server_default=None,
        nullable=True,
        existing_type=sa.Boolean(),
    )

    # ==================================================================
    # 10. VERIFICATION_CODES — remove indexes, revert server_default
    # ==================================================================
    op.drop_index("ix_verification_codes_user_active", table_name="verification_codes")
    # if_exists because this index may have existed before migration 009
    op.drop_index("ix_verification_codes_user_id", table_name="verification_codes", if_exists=True)
    op.alter_column(
        "verification_codes", "is_used",
        server_default=None,
        nullable=True,
        existing_type=sa.Boolean(),
    )

    # ==================================================================
    # 9. CONTACTS — revert server_default
    # ==================================================================
    op.alter_column(
        "contacts", "is_read",
        server_default=None,
        nullable=True,
        existing_type=sa.Boolean(),
    )

    # ==================================================================
    # 8. NEWSLETTER_CAMPAIGNS — revert server_defaults
    # ==================================================================
    op.alter_column("newsletter_campaigns", "clicked_count", server_default=None, nullable=True, existing_type=sa.Integer())
    op.alter_column("newsletter_campaigns", "opened_count", server_default=None, nullable=True, existing_type=sa.Integer())
    op.alter_column("newsletter_campaigns", "recipients_count", server_default=None, nullable=True, existing_type=sa.Integer())
    op.alter_column("newsletter_campaigns", "status", server_default=None, nullable=True, existing_type=sa.String(20))

    # ==================================================================
    # 7. NEWSLETTER_SUBSCRIBERS — revert CHECK + server_defaults + index
    # ==================================================================
    op.drop_index("ix_newsletter_confirmed_active", table_name="newsletter_subscribers")
    op.alter_column("newsletter_subscribers", "is_confirmed", server_default=None, nullable=True, existing_type=sa.Boolean())
    op.alter_column("newsletter_subscribers", "source", server_default=None, nullable=True, existing_type=sa.String(100))
    op.alter_column("newsletter_subscribers", "status", server_default=None, nullable=True, existing_type=sa.String(50))
    op.drop_constraint("ck_newsletter_subscribers_status", "newsletter_subscribers", type_="check")

    # ==================================================================
    # 6. BLOG_POSTS — revert nullable tightening
    # ==================================================================
    op.alter_column("blog_posts", "status", nullable=True, existing_type=sa.String(20), existing_server_default=sa.text("'draft'"))
    op.alter_column("blog_posts", "views", nullable=True, existing_type=sa.Integer(), existing_server_default=sa.text("0"))

    # ==================================================================
    # 5. REPORT — revert server_defaults, drop index (if_exists guard)
    # ==================================================================
    op.drop_index("ix_reports_study_id", table_name="reports", if_exists=True)
    op.alter_column("reports", "is_available", server_default=None, nullable=True, existing_type=sa.Boolean())
    op.alter_column("reports", "download_count", server_default=None, nullable=True, existing_type=sa.Integer())
    op.alter_column("reports", "report_type", server_default=None, nullable=True, existing_type=sa.String(50))

    # ==================================================================
    # 4. INSIGHT — revert server_default, drop index (if_exists guard)
    # ==================================================================
    op.drop_index("ix_insights_study_id", table_name="insights", if_exists=True)
    op.alter_column("insights", "is_published", server_default=None, nullable=True, existing_type=sa.Boolean())

    # ==================================================================
    # 3. PAYMENTS — drop index + CHECK
    # ==================================================================
    op.drop_index("ix_payments_created_at", table_name="payments")
    op.drop_constraint("ck_payments_amount_positive", "payments", type_="check")

    # ==================================================================
    # 2. SUBSCRIPTION — revert server_default
    # ==================================================================
    op.alter_column("subscriptions", "status", server_default=None, nullable=True, existing_type=sa.String(50))

    # ==================================================================
    # 1. STUDY — drop index, revert server_defaults, drop CHECK
    # ==================================================================
    op.drop_index("ix_studies_active", table_name="studies")
    op.alter_column("studies", "is_active", server_default=None, nullable=True, existing_type=sa.Boolean())
    op.alter_column("studies", "icon", server_default=None, existing_type=sa.String(50))
    op.alter_column("studies", "duration", server_default=None, existing_type=sa.String(50))
    op.drop_constraint("ck_studies_status", "studies", type_="check")
