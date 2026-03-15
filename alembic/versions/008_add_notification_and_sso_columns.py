"""Add notifications table and SSO columns to users

Creates the notifications table for in-app notifications and adds
sso_provider / sso_id columns to the users table for SSO support
(Google, Microsoft).

Revision ID: 008
Revises: 007
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    # -- Notifications table --------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("is_read", sa.Boolean, default=False, index=True),
        sa.Column("metadata_json", JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Composite index for efficient "unread notifications" queries
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "is_read", "created_at"],
    )

    # -- SSO columns on users -------------------------------------------------
    op.add_column(
        "users",
        sa.Column("sso_provider", sa.String(50), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("sso_id", sa.String(255), nullable=True),
    )

    # Unique constraint: one SSO identity per provider
    op.create_index(
        "ix_users_sso_provider_id",
        "users",
        ["sso_provider", "sso_id"],
        unique=True,
        postgresql_where=sa.text("sso_provider IS NOT NULL AND sso_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_users_sso_provider_id", table_name="users")
    op.drop_column("users", "sso_id")
    op.drop_column("users", "sso_provider")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_table("notifications")
