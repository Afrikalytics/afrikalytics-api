"""Migrate Text columns storing JSON to native JSONB type

Columns migrated:
- blog_posts.tags: Text -> JSONB (stores tag lists)
- insights.images: Text -> JSONB (stores image URL lists)
- insights.key_findings: Text -> JSONB (stores findings lists)
- insights.recommendations: Text -> JSONB (stores recommendation lists)
- audit_logs.details: Text -> JSONB (stores action detail objects)

Uses postgresql_using='column::jsonb' to cast existing JSON text data
during the migration. Adds server_default='[]'::jsonb where appropriate.

Revision ID: 003
Revises: 002
Create Date: 2026-03-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================================================================
    # 1. BLOG_POSTS.tags — Text -> JSONB
    # ==================================================================
    op.alter_column(
        "blog_posts",
        "tags",
        existing_type=sa.Text(),
        type_=JSONB,
        existing_nullable=True,
        postgresql_using="tags::jsonb",
        server_default=sa.text("'[]'::jsonb"),
    )

    # ==================================================================
    # 2. INSIGHTS.images — Text -> JSONB
    # ==================================================================
    op.alter_column(
        "insights",
        "images",
        existing_type=sa.Text(),
        type_=JSONB,
        existing_nullable=True,
        postgresql_using="images::jsonb",
        server_default=sa.text("'[]'::jsonb"),
    )

    # ==================================================================
    # 3. INSIGHTS.key_findings — Text -> JSONB
    # ==================================================================
    op.alter_column(
        "insights",
        "key_findings",
        existing_type=sa.Text(),
        type_=JSONB,
        existing_nullable=True,
        postgresql_using="key_findings::jsonb",
        server_default=sa.text("'[]'::jsonb"),
    )

    # ==================================================================
    # 4. INSIGHTS.recommendations — Text -> JSONB
    # ==================================================================
    op.alter_column(
        "insights",
        "recommendations",
        existing_type=sa.Text(),
        type_=JSONB,
        existing_nullable=True,
        postgresql_using="recommendations::jsonb",
        server_default=sa.text("'[]'::jsonb"),
    )

    # ==================================================================
    # 5. AUDIT_LOGS.details — Text -> JSONB
    # ==================================================================
    op.alter_column(
        "audit_logs",
        "details",
        existing_type=sa.Text(),
        type_=JSONB,
        existing_nullable=True,
        postgresql_using="details::jsonb",
    )


def downgrade() -> None:
    # ==================================================================
    # 5. AUDIT_LOGS.details — JSONB -> Text
    # ==================================================================
    op.alter_column(
        "audit_logs",
        "details",
        existing_type=JSONB,
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="details::text",
    )

    # ==================================================================
    # 4. INSIGHTS.recommendations — JSONB -> Text
    # ==================================================================
    op.alter_column(
        "insights",
        "recommendations",
        existing_type=JSONB,
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="recommendations::text",
        server_default=None,
    )

    # ==================================================================
    # 3. INSIGHTS.key_findings — JSONB -> Text
    # ==================================================================
    op.alter_column(
        "insights",
        "key_findings",
        existing_type=JSONB,
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="key_findings::text",
        server_default=None,
    )

    # ==================================================================
    # 2. INSIGHTS.images — JSONB -> Text
    # ==================================================================
    op.alter_column(
        "insights",
        "images",
        existing_type=JSONB,
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="images::text",
        server_default=None,
    )

    # ==================================================================
    # 1. BLOG_POSTS.tags — JSONB -> Text
    # ==================================================================
    op.alter_column(
        "blog_posts",
        "tags",
        existing_type=JSONB,
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="tags::text",
        server_default=None,
    )
