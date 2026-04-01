"""Add composite indexes for analytics and common query patterns.

These indexes optimize:
- Payment history queries (user + subscription join)
- Subscription status filtering
- User plan analytics
- Content discovery (published insights, reports)
- Blog post listing and search

Revision ID: 014
Revises: 013
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Payment queries: history per user, joins with subscription
    op.create_index(
        "ix_payments_user_subscription",
        "payments",
        ["user_id", "subscription_id"],
    )
    op.create_index(
        "ix_payments_status_created",
        "payments",
        ["status", "created_at"],
    )

    # Subscription analytics: active counts, expiry checks
    op.create_index(
        "ix_subscriptions_status_created",
        "subscriptions",
        ["status", "created_at"],
    )

    # User plan analytics and admin queries
    op.create_index(
        "ix_users_plan_created",
        "users",
        ["plan", "created_at"],
    )
    op.create_index(
        "ix_users_active_admin",
        "users",
        ["is_active", "is_admin"],
    )

    # Published content discovery
    op.create_index(
        "ix_insights_published_created",
        "insights",
        ["is_published", "created_at"],
    )
    op.create_index(
        "ix_reports_available_created",
        "reports",
        ["is_available", "created_at"],
    )

    # Blog: published posts listing, category filtering
    op.create_index(
        "ix_blog_posts_status_published",
        "blog_posts",
        ["status", "published_at"],
    )
    op.create_index(
        "ix_blog_posts_category",
        "blog_posts",
        ["category"],
    )


def downgrade() -> None:
    op.drop_index("ix_blog_posts_category", table_name="blog_posts")
    op.drop_index("ix_blog_posts_status_published", table_name="blog_posts")
    op.drop_index("ix_reports_available_created", table_name="reports")
    op.drop_index("ix_insights_published_created", table_name="insights")
    op.drop_index("ix_users_active_admin", table_name="users")
    op.drop_index("ix_users_plan_created", table_name="users")
    op.drop_index("ix_subscriptions_status_created", table_name="subscriptions")
    op.drop_index("ix_payments_status_created", table_name="payments")
    op.drop_index("ix_payments_user_subscription", table_name="payments")
