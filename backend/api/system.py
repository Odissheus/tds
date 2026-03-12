"""
System API — status, logs, health.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.models.product import Product, StatusEnum
from backend.models.scrape_log import ScrapeLog, ScrapeStatusEnum

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger("tds.api.system")


@router.get("/status")
async def system_status(session: AsyncSession = Depends(get_async_session)):
    """Get system status overview."""
    total_products = await session.execute(
        select(func.count(Product.id)).where(Product.status != StatusEnum.disabled)
    )
    total = total_products.scalar()

    google_products = await session.execute(
        select(func.count(Product.id)).where(Product.is_google == True, Product.status != StatusEnum.disabled)
    )
    google_count = google_products.scalar()

    last_scrape = await session.execute(
        select(ScrapeLog.scraped_at).order_by(ScrapeLog.scraped_at.desc()).limit(1)
    )
    last_scrape_time = last_scrape.scalar()

    alert_products = await session.execute(
        select(Product).where(Product.not_found_streak >= 3, Product.status != StatusEnum.disabled)
    )
    alerts = alert_products.scalars().all()

    return {
        "status": "active",
        "total_products_monitored": total,
        "google_products": google_count,
        "competitor_products": total - google_count if total else 0,
        "retailers": ["euronics", "unieuro", "mediaworld"],
        "last_scrape": last_scrape_time.isoformat() if last_scrape_time else None,
        "alerts": [
            {
                "product_id": str(p.id),
                "brand": p.brand,
                "model": p.model,
                "not_found_streak": p.not_found_streak,
            }
            for p in alerts
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/logs")
async def scrape_logs(
    limit: int = 50,
    session: AsyncSession = Depends(get_async_session),
):
    """Get recent scrape logs."""
    result = await session.execute(
        select(ScrapeLog, Product)
        .join(Product, ScrapeLog.product_id == Product.id)
        .order_by(ScrapeLog.scraped_at.desc())
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "id": str(log.id),
            "product": f"{product.brand} {product.model}",
            "retailer": log.retailer,
            "status": log.status.value,
            "error_message": log.error_message,
            "scraped_at": log.scraped_at.isoformat(),
        }
        for log, product in rows
    ]


@router.post("/mark-eol/{product_id}")
async def mark_product_eol(
    product_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Mark a product as EOL."""
    import uuid

    result = await session.execute(select(Product).where(Product.id == uuid.UUID(product_id)))
    product = result.scalar_one_or_none()

    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")

    product.status = StatusEnum.eol
    product.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return {"status": "ok", "message": f"{product.brand} {product.model} marked as EOL"}
