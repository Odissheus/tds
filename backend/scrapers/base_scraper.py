import logging
import asyncio
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from playwright.async_api import Browser, Page, async_playwright

logger = logging.getLogger("tds.scraper")

RETAILERS = {
    "euronics": {
        "base_url": "https://www.euronics.it",
        "search_url": "https://www.euronics.it/search?query={query}",
        "promo_url": "https://www.euronics.it/offerte/",
        "variants": ["Tufano", "Di Mo", "Bruno", "Comet", "IRES", "Butali"],
    },
    "unieuro": {
        "base_url": "https://www.unieuro.it",
        "search_url": "https://www.unieuro.it/online/ricerca?q={query}",
        "promo_url": "https://www.unieuro.it/online/offerte/",
    },
    "mediaworld": {
        "base_url": "https://www.mediaworld.it",
        "search_url": "https://www.mediaworld.it/search/{query}",
        "promo_url": "https://www.mediaworld.it/it/offerte",
    },
    "amazon": {
        "base_url": "https://www.amazon.it",
        "search_url": "https://www.amazon.it/s?k={query}",
        "promo_url": "https://www.amazon.it/deals",
    },
}


class PromoResult:
    """Data class for a scraped promotion result."""

    def __init__(
        self,
        retailer: str,
        retailer_variant: Optional[str],
        prezzo_originale: float,
        prezzo_promo: float,
        sconto_percentuale: float,
        data_inizio: date,
        data_fine: Optional[date],
        url_fonte: str,
        promo_tag: Optional[str] = None,
    ):
        self.retailer = retailer
        self.retailer_variant = retailer_variant
        self.prezzo_originale = prezzo_originale
        self.prezzo_promo = prezzo_promo
        self.sconto_percentuale = sconto_percentuale
        self.data_inizio = data_inizio
        self.data_fine = data_fine
        self.url_fonte = url_fonte
        self.promo_tag = promo_tag


class BaseScraper(ABC):
    """Base class for all retailer scrapers using Playwright."""

    retailer_name: str = ""

    def __init__(self):
        self.config = RETAILERS.get(self.retailer_name, {})
        self.browser: Optional[Browser] = None

    async def init_browser(self):
        """Initialize Playwright browser."""
        pw = await async_playwright().start()
        self.browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._pw = pw

    async def close_browser(self):
        """Close browser and Playwright."""
        if self.browser:
            await self.browser.close()
        if hasattr(self, "_pw") and self._pw:
            await self._pw.stop()

    async def new_page(self) -> Page:
        """Create a new browser page with common settings."""
        if not self.browser:
            await self.init_browser()
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="it-IT",
        )
        page = await context.new_page()
        page.set_default_timeout(30000)
        return page

    def _parse_price(self, text: str) -> Optional[float]:
        """Parse Italian price format (1.299,99 €) to float."""
        if not text:
            return None
        cleaned = text.strip().replace("€", "").replace("\xa0", "").strip()
        cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _calc_discount(self, original: float, promo: float) -> float:
        """Calculate discount percentage."""
        if original <= 0:
            return 0.0
        return round(((original - promo) / original) * 100, 1)

    def _current_week(self) -> str:
        """Return current ISO week string like '2026-W11'."""
        now = datetime.now(timezone.utc)
        return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"

    @abstractmethod
    async def search_product(self, product_model: str, product_brand: str) -> List[PromoResult]:
        """Search for a product and return promo results if found."""
        ...

    async def scrape_with_retry(
        self, product_model: str, product_brand: str, max_retries: int = 3
    ) -> List[PromoResult]:
        """Scrape with exponential backoff retry."""
        for attempt in range(max_retries):
            try:
                results = await self.search_product(product_model, product_brand)
                return results
            except Exception as e:
                wait_time = 2 ** attempt
                logger.warning(
                    "Scrape attempt %d/%d failed for %s on %s: %s. Retrying in %ds.",
                    attempt + 1,
                    max_retries,
                    product_model,
                    self.retailer_name,
                    str(e),
                    wait_time,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    raise
        return []
