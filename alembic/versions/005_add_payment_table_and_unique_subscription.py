"""Add payments table and unique active subscription constraint.

Revision ID: 005
Revises: 004
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    # Create payments table
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('subscription_id', sa.Integer(), sa.ForeignKey('subscriptions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), server_default=sa.text("'XOF'"), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_ref', sa.String(255), nullable=True),
        sa.Column('provider_status', sa.String(50), nullable=True),
        sa.Column('plan', sa.String(50), nullable=False),
        sa.Column('payment_method', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('metadata_json', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'refunded')",
            name='ck_payments_status',
        ),
    )

    # Indexes on payments
    op.create_index('ix_payments_id', 'payments', ['id'])
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])
    op.create_index('ix_payments_subscription_id', 'payments', ['subscription_id'])
    op.create_index('ix_payments_provider_ref', 'payments', ['provider_ref'], unique=True)

    # Partial unique index on subscriptions: only one active subscription per user
    op.create_index(
        'uq_one_active_subscription_per_user',
        'subscriptions',
        ['user_id'],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade():
    op.drop_index('uq_one_active_subscription_per_user', 'subscriptions')
    op.drop_index('ix_payments_provider_ref', 'payments')
    op.drop_index('ix_payments_subscription_id', 'payments')
    op.drop_index('ix_payments_user_id', 'payments')
    op.drop_index('ix_payments_id', 'payments')
    op.drop_table('payments')
