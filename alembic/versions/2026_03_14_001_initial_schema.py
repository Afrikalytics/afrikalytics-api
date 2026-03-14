"""Initial schema — all tables from models.py

Revision ID: 001
Revises: None
Create Date: 2026-03-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(50), default="basic", index=True),
        sa.Column("order_id", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, index=True),
        sa.Column("is_admin", sa.Boolean(), default=False),
        sa.Column("admin_role", sa.String(50), nullable=True),
        sa.Column(
            "parent_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "plan IN ('basic', 'professionnel', 'entreprise')",
            name="ck_users_plan",
        ),
        sa.CheckConstraint(
            "admin_role IN ('super_admin', 'admin_content', 'admin_studies', "
            "'admin_insights', 'admin_reports') OR admin_role IS NULL",
            name="ck_users_admin_role",
        ),
    )

    # ------------------------------------------------------------------
    # verification_codes
    # ------------------------------------------------------------------
    op.create_table(
        "verification_codes",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_used", sa.Boolean(), default=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_verification_code_lookup",
        "verification_codes",
        ["user_id", "code", "is_used"],
    )

    # ------------------------------------------------------------------
    # studies
    # ------------------------------------------------------------------
    op.create_table(
        "studies",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("duration", sa.String(50), nullable=True),
        sa.Column("deadline", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), default="Ouvert", index=True),
        sa.Column("icon", sa.String(50), default="users"),
        sa.Column("embed_url_particulier", sa.String(500), nullable=True),
        sa.Column("embed_url_entreprise", sa.String(500), nullable=True),
        sa.Column("embed_url_results", sa.String(500), nullable=True),
        sa.Column("report_url_basic", sa.String(500), nullable=True),
        sa.Column("report_url_premium", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # subscriptions
    # ------------------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column("plan", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), default="active", index=True),
        sa.Column("woocommerce_order_id", sa.String(100), nullable=True),
        sa.Column(
            "start_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled', 'expired')",
            name="ck_subscriptions_status",
        ),
    )

    # ------------------------------------------------------------------
    # blog_posts
    # ------------------------------------------------------------------
    op.create_table(
        "blog_posts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("featured_image", sa.String(500), nullable=True),
        sa.Column("category", sa.String(100), nullable=True, index=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("status", sa.String(50), default="draft", index=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_title", sa.String(255), nullable=True),
        sa.Column("meta_description", sa.String(500), nullable=True),
        sa.Column("og_image", sa.String(500), nullable=True),
        sa.Column("views", sa.Integer(), default=0),
        sa.Column("reading_time", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # newsletter_subscribers
    # ------------------------------------------------------------------
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("status", sa.String(50), default="active", index=True),
        sa.Column("is_confirmed", sa.Boolean(), default=False),
        sa.Column("confirmation_token", sa.String(255), nullable=True, index=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(100), default="blog_footer"),
        sa.Column(
            "unsubscribe_token",
            sa.String(255),
            unique=True,
            nullable=True,
            index=True,
        ),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "subscribed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # newsletter_campaigns
    # ------------------------------------------------------------------
    op.create_table(
        "newsletter_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "blog_post_id",
            sa.Integer(),
            sa.ForeignKey("blog_posts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("preview_text", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), default="draft"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipients_count", sa.Integer(), default=0),
        sa.Column("opened_count", sa.Integer(), default=0),
        sa.Column("clicked_count", sa.Integer(), default=0),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # insights
    # ------------------------------------------------------------------
    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "study_id",
            sa.Integer(),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_findings", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("images", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), default=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # reports
    # ------------------------------------------------------------------
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "study_id",
            sa.Integer(),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("report_type", sa.String(50), nullable=True, index=True),
        sa.Column(
            "download_count",
            sa.Integer(),
            default=0,
            server_default=sa.text("0"),
        ),
        sa.Column("is_available", sa.Boolean(), default=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "report_type IN ('basic', 'premium')",
            name="ck_reports_report_type",
        ),
    )

    # ------------------------------------------------------------------
    # contacts
    # ------------------------------------------------------------------
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), default=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------------------
    # token_blacklist
    # ------------------------------------------------------------------
    op.create_table(
        "token_blacklist",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("jti", sa.String(36), unique=True, nullable=False, index=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("token_blacklist")
    op.drop_table("audit_logs")
    op.drop_table("contacts")
    op.drop_table("reports")
    op.drop_table("insights")
    op.drop_table("newsletter_campaigns")
    op.drop_table("newsletter_subscribers")
    op.drop_table("blog_posts")
    op.drop_table("subscriptions")
    op.drop_table("studies")
    op.drop_index("ix_verification_code_lookup", table_name="verification_codes")
    op.drop_table("verification_codes")
    op.drop_table("users")
