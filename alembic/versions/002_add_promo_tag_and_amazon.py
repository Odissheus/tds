"""Add promo_tag column to promotions and Amazon retailer support

Revision ID: 002
Revises: 001
Create Date: 2026-03-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("promotions", sa.Column("promo_tag", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("promotions", "promo_tag")
