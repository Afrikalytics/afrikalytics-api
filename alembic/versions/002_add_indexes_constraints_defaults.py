"""Add indexes, CHECK constraints, server_defaults, and column alterations

Changes covered:
- audit_logs: composite index (user_id, action, created_at), index on resource_type,
  user_id nullable=True with ondelete SET NULL
- newsletter_campaigns: index on status, index on blog_post_id,
  CHECK constraint on status
- token_blacklist: DateTime(timezone=True) on expires_at and created_at,
  index on expires_at, index on user_id
- User: server_default on plan, is_active, is_admin
- BlogPost: server_default on views and status, CHECK constraint on status
- Study: server_default on status

Revision ID: 002
Revises: 001
Create Date: 2026-03-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================================================================
    # 1. USER — add server_default on plan, is_active, is_admin
    # ==================================================================
    op.alter_column(
        "users",
        "plan",
        server_default=sa.text("'basic'"),
    )
    op.alter_column(
        "users",
        "is_active",
        server_default=sa.text("'true'"),
    )
    op.alter_column(
        "users",
        "is_admin",
        server_default=sa.text("'false'"),
    )

    # ==================================================================
    # 2. STUDY — add server_default on status
    # ==================================================================
    op.alter_column(
        "studies",
        "status",
        server_default=sa.text("'Ouvert'"),
    )

    # ==================================================================
    # 3. BLOG_POSTS — add server_default on status and views,
    #    add CHECK constraint on status
    # ==================================================================
    op.alter_column(
        "blog_posts",
        "status",
        server_default=sa.text("'draft'"),
    )
    op.alter_column(
        "blog_posts",
        "views",
        server_default=sa.text("0"),
    )
    op.create_check_constraint(
        "ck_blog_posts_status",
        "blog_posts",
        "status IN ('draft', 'published', 'scheduled')",
    )

    # ==================================================================
    # 4. NEWSLETTER_CAMPAIGNS — add indexes on status and blog_post_id,
    #    add CHECK constraint on status
    # ==================================================================
    op.create_index(
        "ix_newsletter_campaigns_status",
        "newsletter_campaigns",
        ["status"],
    )
    op.create_index(
        "ix_newsletter_campaigns_blog_post_id",
        "newsletter_campaigns",
        ["blog_post_id"],
    )
    op.create_check_constraint(
        "ck_newsletter_campaigns_status",
        "newsletter_campaigns",
        "status IN ('draft', 'scheduled', 'sent', 'failed')",
    )

    # ==================================================================
    # 5. AUDIT_LOGS — composite index, index on resource_type,
    #    alter user_id to nullable + ondelete SET NULL
    # ==================================================================

    # Drop existing FK on audit_logs.user_id (no ondelete, nullable=False)
    op.drop_constraint(
        "audit_logs_user_id_fkey",
        "audit_logs",
        type_="foreignkey",
    )

    # Re-create FK with ondelete SET NULL
    op.create_foreign_key(
        "audit_logs_user_id_fkey",
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Make user_id nullable
    op.alter_column(
        "audit_logs",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # Composite index for efficient log queries
    op.create_index(
        "ix_audit_logs_user_action_created",
        "audit_logs",
        ["user_id", "action", "created_at"],
    )

    # Index on resource_type for filtering
    op.create_index(
        "ix_audit_logs_resource_type",
        "audit_logs",
        ["resource_type"],
    )

    # ==================================================================
    # 6. TOKEN_BLACKLIST — change expires_at & created_at to
    #    DateTime(timezone=True), add indexes on expires_at and user_id
    # ==================================================================
    op.alter_column(
        "token_blacklist",
        "expires_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "token_blacklist",
        "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        server_default=sa.func.now(),
    )
    op.create_index(
        "ix_token_blacklist_expires_at",
        "token_blacklist",
        ["expires_at"],
    )
    op.create_index(
        "ix_token_blacklist_user_id",
        "token_blacklist",
        ["user_id"],
    )


def downgrade() -> None:
    # ==================================================================
    # 6. TOKEN_BLACKLIST — revert
    # ==================================================================
    op.drop_index("ix_token_blacklist_user_id", table_name="token_blacklist")
    op.drop_index("ix_token_blacklist_expires_at", table_name="token_blacklist")
    op.alter_column(
        "token_blacklist",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
        server_default=sa.func.now(),
    )
    op.alter_column(
        "token_blacklist",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
    )

    # ==================================================================
    # 5. AUDIT_LOGS — revert
    # ==================================================================
    op.drop_index("ix_audit_logs_resource_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_action_created", table_name="audit_logs")

    # Revert user_id to NOT NULL
    op.alter_column(
        "audit_logs",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # Drop SET NULL FK, restore plain FK
    op.drop_constraint(
        "audit_logs_user_id_fkey",
        "audit_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "audit_logs_user_id_fkey",
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
    )

    # ==================================================================
    # 4. NEWSLETTER_CAMPAIGNS — revert
    # ==================================================================
    op.drop_constraint(
        "ck_newsletter_campaigns_status",
        "newsletter_campaigns",
        type_="check",
    )
    op.drop_index(
        "ix_newsletter_campaigns_blog_post_id",
        table_name="newsletter_campaigns",
    )
    op.drop_index(
        "ix_newsletter_campaigns_status",
        table_name="newsletter_campaigns",
    )

    # ==================================================================
    # 3. BLOG_POSTS — revert
    # ==================================================================
    op.drop_constraint(
        "ck_blog_posts_status",
        "blog_posts",
        type_="check",
    )
    op.alter_column(
        "blog_posts",
        "views",
        server_default=None,
    )
    op.alter_column(
        "blog_posts",
        "status",
        server_default=None,
    )

    # ==================================================================
    # 2. STUDY — revert
    # ==================================================================
    op.alter_column(
        "studies",
        "status",
        server_default=None,
    )

    # ==================================================================
    # 1. USER — revert
    # ==================================================================
    op.alter_column(
        "users",
        "is_admin",
        server_default=None,
    )
    op.alter_column(
        "users",
        "is_active",
        server_default=None,
    )
    op.alter_column(
        "users",
        "plan",
        server_default=None,
    )
