"""Add dashboard_layouts table for user-saved dashboard configurations.

Stores the full DashboardLayout JSON (widgets, positions, config) per user.
Supports both user layouts and shared templates.

Revision ID: 015
Revises: 014
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_layouts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("layout", JSONB(), nullable=False),
        sa.Column(
            "is_template",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("template_category", sa.String(100), nullable=True),
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
    op.create_index(
        "ix_dashboard_layouts_user_template",
        "dashboard_layouts",
        ["user_id", "is_template"],
    )


def downgrade() -> None:
    op.drop_index("ix_dashboard_layouts_user_template", table_name="dashboard_layouts")
    op.drop_table("dashboard_layouts")
