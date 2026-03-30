import logging
import asyncio
import re
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from playwright.async_api import Browser, Page, async_playwright

logger = logging.getLogger("tds.scraper")

RETAILERS = {
    "euronics": {
        "base_url": "https://www.euronics.it",
        "search_url": "https://www.euronics.it/search?q={query}",
        "promo_url": "https://www.euronics.it/offerte/",
        "variants": ["Tufano", "Di Mo", "Bruno", "Comet", "IRES", "Butali"],
    },
    "unieuro": {
        "base_url": "https://www.unieuro.it",
        "search_url": "https://www.unieuro.it/online/cerca?q={query}",
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

# Regex for Italian prices: €1.299,99 or 1.299,99€ or 1299,99 or €1299
PRICE_RE = re.compile(
    r"€\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)"
    r"|(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*€"
)

STORAGE_COMBO_RE = re.compile(r'\b(\d+)[+/](\d+)\s*[Gg][Bb]')
STORAGE_RE = re.compile(r'\b(\d+)\s*(?:GB|gb)', re.IGNORECASE)
STORAGE_TB_RE = re.compile(r'\b(\d+)\s*(?:TB|tb)', re.IGNORECASE)
VALID_STORAGE_VALUES = (64, 128, 256, 512, 1024)

BUNDLE_KEYWORDS = [
    "con caricatore", "with charger", "+ caricatore",
    "con cuffie", "con auricolari", "con buds",
    "con cover", "con custodia", "con case",
    "con smartwatch", "con watch",
    "kit ", "bundle", "pack ",
    "+ moto buds", "+ buds", "+ watch",
    "starter kit", "special pack",
    "combo", "inclus",
]

# Price bounds per category for validation
CATEGORY_PRICE_BOUNDS = {
    "smartphone": (150, 2500),
    "accessory": (5, 300),
    "hearable": (20, 500),
    "wearable": (50, 800),
}


def extract_storage_gb(title: str) -> Optional[int]:
    """Extract storage in GB from product title. Returns None if not found."""
    if not title:
        return None
    # Pattern: 12+256GB -> takes the second (storage) number
    m = STORAGE_COMBO_RE.search(title)
    if m:
        val = int(m.group(2))
        if val in VALID_STORAGE_VALUES:
            return val
    # Pattern: 1TB
    m = STORAGE_TB_RE.search(title)
    if m:
        return int(m.group(1)) * 1024
    # Pattern: 256GB
    m = STORAGE_RE.search(title)
    if m:
        val = int(m.group(1))
        if val in VALID_STORAGE_VALUES:
            return val
    return None


def detect_bundle(title: str) -> tuple:
    """Detect if a product listing is a bundle. Returns (is_bundle, bundle_description)."""
    if not title:
        return False, None
    title_lower = title.lower()
    for kw in BUNDLE_KEYWORDS:
        if kw in title_lower:
            return True, title[:500]
    return False, None


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
        storage_gb: Optional[int] = None,
        is_bundle: bool = False,
        bundle_description: Optional[str] = None,
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
        self.storage_gb = storage_gb
        self.is_bundle = is_bundle
        self.bundle_description = bundle_description


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
                "Chrome/124.0.0.0 Safari/537.36"
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
            val = float(cleaned)
            return val if val > 0 else None
        except (ValueError, TypeError):
            return None

    def _extract_prices_from_text(self, text: str) -> List[float]:
        """Extract all Italian-format prices from a text string."""
        prices = []
        for m in PRICE_RE.finditer(text):
            raw = m.group(1) or m.group(2)
            p = self._parse_price(raw)
            if p and p > 1:
                prices.append(p)
        return sorted(set(prices))

    def _calc_discount(self, original: float, promo: float) -> float:
        """Calculate discount percentage."""
        if original <= 0:
            return 0.0
        return round(((original - promo) / original) * 100, 1)

    def _current_week(self) -> str:
        """Return current ISO week string like '2026-W11'."""
        now = datetime.now(timezone.utc)
        return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"

    def _is_matching_product(self, title: str, model: str, brand: str) -> bool:
        """Check if title matches the product we're looking for."""
        if not title:
            return False
        title_lower = title.lower()
        model_parts = model.lower().split()
        brand_lower = brand.lower()

        if brand_lower not in title_lower:
            return False

        match_count = sum(1 for part in model_parts if part in title_lower)
        return match_count >= max(1, len(model_parts) * 0.5)

    async def _dismiss_cookies(self, page: Page):
        """Try to dismiss cookie consent banners."""
        cookie_selectors = [
            "#onetrust-accept-btn-handler",
            "[id*='cookie'] button[id*='accept']",
            "button[id*='accept']",
            "[class*='cookie'] button",
            "#sp-cc-accept",
            "button:has-text('Accetta')",
            "button:has-text('Accetto')",
            "button:has-text('Accept')",
        ]
        for sel in cookie_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    logger.info("[%s] Dismissed cookie banner via %s", self.retailer_name, sel)
                    return
            except Exception:
                continue

    async def _log_page_state(self, page: Page, context: str):
        """Log the current page state for debugging."""
        try:
            title = await page.title()
            url = page.url
            body_text = await page.evaluate(
                "() => (document.body?.innerText || '').substring(0, 300)"
            )
            logger.info(
                "[%s][%s] URL: %s | Title: %s | Preview: %.200s",
                self.retailer_name, context, url, title, body_text.replace("\n", " "),
            )
        except Exception as e:
            logger.warning("[%s][%s] Could not log page state: %s", self.retailer_name, context, e)

    async def _js_extract_products(self, page: Page, product_model: str, product_brand: str) -> List[dict]:
        """JavaScript-based fallback extraction — finds products by scanning all text on page."""
        try:
            data = await page.evaluate("""(args) => {
                const [brand, model] = args;
                const brandLower = brand.toLowerCase();
                const modelParts = model.toLowerCase().split(' ');
                const results = [];

                // Find all links that could be product links
                const links = document.querySelectorAll('a[href]');
                for (const link of links) {
                    const text = (link.textContent || '').trim();
                    const textLower = text.toLowerCase();

                    // Check if this link mentions our product
                    if (!textLower.includes(brandLower)) continue;
                    const matchCount = modelParts.filter(p => textLower.includes(p)).length;
                    if (matchCount < Math.max(1, modelParts.length * 0.5)) continue;

                    // Found a matching product link — look for prices in parent/siblings
                    let container = link.closest('[class*="product"], [class*="card"], [class*="tile"], article, li') || link.parentElement?.parentElement;
                    if (!container) continue;

                    const containerText = container.textContent || '';

                    // Extract prices with regex
                    const priceRe = /€\\s*(\\d{1,3}(?:\\.\\d{3})*(?:,\\d{1,2})?)/g;
                    const priceRe2 = /(\\d{1,3}(?:\\.\\d{3})*(?:,\\d{1,2}))\\s*€/g;
                    const prices = [];

                    let m;
                    while ((m = priceRe.exec(containerText)) !== null) {
                        prices.push(m[1]);
                    }
                    while ((m = priceRe2.exec(containerText)) !== null) {
                        prices.push(m[1]);
                    }

                    if (prices.length === 0) continue;

                    results.push({
                        title: text.substring(0, 200),
                        href: link.href || '',
                        prices: prices,
                        containerText: containerText.substring(0, 500),
                    });
                }
                return results;
            }""", [product_brand, product_model])
            return data or []
        except Exception as e:
            logger.warning("[%s] JS extraction failed: %s", self.retailer_name, e)
            return []

    @abstractmethod
    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        """Search for a product and return promo results if found."""
        ...

    async def scrape_with_retry(
        self, product_model: str, product_brand: str, listino_eur: float = 0, max_retries: int = 2
    ) -> List[PromoResult]:
        """Scrape with exponential backoff retry."""
        for attempt in range(max_retries):
            try:
                results = await self.search_product(product_model, product_brand, listino_eur)
                return results
            except Exception as e:
                wait_time = 2 ** attempt
                logger.warning(
                    "[%s] Attempt %d/%d failed for %s %s: %s. Retrying in %ds.",
                    self.retailer_name,
                    attempt + 1,
                    max_retries,
                    product_brand,
                    product_model,
                    str(e),
                    wait_time,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    raise
        return []
