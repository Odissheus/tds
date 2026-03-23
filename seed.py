"""
TDS — Seed script for initial product catalog.
Idempotent: uses upsert on (brand, model) — safe to run multiple times.
"""
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from backend.database import sync_session_factory
from backend.models.base import Base
from backend.models.product import Product, CategoryEnum, StatusEnum

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tds.seed")

CATALOG = [
    # ========================
    # GOOGLE PIXEL — PRIORITY 1 (Pixel 10)
    # ========================
    {"brand": "Google", "series": "Pixel 10", "model": "Pixel 10", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 899.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 10", "model": "Pixel 10 Pro", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1099.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 10", "model": "Pixel 10 Pro XL", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1199.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 10", "model": "Pixel 10 Pro Fold", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1899.0, "status": "active"},

    # ========================
    # GOOGLE PIXEL — PRIORITY 2 (Pixel 9)
    # ========================
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 899.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9 Pro", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1099.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9 Pro XL", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1179.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9 Pro Fold", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1799.0, "status": "active"},

    # ========================
    # SAMSUNG — COMPETITOR
    # ========================
    {"brand": "Samsung", "series": "Galaxy S25", "model": "Galaxy S25", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 879.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy S25", "model": "Galaxy S25+", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1099.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy S25", "model": "Galaxy S25 Ultra", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1459.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy A", "model": "Galaxy A55", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 449.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy A", "model": "Galaxy A35", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 329.0, "status": "active"},

    # ========================
    # APPLE — COMPETITOR
    # ========================
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 929.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16 Plus", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1059.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1179.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16 Pro Max", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1429.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16e", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 679.0, "status": "active"},

    # ========================
    # HONOR — COMPETITOR
    # ========================
    {"brand": "Honor", "series": "Magic7", "model": "Honor Magic7 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 799.0, "status": "active"},
    {"brand": "Honor", "series": "Magic7", "model": "Honor Magic7 Lite", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 299.0, "status": "active"},
    {"brand": "Honor", "series": "Honor 400", "model": "Honor 400", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 399.0, "status": "active"},

    # ========================
    # OPPO — COMPETITOR
    # ========================
    {"brand": "OPPO", "series": "Find X9", "model": "OPPO Find X9 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 999.0, "status": "active"},
    {"brand": "OPPO", "series": "Reno13", "model": "OPPO Reno13", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 399.0, "status": "active"},

    # ========================
    # XIAOMI / REDMI / POCO — COMPETITOR
    # ========================
    {"brand": "Xiaomi", "series": "Xiaomi 15", "model": "Xiaomi 15", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 799.0, "status": "active"},
    {"brand": "Xiaomi", "series": "Xiaomi 15", "model": "Xiaomi 15 Ultra", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1299.0, "status": "active"},
    {"brand": "Redmi", "series": "Redmi Note 15", "model": "Redmi Note 15 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 349.0, "status": "active"},
    {"brand": "POCO", "series": "POCO F7", "model": "POCO F7", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 399.0, "status": "active"},

    # ========================
    # MOTOROLA — COMPETITOR
    # ========================
    {"brand": "Motorola", "series": "Edge 60", "model": "Motorola Edge 60 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 799.0, "status": "active"},
    {"brand": "Motorola", "series": "Edge 60", "model": "Motorola Edge 60 Fusion", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 399.0, "status": "active"},
    {"brand": "Motorola", "series": "Razr 50", "model": "Motorola Razr 50", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 899.0, "status": "active"},
]


def seed_catalog():
    """Seed the product catalog. Idempotent — uses upsert logic."""
    with sync_session_factory() as session:
        created = 0
        updated = 0

        for item in CATALOG:
            existing = session.execute(
                select(Product).where(
                    Product.brand == item["brand"],
                    Product.model == item["model"],
                )
            ).scalar_one_or_none()

            if existing:
                changed = False
                for field in ["series", "category", "tier", "is_google", "listino_eur", "status"]:
                    new_val = item[field]
                    if field == "category":
                        new_val = CategoryEnum(new_val)
                    elif field == "status":
                        new_val = StatusEnum(new_val)
                    if getattr(existing, field) != new_val:
                        setattr(existing, field, new_val)
                        changed = True
                # Always reset streak on seed run
                if existing.not_found_streak != 0:
                    existing.not_found_streak = 0
                    changed = True
                if changed:
                    updated += 1
            else:
                product = Product(
                    brand=item["brand"],
                    series=item["series"],
                    model=item["model"],
                    category=CategoryEnum(item["category"]),
                    tier=item["tier"],
                    is_google=item["is_google"],
                    listino_eur=item["listino_eur"],
                    status=StatusEnum(item["status"]),
                )
                session.add(product)
                created += 1

        # Disable products not in catalog
        catalog_models = {(item["brand"], item["model"]) for item in CATALOG}
        all_products = session.execute(select(Product)).scalars().all()
        disabled = 0
        for p in all_products:
            if (p.brand, p.model) not in catalog_models and p.status != StatusEnum.disabled:
                p.status = StatusEnum.disabled
                disabled += 1

        session.commit()
        logger.info("Seed complete: %d created, %d updated, %d disabled, %d in catalog", created, updated, disabled, len(CATALOG))


if __name__ == "__main__":
    seed_catalog()
