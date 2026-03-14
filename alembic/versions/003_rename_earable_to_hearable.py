"""Rename category_enum value earable -> hearable

Revision ID: 003
Revises: 002
Create Date: 2026-03-14
"""
from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE category_enum RENAME VALUE 'earable' TO 'hearable'")


def downgrade() -> None:
    op.execute("ALTER TYPE category_enum RENAME VALUE 'hearable' TO 'earable'")
