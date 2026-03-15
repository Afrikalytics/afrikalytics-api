"""Add soft delete (deleted_at) column to main tables.

Revision ID: 004
Revises: 002
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '002'
branch_labels = None
depends_on = None

TABLES = ['users', 'studies', 'blog_posts', 'insights', 'reports', 'contacts']


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        op.create_index(f'ix_{table}_deleted_at', table, ['deleted_at'])


def downgrade():
    for table in TABLES:
        op.drop_index(f'ix_{table}_deleted_at', table)
        op.drop_column(table, 'deleted_at')
