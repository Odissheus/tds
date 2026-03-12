"""
MediaWorld.it scraper — DISABLED due to persistent CAPTCHA blocking.
Returns empty results immediately to avoid wasting time.
"""
import logging
from typing import List

from backend.scrapers.base_scraper import BaseScraper, PromoResult

logger = logging.getLogger("tds.scraper.mediaworld")


class MediaWorldScraper(BaseScraper):
    retailer_name = "mediaworld"

    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        """MediaWorld blocks with CAPTCHA — skip immediately."""
        logger.info(
            "[mediaworld] SKIPPED %s %s — CAPTCHA blocked, returning empty",
            product_brand, product_model,
        )
        return []
