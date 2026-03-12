"""
Scraper Agent — orchestrates scraping across all retailers for all active products.
Triggered by Celery worker (scheduler: Wed/Thu 08:00) or manually via API.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import sync_session_factory
from backend.models.product import Product, StatusEnum
from backend.models.promotion import Promotion
from backend.models.scrape_log import ScrapeLog, ScrapeStatusEnum
from backend.scrapers.euronics import EuronicsScraper
from backend.scrapers.unieuro import UnieuroScraper
from backend.scrapers.mediaworld import MediaWorldScraper
from backend.scrapers.base_scraper import BaseScraper, PromoResult

logger = logging.getLogger("tds.agent.scraper")

SCRAPER_CLASSES: List[type] = [EuronicsScraper, UnieuroScraper, MediaWorldScraper]


async def run_scraping_for_product(product_id: str) -> dict:
    """Run scraping for a single product across all retailers."""
    with sync_session_factory() as session:
        product = session.get(Product, product_id)
        if not product:
            return {"error": f"Product {product_id} not found"}

        results = await _scrape_product(session, product)
        session.commit()
        return results


async def run_full_scraping() -> dict:
    """Run scraping for all active products across all retailers."""
    logger.info("Starting full scraping run")
    stats = {"total_products": 0, "total_found": 0, "total_not_found": 0, "total_errors": 0}

    with sync_session_factory() as session:
        products = session.execute(
            select(Product).where(Product.status != StatusEnum.disabled)
        ).scalars().all()

        stats["total_products"] = len(products)
        logger.info("Scraping %d products", len(products))

        for product in products:
            try:
                result = await _scrape_product(session, product)
                stats["total_found"] += result.get("found", 0)
                stats["total_not_found"] += result.get("not_found", 0)
                stats["total_errors"] += result.get("errors", 0)
            except Exception as e:
                logger.error("Error scraping product %s: %s", product.model, str(e))
                stats["total_errors"] += 1

        session.commit()

    logger.info(
        "Full scraping complete: %d products, %d found, %d not found, %d errors",
        stats["total_products"],
        stats["total_found"],
        stats["total_not_found"],
        stats["total_errors"],
    )
    return stats


async def _scrape_product(session: Session, product: Product) -> dict:
    """Scrape a single product across all retailers."""
    result = {"found": 0, "not_found": 0, "errors": 0}
    now = datetime.now(timezone.utc)
    week_str = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"

    for scraper_cls in SCRAPER_CLASSES:
        scraper: BaseScraper = scraper_cls()
        try:
            await scraper.init_browser()
            promos: List[PromoResult] = await scraper.scrape_with_retry(
                product.model, product.brand
            )

            if promos:
                for promo in promos:
                    promotion = Promotion(
                        product_id=product.id,
                        retailer=promo.retailer,
                        retailer_variant=promo.retailer_variant,
                        prezzo_originale=promo.prezzo_originale,
                        prezzo_promo=promo.prezzo_promo,
                        sconto_percentuale=promo.sconto_percentuale,
                        data_inizio=promo.data_inizio,
                        data_fine=promo.data_fine,
                        url_fonte=promo.url_fonte,
                        settimana=week_str,
                        scraped_at=now,
                    )
                    session.add(promotion)

                log_entry = ScrapeLog(
                    product_id=product.id,
                    retailer=scraper.retailer_name,
                    status=ScrapeStatusEnum.found,
                    scraped_at=now,
                )
                session.add(log_entry)

                product.not_found_streak = 0
                result["found"] += 1
                logger.info(
                    "Found %d promos for %s on %s",
                    len(promos),
                    product.model,
                    scraper.retailer_name,
                )
            else:
                log_entry = ScrapeLog(
                    product_id=product.id,
                    retailer=scraper.retailer_name,
                    status=ScrapeStatusEnum.not_found,
                    scraped_at=now,
                )
                session.add(log_entry)

                product.not_found_streak += 1
                result["not_found"] += 1

                if product.not_found_streak >= 3:
                    await _send_not_found_alert(product)

        except Exception as e:
            logger.error(
                "Error scraping %s on %s: %s",
                product.model,
                scraper.retailer_name,
                str(e),
            )
            log_entry = ScrapeLog(
                product_id=product.id,
                retailer=scraper.retailer_name,
                status=ScrapeStatusEnum.error,
                error_message=str(e)[:1000],
                scraped_at=now,
            )
            session.add(log_entry)
            result["errors"] += 1

        finally:
            await scraper.close_browser()

    return result


async def _send_not_found_alert(product: Product):
    """Send alert email when product not found for 3+ consecutive weeks."""
    try:
        from backend.agents.email_agent import send_alert_email

        await send_alert_email(
            subject=f"⚠️ TDS Alert: {product.model} non trovato da {product.not_found_streak} settimane — verificare status",
            body=f"""
            <h2>⚠️ Prodotto non trovato</h2>
            <p><strong>{product.brand} {product.model}</strong> non è stato trovato in promozione
            da <strong>{product.not_found_streak} settimane consecutive</strong>.</p>
            <p>Verifica lo status del prodotto nella dashboard TDS.</p>
            <p>Tier: {product.tier} | Categoria: {product.category.value} | Status: {product.status.value}</p>
            <hr>
            <p><small>TDS Tech Deep Search — React SRL</small></p>
            """,
        )
    except Exception as e:
        logger.error("Failed to send not-found alert for %s: %s", product.model, str(e))
