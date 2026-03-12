"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Products table
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("brand", sa.String(100), nullable=False, index=True),
        sa.Column("series", sa.String(200), nullable=False),
        sa.Column("model", sa.String(300), nullable=False, index=True),
        sa.Column("category", sa.Enum("smartphone", "earable", "wearable", "accessory", "bundle", name="category_enum"), nullable=False),
        sa.Column("tier", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_google", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("listino_eur", sa.Float, nullable=True),
        sa.Column("status", sa.Enum("active", "eol", "disabled", name="status_enum"), nullable=False, server_default="active"),
        sa.Column("not_found_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Promotions table
    op.create_table(
        "promotions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("retailer", sa.String(50), nullable=False, index=True),
        sa.Column("retailer_variant", sa.String(100), nullable=True),
        sa.Column("prezzo_originale", sa.Float, nullable=False),
        sa.Column("prezzo_promo", sa.Float, nullable=False),
        sa.Column("sconto_percentuale", sa.Float, nullable=False),
        sa.Column("data_inizio", sa.Date, nullable=False),
        sa.Column("data_fine", sa.Date, nullable=True),
        sa.Column("url_fonte", sa.String(500), nullable=False),
        sa.Column("settimana", sa.String(10), nullable=False, index=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Scrape logs table
    op.create_table(
        "scrape_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("retailer", sa.String(50), nullable=False),
        sa.Column("status", sa.Enum("found", "not_found", "error", name="scrape_status_enum"), nullable=False),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Reports table
    op.create_table(
        "reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("type", sa.Enum("weekly", "custom", name="report_type_enum"), nullable=False),
        sa.Column("settimana", sa.String(10), nullable=False, index=True),
        sa.Column("pdf_path", sa.String(500), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by", sa.String(50), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("scrape_logs")
    op.drop_table("promotions")
    op.drop_table("products")
    op.execute("DROP TYPE IF EXISTS report_type_enum")
    op.execute("DROP TYPE IF EXISTS scrape_status_enum")
    op.execute("DROP TYPE IF EXISTS status_enum")
    op.execute("DROP TYPE IF EXISTS category_enum")
