"""Add import columns to studies table

Adds 4 columns for CSV/Excel data import feature:
- imported_data (JSONB): raw imported data rows
- imported_columns (JSONB): column names/metadata
- imported_row_count (Integer): number of imported rows
- import_source (String): original filename

Revision ID: 007
Revises: 006
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("studies", sa.Column("imported_data", JSONB, nullable=True))
    op.add_column("studies", sa.Column("imported_columns", JSONB, nullable=True))
    op.add_column("studies", sa.Column("imported_row_count", sa.Integer, nullable=True))
    op.add_column("studies", sa.Column("import_source", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("studies", "import_source")
    op.drop_column("studies", "imported_row_count")
    op.drop_column("studies", "imported_columns")
    op.drop_column("studies", "imported_data")
