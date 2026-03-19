"""create products and reviews tables

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('price', sa.Numeric(10, 2)),
    )
    op.create_table(
        'reviews',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('body', sa.Text()),
        sa.Column('rating', sa.Integer()),
        sa.Column('product_id', sa.Integer()),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
    )


def downgrade():
    op.drop_table('reviews')
    op.drop_table('products')
