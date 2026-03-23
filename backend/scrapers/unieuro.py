"""
Unieuro.it scraper — multi-URL strategy with homepage search fallback.

Unieuro uses an Angular/Ionic SPA. Direct URL search may return 404.
Tries multiple search URLs, then falls back to homepage search input.
"""
import logging
import re
from datetime import date
from typing import List, Optional

from backend.scrapers.base_scraper import BaseScraper, PromoResult, extract_storage_gb, detect_bundle

logger = logging.getLogger("tds.scraper.unieuro")

PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")

# Search URLs to try in order
SEARCH_URLS = [
    "https://www.unieuro.it/online/cerca?q={query}",
    "https://www.unieuro.it/search?q={query}",
    "https://www.unieuro.it/ricerca?q={query}",
    "https://www.unieuro.it/online/search?q={query}",
]

# Search input selectors to try on homepage
SEARCH_INPUT_SELECTORS = [
    'input[placeholder*="cerchi"]',
    'input[placeholder*="Cerca"]',
    'input[type="search"]',
    'input[name="q"]',
    'input[id*="search"]',
    '#searchInput',
    'input[class*="search"]',
]

MIN_PRICE = 15.0
MAX_DISCOUNT = 60.0


class UnieuroScraper(BaseScraper):
    retailer_name = "unieuro"

    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        results: List[PromoResult] = []
        page = await self.new_page()

        try:
            query = f"{product_brand} {product_model}"
            search_landed = False

            # Strategy 1: Try direct search URLs
            for url_template in SEARCH_URLS:
                search_url = url_template.format(query=query.replace(" ", "+"))
                logger.info("[unieuro] Trying URL: %s", search_url)
                try:
                    resp = await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(3000)

                    # Check if page loaded with products (not 404)
                    if resp and resp.status < 400:
                        # Check for product content
                        has_products = await page.evaluate("""() => {
                            const cards = document.querySelectorAll(
                                'app-product, .product-card, .product-tile, ' +
                                '[class*="product-item"], [class*="product-card"]'
                            );
                            return cards.length > 0;
                        }""")
                        if has_products:
                            logger.info("[unieuro] Found products at %s", search_url)
                            search_landed = True
                            break
                        # Also check if there's any price-like content
                        has_prices = await page.evaluate("""() => {
                            const text = document.body.innerText || '';
                            return /\\d{2,3}(?:\\.\\d{3})*,\\d{2}/.test(text);
                        }""")
                        if has_prices:
                            logger.info("[unieuro] Found price content at %s", search_url)
                            search_landed = True
                            break
                except Exception as e:
                    logger.debug("[unieuro] URL %s failed: %s", search_url, e)
                    continue

            # Strategy 2: Homepage search fallback
            if not search_landed:
                logger.info("[unieuro] Direct URLs failed, navigating to homepage")
                await page.goto("https://www.unieuro.it", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                # Dismiss cookies
                try:
                    for cookie_text in ["Accetta tutti", "Accetta", "Accept"]:
                        cookie_btn = await page.query_selector(f"text={cookie_text}")
                        if cookie_btn:
                            await cookie_btn.click()
                            await page.wait_for_timeout(1000)
                            break
                except Exception:
                    pass

                # Find and use search input
                search_input = None
                for sel in SEARCH_INPUT_SELECTORS:
                    search_input = await page.query_selector(sel)
                    if search_input:
                        logger.info("[unieuro] Found search input with selector: %s", sel)
                        break

                if not search_input:
                    logger.warning("[unieuro] No search input found on homepage")
                    return results

                await search_input.click()
                await page.wait_for_timeout(500)
                await search_input.fill(query)
                await page.wait_for_timeout(2000)
                await search_input.press("Enter")
                await page.wait_for_timeout(8000)

                logger.info("[unieuro] After homepage search, URL: %s", page.url)

            await self._dismiss_cookies(page)

            # Extract products via JS
            data = await self._extract_products_js(page, product_brand, product_model)
            logger.info("[unieuro] JS extraction found %d matching products", len(data or []))

            for item in (data or []):
                promo = self._build_promo_from_item(item, listino_eur)
                if promo:
                    results.append(promo)

            # Fallback: full page link scan
            if not results:
                logger.info("[unieuro] Primary extraction found nothing, trying link scan")
                js_products = await self._js_extract_products(page, product_model, product_brand)
                for jp in js_products[:8]:
                    promo = self._build_promo_from_link_scan(jp, product_model, product_brand, listino_eur)
                    if promo:
                        results.append(promo)

        finally:
            await page.close()

        logger.info("[unieuro] Total results for '%s %s': %d", product_brand, product_model, len(results))
        return results

    async def _extract_products_js(self, page, product_brand: str, product_model: str) -> list:
        """Extract products via JavaScript — handles Angular SPA components."""
        try:
            data = await page.evaluate("""(args) => {
                const [brand, model] = args;
                const brandLower = brand.toLowerCase();
                const modelParts = model.toLowerCase().split(' ');
                const results = [];

                // Try multiple card selectors
                const selectors = [
                    'app-product',
                    '.product-card',
                    '.product-tile',
                    '[class*="product-item"]',
                    '[class*="product-card"]',
                    'article[class*="product"]',
                ];

                let cards = [];
                for (const sel of selectors) {
                    cards = document.querySelectorAll(sel);
                    if (cards.length > 0) break;
                }

                for (const card of cards) {
                    // Try multiple title selectors
                    const titleSelectors = [
                        '.product-description',
                        '.product-description p',
                        '.product-name',
                        '.product-title',
                        'h2', 'h3',
                        '[class*="name"]',
                        '[class*="title"]',
                    ];

                    let title = '';
                    for (const ts of titleSelectors) {
                        const el = card.querySelector(ts);
                        if (el && el.textContent.trim().length > 5) {
                            title = el.textContent.trim();
                            break;
                        }
                    }

                    const titleLower = title.toLowerCase();

                    // Check match
                    if (!titleLower.includes(brandLower)) continue;
                    const matchCount = modelParts.filter(p => titleLower.includes(p)).length;
                    if (matchCount < Math.max(1, modelParts.length * 0.5)) continue;

                    // Extract prices from card text
                    const text = card.innerText || '';
                    const priceRe = /(\\d{1,3}(?:\\.\\d{3})*,\\d{2})/g;
                    const prices = [];
                    let m;
                    while ((m = priceRe.exec(text)) !== null) {
                        const raw = m[1].replace(/\\./g, '').replace(',', '.');
                        const val = parseFloat(raw);
                        if (val > 10) prices.push(val);
                    }

                    // Extract link
                    const linkSelectors = [
                        'a.product-link-title',
                        'a[href*="pid"]',
                        'a[href*="/p/"]',
                        'a[href*="/prodotto"]',
                        'a[href]',
                    ];
                    let href = '';
                    for (const ls of linkSelectors) {
                        const linkEl = card.querySelector(ls);
                        if (linkEl) {
                            href = linkEl.getAttribute('href') || '';
                            if (href) break;
                        }
                    }

                    if (prices.length > 0) {
                        results.push({
                            title: title.substring(0, 200),
                            href: href,
                            prices: prices,
                        });
                    }
                }
                return results;
            }""", [product_brand, product_model])
            return data or []
        except Exception as e:
            logger.warning("[unieuro] JS extraction failed: %s", e)
            return []

    def _build_promo_from_item(self, item: dict, listino_eur: float) -> Optional[PromoResult]:
        """Build PromoResult from JS-extracted item."""
        title = item.get("title", "")
        storage = extract_storage_gb(title)
        is_bundle, bundle_desc = detect_bundle(title)

        # Filter prices: remove installment prices (< MIN_PRICE) and sort
        prices = sorted([p for p in item.get("prices", []) if p >= MIN_PRICE])
        if not prices:
            return None

        prezzo_promo = prices[0]
        prezzo_originale = prices[-1] if len(prices) > 1 and prices[-1] > prezzo_promo else None

        if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
            prezzo_originale = listino_eur

        if prezzo_originale is None or prezzo_originale <= prezzo_promo:
            return None

        sconto = self._calc_discount(prezzo_originale, prezzo_promo)

        # Skip implausible discounts (>60% usually means installment price was grabbed)
        if sconto > MAX_DISCOUNT:
            logger.info("[unieuro] SKIPPED (discount too high %.1f%%): %s", sconto, title[:60])
            return None

        href = item.get("href", "")
        url = href if href and href.startswith("http") else (
            f"https://www.unieuro.it{href}" if href else "https://www.unieuro.it"
        )

        logger.info("[unieuro] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                    title[:60], prezzo_originale, prezzo_promo, sconto)

        return PromoResult(
            retailer="unieuro", retailer_variant=None,
            prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
            sconto_percentuale=sconto, data_inizio=date.today(),
            data_fine=None, url_fonte=url, promo_tag="Sconto Unieuro",
            storage_gb=storage, is_bundle=is_bundle, bundle_description=bundle_desc,
        )

    def _build_promo_from_link_scan(
        self, jp: dict, product_model: str, product_brand: str, listino_eur: float
    ) -> Optional[PromoResult]:
        """Build PromoResult from link-scan fallback."""
        title = jp.get("title", "")
        if not self._is_matching_product(title, product_model, product_brand):
            return None

        storage = extract_storage_gb(title)
        is_bundle, bundle_desc = detect_bundle(title)

        prices_raw = jp.get("prices", [])
        prices = []
        for raw in prices_raw:
            p = self._parse_price(raw) if isinstance(raw, str) else raw
            if p and p >= MIN_PRICE:
                prices.append(p)

        if not prices:
            return None

        prices.sort()
        prezzo_promo = prices[0]
        prezzo_originale = prices[-1] if len(prices) > 1 and prices[-1] > prezzo_promo else None

        if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
            prezzo_originale = listino_eur
        if prezzo_originale is None or prezzo_originale <= prezzo_promo:
            return None

        sconto = self._calc_discount(prezzo_originale, prezzo_promo)
        if sconto > MAX_DISCOUNT:
            return None

        href = jp.get("href", "")
        url = href if href and href.startswith("http") else (
            f"https://www.unieuro.it{href}" if href else "https://www.unieuro.it"
        )

        logger.info("[unieuro][link-scan] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                    title[:60], prezzo_originale, prezzo_promo, sconto)

        return PromoResult(
            retailer="unieuro", retailer_variant=None,
            prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
            sconto_percentuale=sconto, data_inizio=date.today(),
            data_fine=None, url_fonte=url, promo_tag="Sconto Unieuro",
            storage_gb=storage, is_bundle=is_bundle, bundle_description=bundle_desc,
        )
