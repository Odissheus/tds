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
    # GOOGLE PIXEL — TIER 1
    # ========================
    # Smartphone
    {"brand": "Google", "series": "Pixel 10", "model": "Pixel 10", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 799.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 10", "model": "Pixel 10 Pro", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1099.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 10", "model": "Pixel 10 Pro XL", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1199.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 899.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9 Pro", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1099.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9 Pro XL", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1179.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9 Pro Fold", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 1899.0, "status": "active"},
    {"brand": "Google", "series": "Pixel 9", "model": "Pixel 9a", "category": "smartphone", "tier": 1, "is_google": True, "listino_eur": 499.0, "status": "active"},
    # Earable
    {"brand": "Google", "series": "Pixel Buds", "model": "Pixel Buds Pro 2", "category": "earable", "tier": 1, "is_google": True, "listino_eur": 229.0, "status": "active"},
    {"brand": "Google", "series": "Pixel Buds", "model": "Pixel Buds A-Series", "category": "earable", "tier": 1, "is_google": True, "listino_eur": 99.0, "status": "active"},
    # Wearable
    {"brand": "Google", "series": "Pixel Watch 3", "model": "Pixel Watch 3 41mm", "category": "wearable", "tier": 1, "is_google": True, "listino_eur": 349.0, "status": "active"},
    {"brand": "Google", "series": "Pixel Watch 3", "model": "Pixel Watch 3 45mm", "category": "wearable", "tier": 1, "is_google": True, "listino_eur": 399.0, "status": "active"},
    # Accessori
    {"brand": "Google", "series": "Pixel Accessories", "model": "Caricatore USB-C 30W Pixel", "category": "accessory", "tier": 1, "is_google": True, "listino_eur": 35.0, "status": "active"},
    {"brand": "Google", "series": "Pixel Accessories", "model": "Caricatore USB-C 45W Pixel", "category": "accessory", "tier": 1, "is_google": True, "listino_eur": 45.0, "status": "active"},
    {"brand": "Google", "series": "Pixel Accessories", "model": "Pixel Stand 2a generazione", "category": "accessory", "tier": 1, "is_google": True, "listino_eur": 79.0, "status": "active"},
    {"brand": "Google", "series": "Pixel Accessories", "model": "Cover ufficiale Pixel 9", "category": "accessory", "tier": 1, "is_google": True, "listino_eur": 35.0, "status": "active"},
    {"brand": "Google", "series": "Pixel Accessories", "model": "Cover ufficiale Pixel 10", "category": "accessory", "tier": 1, "is_google": True, "listino_eur": 35.0, "status": "active"},

    # ========================
    # GOOGLE PIXEL — TIER 2
    # ========================
    {"brand": "Google", "series": "Pixel 8", "model": "Pixel 8", "category": "smartphone", "tier": 2, "is_google": True, "listino_eur": 699.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel 8", "model": "Pixel 8 Pro", "category": "smartphone", "tier": 2, "is_google": True, "listino_eur": 1099.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel 8", "model": "Pixel 8a", "category": "smartphone", "tier": 2, "is_google": True, "listino_eur": 499.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel 7", "model": "Pixel 7", "category": "smartphone", "tier": 2, "is_google": True, "listino_eur": 599.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel 7", "model": "Pixel 7 Pro", "category": "smartphone", "tier": 2, "is_google": True, "listino_eur": 899.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel 7", "model": "Pixel 7a", "category": "smartphone", "tier": 2, "is_google": True, "listino_eur": 499.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel Buds", "model": "Pixel Buds Pro gen1", "category": "earable", "tier": 2, "is_google": True, "listino_eur": 219.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel Watch", "model": "Pixel Watch 1", "category": "wearable", "tier": 2, "is_google": True, "listino_eur": 349.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel Watch", "model": "Pixel Watch 2", "category": "wearable", "tier": 2, "is_google": True, "listino_eur": 349.0, "status": "eol"},
    {"brand": "Google", "series": "Pixel Accessories", "model": "Cover ufficiale Pixel 8", "category": "accessory", "tier": 2, "is_google": True, "listino_eur": 35.0, "status": "eol"},

    # ========================
    # SAMSUNG — TIER 1
    # ========================
    {"brand": "Samsung", "series": "Galaxy S25", "model": "Galaxy S25", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 879.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy S25", "model": "Galaxy S25+", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1099.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy S25", "model": "Galaxy S25 Ultra", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1459.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy S25", "model": "Galaxy S25 FE", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 749.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy A", "model": "Galaxy A55", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 449.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy A", "model": "Galaxy A35", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 329.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy Buds", "model": "Galaxy Buds3 Pro", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 249.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy Buds", "model": "Galaxy Buds3", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 149.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy Buds", "model": "Galaxy Buds FE", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 99.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy Watch", "model": "Galaxy Watch 7 40mm", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 299.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy Watch", "model": "Galaxy Watch 7 44mm", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 329.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy Watch", "model": "Galaxy Watch Ultra", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 649.0, "status": "active"},
    {"brand": "Samsung", "series": "Galaxy Watch", "model": "Galaxy Watch FE", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 199.0, "status": "active"},
    {"brand": "Samsung", "series": "Samsung Accessories", "model": "Caricatore wireless Samsung 15W", "category": "accessory", "tier": 1, "is_google": False, "listino_eur": 29.0, "status": "active"},
    {"brand": "Samsung", "series": "Samsung Accessories", "model": "Cover Galaxy S25", "category": "accessory", "tier": 1, "is_google": False, "listino_eur": 29.0, "status": "active"},

    # SAMSUNG — TIER 2
    {"brand": "Samsung", "series": "Galaxy S24", "model": "Galaxy S24", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 879.0, "status": "eol"},
    {"brand": "Samsung", "series": "Galaxy S24", "model": "Galaxy S24+", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 1099.0, "status": "eol"},
    {"brand": "Samsung", "series": "Galaxy S24", "model": "Galaxy S24 Ultra", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 1419.0, "status": "eol"},
    {"brand": "Samsung", "series": "Galaxy Buds", "model": "Galaxy Buds2 Pro", "category": "earable", "tier": 2, "is_google": False, "listino_eur": 229.0, "status": "eol"},
    {"brand": "Samsung", "series": "Galaxy Watch", "model": "Galaxy Watch 6", "category": "wearable", "tier": 2, "is_google": False, "listino_eur": 299.0, "status": "eol"},

    # ========================
    # APPLE — TIER 1
    # ========================
    {"brand": "Apple", "series": "iPhone 17", "model": "iPhone 17", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 979.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 17", "model": "iPhone 17 Air", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1099.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 17", "model": "iPhone 17 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1239.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 17", "model": "iPhone 17 Pro Max", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1479.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 929.0, "status": "active"},
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16e", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 679.0, "status": "active"},
    {"brand": "Apple", "series": "AirPods", "model": "AirPods 4", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 149.0, "status": "active"},
    {"brand": "Apple", "series": "AirPods", "model": "AirPods Pro 3", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 279.0, "status": "active"},
    {"brand": "Apple", "series": "AirPods", "model": "AirPods Max USB-C", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 579.0, "status": "active"},
    {"brand": "Apple", "series": "Apple Watch", "model": "Apple Watch Series 10 40mm", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 449.0, "status": "active"},
    {"brand": "Apple", "series": "Apple Watch", "model": "Apple Watch Series 10 44mm", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 479.0, "status": "active"},
    {"brand": "Apple", "series": "Apple Watch", "model": "Apple Watch Ultra 2", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 799.0, "status": "active"},
    {"brand": "Apple", "series": "Apple Accessories", "model": "MagSafe charger", "category": "accessory", "tier": 1, "is_google": False, "listino_eur": 45.0, "status": "active"},
    {"brand": "Apple", "series": "Apple Accessories", "model": "Cover iPhone 17 serie", "category": "accessory", "tier": 1, "is_google": False, "listino_eur": 55.0, "status": "active"},

    # APPLE — TIER 2
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16 Pro", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 1179.0, "status": "eol"},
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16 Pro Max", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 1429.0, "status": "eol"},
    {"brand": "Apple", "series": "iPhone 16", "model": "iPhone 16 Plus", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 1059.0, "status": "eol"},
    {"brand": "Apple", "series": "AirPods", "model": "AirPods 3", "category": "earable", "tier": 2, "is_google": False, "listino_eur": 179.0, "status": "eol"},
    {"brand": "Apple", "series": "Apple Watch", "model": "Apple Watch Series 9", "category": "wearable", "tier": 2, "is_google": False, "listino_eur": 429.0, "status": "eol"},

    # ========================
    # HONOR — TIER 1
    # ========================
    {"brand": "Honor", "series": "Magic7", "model": "Honor Magic7 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 799.0, "status": "active"},
    {"brand": "Honor", "series": "Magic7", "model": "Honor Magic7 Lite", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 299.0, "status": "active"},
    {"brand": "Honor", "series": "Honor 400", "model": "Honor 400", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 399.0, "status": "active"},
    {"brand": "Honor", "series": "Honor 400", "model": "Honor 400 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 549.0, "status": "active"},
    {"brand": "Honor", "series": "Honor Earbuds", "model": "Honor Earbuds X7", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 49.0, "status": "active"},
    {"brand": "Honor", "series": "Honor Earbuds", "model": "Honor Magic Earbuds Pro", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 99.0, "status": "active"},
    {"brand": "Honor", "series": "Honor Watch", "model": "Honor Watch 5", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 149.0, "status": "active"},
    {"brand": "Honor", "series": "Honor Band", "model": "Honor Band 9", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 49.0, "status": "active"},

    # HONOR — TIER 2
    {"brand": "Honor", "series": "Magic6", "model": "Honor Magic6 Pro", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 799.0, "status": "eol"},
    {"brand": "Honor", "series": "Honor 200", "model": "Honor 200", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 449.0, "status": "eol"},
    {"brand": "Honor", "series": "Honor 200", "model": "Honor 200 Pro", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 599.0, "status": "eol"},

    # ========================
    # OPPO — TIER 1
    # ========================
    {"brand": "OPPO", "series": "Find X9", "model": "OPPO Find X9 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 999.0, "status": "active"},
    {"brand": "OPPO", "series": "Reno13", "model": "OPPO Reno13", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 399.0, "status": "active"},
    {"brand": "OPPO", "series": "Reno13", "model": "OPPO Reno13 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 549.0, "status": "active"},
    {"brand": "OPPO", "series": "OPPO Enco", "model": "OPPO Enco X3 Pro", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 199.0, "status": "active"},
    {"brand": "OPPO", "series": "OPPO Enco", "model": "OPPO Enco Air4 Pro", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 79.0, "status": "active"},
    {"brand": "OPPO", "series": "OPPO Watch", "model": "OPPO Watch X2", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 279.0, "status": "active"},

    # OPPO — TIER 2
    {"brand": "OPPO", "series": "Find X8", "model": "OPPO Find X8 Pro", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 1099.0, "status": "eol"},
    {"brand": "OPPO", "series": "Reno12", "model": "OPPO Reno12", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 379.0, "status": "eol"},
    {"brand": "OPPO", "series": "OPPO Enco", "model": "OPPO Enco X2", "category": "earable", "tier": 2, "is_google": False, "listino_eur": 149.0, "status": "eol"},

    # ========================
    # XIAOMI — TIER 1
    # ========================
    {"brand": "Xiaomi", "series": "Xiaomi 15", "model": "Xiaomi 15", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 799.0, "status": "active"},
    {"brand": "Xiaomi", "series": "Xiaomi 15", "model": "Xiaomi 15 Ultra", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1299.0, "status": "active"},
    {"brand": "Xiaomi", "series": "Xiaomi 15T", "model": "Xiaomi 15T", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 549.0, "status": "active"},
    {"brand": "Xiaomi", "series": "Xiaomi 15T", "model": "Xiaomi 15T Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 699.0, "status": "active"},
    {"brand": "Xiaomi", "series": "Xiaomi Buds", "model": "Xiaomi Buds 5 Pro", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 169.0, "status": "active"},
    {"brand": "Xiaomi", "series": "Xiaomi Buds", "model": "Xiaomi Buds 5", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 79.0, "status": "active"},
    {"brand": "Xiaomi", "series": "Xiaomi Watch", "model": "Xiaomi Watch S4", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 199.0, "status": "active"},
    {"brand": "Xiaomi", "series": "Xiaomi Watch", "model": "Xiaomi Watch 2 Pro", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 249.0, "status": "active"},

    # ========================
    # REDMI — TIER 1
    # ========================
    {"brand": "Redmi", "series": "Redmi Note 15", "model": "Redmi Note 15 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 349.0, "status": "active"},
    {"brand": "Redmi", "series": "Redmi Note 15", "model": "Redmi Note 15 Pro+", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 449.0, "status": "active"},
    {"brand": "Redmi", "series": "Redmi Buds", "model": "Redmi Buds 6 Pro", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 59.0, "status": "active"},
    {"brand": "Redmi", "series": "Redmi Watch", "model": "Redmi Watch 5", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 69.0, "status": "active"},

    # ========================
    # POCO — TIER 1
    # ========================
    {"brand": "POCO", "series": "POCO F7", "model": "POCO F7", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 399.0, "status": "active"},
    {"brand": "POCO", "series": "POCO F7", "model": "POCO F7 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 499.0, "status": "active"},

    # ========================
    # XIAOMI/REDMI — TIER 2
    # ========================
    {"brand": "Xiaomi", "series": "Xiaomi 14", "model": "Xiaomi 14", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 799.0, "status": "eol"},
    {"brand": "Xiaomi", "series": "Xiaomi 14T", "model": "Xiaomi 14T", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 549.0, "status": "eol"},
    {"brand": "Redmi", "series": "Redmi Note 14", "model": "Redmi Note 14 Pro", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 329.0, "status": "eol"},
    {"brand": "Xiaomi", "series": "Xiaomi Buds", "model": "Xiaomi Buds 4 Pro", "category": "earable", "tier": 2, "is_google": False, "listino_eur": 149.0, "status": "eol"},
    {"brand": "Xiaomi", "series": "Xiaomi Watch", "model": "Xiaomi Watch S3", "category": "wearable", "tier": 2, "is_google": False, "listino_eur": 149.0, "status": "eol"},

    # ========================
    # MOTOROLA — TIER 1
    # ========================
    {"brand": "Motorola", "series": "Edge 60", "model": "Motorola Edge 60", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 599.0, "status": "active"},
    {"brand": "Motorola", "series": "Edge 60", "model": "Motorola Edge 60 Pro", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 799.0, "status": "active"},
    {"brand": "Motorola", "series": "Edge 60", "model": "Motorola Edge 60 Fusion", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 399.0, "status": "active"},
    {"brand": "Motorola", "series": "Razr 50", "model": "Motorola Razr 50", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 899.0, "status": "active"},
    {"brand": "Motorola", "series": "Razr 50", "model": "Motorola Razr 50 Ultra", "category": "smartphone", "tier": 1, "is_google": False, "listino_eur": 1199.0, "status": "active"},
    {"brand": "Motorola", "series": "Moto Buds", "model": "Moto Buds+", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 129.0, "status": "active"},
    {"brand": "Motorola", "series": "Moto Buds", "model": "Moto Buds Loop", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 79.0, "status": "active"},
    {"brand": "Motorola", "series": "Moto Buds", "model": "Moto Buds Fit", "category": "earable", "tier": 1, "is_google": False, "listino_eur": 69.0, "status": "active"},
    {"brand": "Motorola", "series": "Moto Watch", "model": "Moto Watch 70", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 99.0, "status": "active"},
    {"brand": "Motorola", "series": "Moto Watch", "model": "Moto Watch 200", "category": "wearable", "tier": 1, "is_google": False, "listino_eur": 179.0, "status": "active"},

    # MOTOROLA — TIER 2
    {"brand": "Motorola", "series": "Edge 50", "model": "Motorola Edge 50", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 499.0, "status": "eol"},
    {"brand": "Motorola", "series": "Edge 50", "model": "Motorola Edge 50 Pro", "category": "smartphone", "tier": 2, "is_google": False, "listino_eur": 699.0, "status": "eol"},
    {"brand": "Motorola", "series": "Moto Buds", "model": "Moto Buds 2023", "category": "earable", "tier": 2, "is_google": False, "listino_eur": 49.0, "status": "eol"},
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

        session.commit()
        logger.info("Seed complete: %d created, %d updated, %d total in catalog", created, updated, len(CATALOG))


if __name__ == "__main__":
    seed_catalog()
