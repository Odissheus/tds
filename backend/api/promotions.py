"""
Promotions API — query promotions data.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.models.product import Product
from backend.models.promotion import Promotion

router = APIRouter(prefix="/api/promotions", tags=["promotions"])
logger = logging.getLogger("tds.api.promotions")


class PromotionOut(BaseModel):
    id: str
    product_id: str
    brand: str
    model: str
    series: str
    category: str
    is_google: bool
    tier: int
    retailer: str
    retailer_variant: Optional[str]
    prezzo_originale: float
    prezzo_promo: float
    sconto_percentuale: float
    data_inizio: str
    data_fine: Optional[str]
    promo_tag: Optional[str]
    url_fonte: str
    settimana: str
    scraped_at: str


def _get_current_week() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"


@router.get("/debug")
async def debug_promotions(session: AsyncSession = Depends(get_async_session)):
    """Diagnostic endpoint — shows what's actually in the DB."""
    current_week = _get_current_week()

    # Total count (no filters)
    total_result = await session.execute(select(func.count(Promotion.id)))
    total_count = total_result.scalar() or 0

    # Count per week
    weeks_result = await session.execute(
        select(Promotion.settimana, func.count(Promotion.id))
        .group_by(Promotion.settimana)
        .order_by(Promotion.settimana.desc())
        .limit(10)
    )
    weeks = [{"week": row[0], "count": row[1]} for row in weeks_result.all()]

    # Count for current week specifically
    current_result = await session.execute(
        select(func.count(Promotion.id)).where(Promotion.settimana == current_week)
    )
    current_count = current_result.scalar() or 0

    # Count per retailer (all time)
    retailers_result = await session.execute(
        select(Promotion.retailer, func.count(Promotion.id))
        .group_by(Promotion.retailer)
    )
    retailers = {row[0]: row[1] for row in retailers_result.all()}

    # Raw SQL check (bypass ORM entirely)
    raw_result = await session.execute(text("SELECT COUNT(*) FROM promotions"))
    raw_count = raw_result.scalar() or 0

    # Check products count
    products_result = await session.execute(text("SELECT COUNT(*) FROM products"))
    products_count = products_result.scalar() or 0

    debug_data = {
        "current_week": current_week,
        "total_promotions_orm": total_count,
        "total_promotions_raw_sql": raw_count,
        "current_week_count": current_count,
        "weeks_in_db": weeks,
        "retailers": retailers,
        "products_count": products_count,
    }

    logger.info("DEBUG promotions: %s", debug_data)
    return debug_data


@router.get("", response_model=List[PromotionOut])
async def list_promotions(
    week: Optional[str] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    retailer: Optional[str] = None,
    tier: Optional[int] = None,
    is_google: Optional[bool] = None,
    session: AsyncSession = Depends(get_async_session),
):
    """List promotions with filters."""
    if not week:
        week = _get_current_week()

    # Diagnostic: count total and for this week
    total_result = await session.execute(select(func.count(Promotion.id)))
    total_count = total_result.scalar() or 0
    week_result = await session.execute(
        select(func.count(Promotion.id)).where(Promotion.settimana == week)
    )
    week_count = week_result.scalar() or 0

    logger.info(
        "GET /api/promotions — week=%s | total_in_db=%d | matching_week=%d",
        week, total_count, week_count,
    )

    # If no results for current week but data exists, log available weeks
    if week_count == 0 and total_count > 0:
        weeks_result = await session.execute(
            select(Promotion.settimana, func.count(Promotion.id))
            .group_by(Promotion.settimana)
            .order_by(Promotion.settimana.desc())
            .limit(5)
        )
        available = [(row[0], row[1]) for row in weeks_result.all()]
        logger.warning(
            "MISMATCH: 0 promos for week=%s but %d total exist. Available weeks: %s",
            week, total_count, available,
        )

    query = (
        select(Promotion, Product)
        .join(Product, Promotion.product_id == Product.id)
        .where(Promotion.settimana == week)
        .order_by(Promotion.retailer, Product.brand, Product.model)
    )

    if brand:
        brands = [b.strip() for b in brand.split(",")]
        query = query.where(Product.brand.in_(brands))
    if category:
        query = query.where(Product.category == category)
    if retailer:
        query = query.where(Promotion.retailer == retailer)
    if tier is not None:
        query = query.where(Product.tier == tier)
    if is_google is not None:
        query = query.where(Product.is_google == is_google)

    results = await session.execute(query)
    rows = results.all()

    # Deduplicate: keep only lowest prezzo_promo per (product_id, retailer)
    best: dict = {}
    for promo, product in rows:
        key = (str(promo.product_id), promo.retailer)
        if key not in best or promo.prezzo_promo < best[key][0].prezzo_promo:
            best[key] = (promo, product)

    deduped = list(best.values())
    logger.info("GET /api/promotions — %d raw, %d after dedup for week=%s", len(rows), len(deduped), week)

    return [
        PromotionOut(
            id=str(promo.id),
            product_id=str(promo.product_id),
            brand=product.brand,
            model=product.model,
            series=product.series,
            category=product.category.value,
            is_google=product.is_google,
            tier=product.tier,
            retailer=promo.retailer,
            retailer_variant=promo.retailer_variant,
            prezzo_originale=promo.prezzo_originale,
            prezzo_promo=promo.prezzo_promo,
            sconto_percentuale=promo.sconto_percentuale,
            data_inizio=str(promo.data_inizio),
            data_fine=str(promo.data_fine) if promo.data_fine else None,
            promo_tag=promo.promo_tag,
            url_fonte=promo.url_fonte,
            settimana=promo.settimana,
            scraped_at=promo.scraped_at.isoformat(),
        )
        for promo, product in deduped
    ]
