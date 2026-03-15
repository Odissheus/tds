"""Add storage_gb, is_bundle, bundle_description to promotions

Revision ID: 004
Revises: 003
Create Date: 2026-03-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("promotions", sa.Column("storage_gb", sa.Integer, nullable=True))
    op.add_column("promotions", sa.Column("is_bundle", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("promotions", sa.Column("bundle_description", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("promotions", "bundle_description")
    op.drop_column("promotions", "is_bundle")
    op.drop_column("promotions", "storage_gb")
