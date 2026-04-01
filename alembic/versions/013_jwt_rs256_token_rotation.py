"""Add token_family column and make user_id nullable on token_blacklist.

Supports JWT RS256 migration and refresh token rotation:
- token_family: groups related refresh tokens for compromise detection.
- user_id nullable: allows family-level revocations without a specific user.

Revision ID: 013
Revises: 012
"""

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add token_family column
    op.add_column(
        "token_blacklist",
        sa.Column("token_family", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_token_blacklist_token_family",
        "token_blacklist",
        ["token_family"],
    )

    # Make user_id nullable (for family-level revocations)
    op.alter_column(
        "token_blacklist",
        "user_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def downgrade() -> None:
    # Revert user_id to NOT NULL (remove rows with NULL user_id first)
    op.execute("DELETE FROM token_blacklist WHERE user_id IS NULL")
    op.alter_column(
        "token_blacklist",
        "user_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.drop_index("ix_token_blacklist_token_family", table_name="token_blacklist")
    op.drop_column("token_blacklist", "token_family")
