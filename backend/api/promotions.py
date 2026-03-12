"""
Promotions API — query promotions data.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
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
    url_fonte: str
    settimana: str
    scraped_at: str


def _get_current_week() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"


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
            url_fonte=promo.url_fonte,
            settimana=promo.settimana,
            scraped_at=promo.scraped_at.isoformat(),
        )
        for promo, product in rows
    ]
