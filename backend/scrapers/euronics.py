"""
Euronics.it scraper — multi-strategy extraction for robustness.

Search URL: https://www.euronics.it/search?q={query}
Uses 4 strategies: CSS selectors, JS comprehensive, data-obj JSON, full page scan.
"""
import json
import logging
from datetime import date
from typing import List, Optional

from backend.scrapers.base_scraper import BaseScraper, PromoResult, extract_storage_gb, detect_bundle

logger = logging.getLogger("tds.scraper.euronics")

# Multiple card selector patterns to try
CARD_SELECTORS = [
    ".product-grid .product",
    ".product-list .product-tile",
    "[class*='product-tile']",
    "[class*='product-card']",
    ".search-results .product",
    "article[class*='product']",
]

# Multiple title selectors within a card
TITLE_SELECTORS = [
    ".tile-name",
    ".product-name",
    ".product-title",
    "h2 a",
    "h3 a",
    "[class*='name']",
    "[class*='title']",
]

# Multiple price selectors
PRICE_SELECTORS = [
    ".discount .price-formatted",
    ".price .price-formatted",
    "[class*='price'] [class*='formatted']",
    "[class*='actual-price']",
    "[class*='sale-price']",
    ".price-value",
]

ORIG_PRICE_SELECTORS = [
    ".more-price-details .value",
    "[class*='original-price']",
    "[class*='list-price']",
    "[class*='was-price']",
    "del",
    ".old-price",
]

LINK_SELECTORS = [
    "a.link-pdp",
    "a[href*='/p/']",
    "a[href*='/product']",
    "a[href*='/prodotto']",
    "a[href]",
]

MIN_PRICE = 15.0


class EuronicsScraper(BaseScraper):
    retailer_name = "euronics"

    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        results: List[PromoResult] = []
        page = await self.new_page()

        try:
            query = f"{product_brand} {product_model}"
            search_url = f"https://www.euronics.it/search?q={query.replace(' ', '+')}"

            logger.info("[euronics] Navigating to: %s", search_url)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await self._dismiss_cookies(page)

            # Strategy 1: CSS extraction with multiple selector patterns
            results = await self._strategy_css(page, product_model, product_brand, listino_eur, search_url)

            # Strategy 2: JS comprehensive extraction
            if not results:
                logger.info("[euronics] CSS found nothing, trying JS comprehensive extraction")
                results = await self._strategy_js_comprehensive(page, product_model, product_brand, listino_eur, search_url)

            # Strategy 3: data-obj JSON extraction
            if not results:
                logger.info("[euronics] JS comprehensive found nothing, trying data-obj fallback")
                results = await self._strategy_data_obj(page, product_model, product_brand, listino_eur, search_url)

            # Strategy 4: Full page link scan
            if not results:
                logger.info("[euronics] data-obj found nothing, trying full page scan")
                js_products = await self._js_extract_products(page, product_model, product_brand)
                for jp in js_products[:8]:
                    promo = self._build_promo_from_item(jp, product_model, product_brand, listino_eur, search_url)
                    if promo:
                        results.append(promo)

        finally:
            await page.close()

        logger.info("[euronics] Total results for '%s %s': %d", product_brand, product_model, len(results))
        return results

    async def _strategy_css(
        self, page, product_model: str, product_brand: str, listino_eur: float, fallback_url: str
    ) -> List[PromoResult]:
        """Strategy 1: Try multiple CSS selector patterns for product cards."""
        results = []

        for card_sel in CARD_SELECTORS:
            cards = await page.query_selector_all(card_sel)
            if not cards:
                continue
            logger.info("[euronics] Found %d cards with selector '%s'", len(cards), card_sel)

            for card in cards[:12]:
                try:
                    # Extract title
                    title = ""
                    for ts in TITLE_SELECTORS:
                        title_el = await card.query_selector(ts)
                        if title_el:
                            title = (await title_el.inner_text()).strip()
                            if title:
                                break

                    if not self._is_matching_product(title, product_model, product_brand):
                        continue

                    storage = extract_storage_gb(title)
                    is_bundle, bundle_desc = detect_bundle(title)
                    logger.info("[euronics] Matched: %s", title[:80])

                    # Extract promo price
                    prezzo_promo = None
                    for ps in PRICE_SELECTORS:
                        price_el = await card.query_selector(ps)
                        if price_el:
                            prezzo_promo = self._parse_price(await price_el.inner_text())
                            if prezzo_promo and prezzo_promo > MIN_PRICE:
                                break
                            prezzo_promo = None

                    # Fallback: extract prices from card text
                    if not prezzo_promo:
                        card_text = await card.inner_text()
                        prices = self._extract_prices_from_text(card_text)
                        prices = [p for p in prices if p > MIN_PRICE]
                        if prices:
                            prezzo_promo = min(prices)

                    if not prezzo_promo or prezzo_promo < MIN_PRICE:
                        continue

                    # Extract original price
                    prezzo_originale = None
                    for ops in ORIG_PRICE_SELECTORS:
                        orig_el = await card.query_selector(ops)
                        if orig_el:
                            prezzo_originale = self._parse_price(await orig_el.inner_text())
                            if prezzo_originale and prezzo_originale > prezzo_promo:
                                break
                            prezzo_originale = None

                    if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                        prezzo_originale = listino_eur

                    if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                        continue

                    # Extract link
                    url = fallback_url
                    for ls in LINK_SELECTORS:
                        link_el = await card.query_selector(ls)
                        if link_el:
                            href = await link_el.get_attribute("href")
                            if href:
                                url = href if href.startswith("http") else f"https://www.euronics.it{href}"
                                break

                    sconto = self._calc_discount(prezzo_originale, prezzo_promo)
                    if sconto > 70:
                        continue

                    logger.info("[euronics][CSS] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                                title[:60], prezzo_originale, prezzo_promo, sconto)

                    results.append(PromoResult(
                        retailer="euronics", retailer_variant=None,
                        prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
                        sconto_percentuale=sconto, data_inizio=date.today(),
                        data_fine=None, url_fonte=url, promo_tag="Sconto Euronics",
                        storage_gb=storage, is_bundle=is_bundle, bundle_description=bundle_desc,
                    ))

                except Exception as e:
                    logger.debug("[euronics] Error parsing card with '%s': %s", card_sel, e)
                    continue

            if results:
                break  # Found results with this selector pattern

        return results

    async def _strategy_js_comprehensive(
        self, page, product_model: str, product_brand: str, listino_eur: float, fallback_url: str
    ) -> List[PromoResult]:
        """Strategy 2: JavaScript comprehensive extraction scanning all containers."""
        results = []
        try:
            data = await page.evaluate("""() => {
                const results = [];
                const containers = document.querySelectorAll(
                    '.product, .product-tile, .new-product-tile, [class*="product"], article, .card'
                );
                const seen = new Set();

                for (const card of containers) {
                    const text = card.innerText || '';
                    if (text.length < 20 || text.length > 5000) continue;

                    // Find title
                    const titleEl = card.querySelector(
                        '.tile-name, .product-name, .product-title, h2, h3, ' +
                        '[class*="name"], [class*="title"]'
                    );
                    const title = titleEl ? titleEl.textContent.trim() : '';
                    if (!title || title.length < 5) continue;

                    // Dedup by title
                    if (seen.has(title)) continue;
                    seen.add(title);

                    // Extract prices
                    const priceRe = /(\\d{1,3}(?:\\.\\d{3})*,\\d{2})/g;
                    const prices = [];
                    let m;
                    while ((m = priceRe.exec(text)) !== null) {
                        const raw = m[1].replace(/\\./g, '').replace(',', '.');
                        const val = parseFloat(raw);
                        if (val > 15) prices.push(val);
                    }

                    // Find link
                    const linkEl = card.querySelector(
                        'a[href*="/p/"], a[href*="/product"], a.link-pdp, a[href*="/prodotto"]'
                    );
                    const href = linkEl ? linkEl.getAttribute('href') : '';

                    if (prices.length > 0) {
                        results.push({
                            title: title.substring(0, 300),
                            prices: prices,
                            href: href || '',
                        });
                    }
                }
                return results;
            }""")

            for item in (data or []):
                promo = self._build_promo_from_item(item, product_model, product_brand, listino_eur, fallback_url)
                if promo:
                    results.append(promo)

        except Exception as e:
            logger.warning("[euronics] JS comprehensive extraction failed: %s", e)

        return results

    async def _strategy_data_obj(
        self, page, product_model: str, product_brand: str, listino_eur: float, fallback_url: str
    ) -> List[PromoResult]:
        """Strategy 3: Extract from data-obj JSON attributes."""
        results = []
        try:
            data = await page.evaluate("""() => {
                const tiles = document.querySelectorAll('.new-product-tile[data-obj], [data-obj]');
                const items = [];
                for (const tile of tiles) {
                    try {
                        const obj = JSON.parse(tile.getAttribute('data-obj'));
                        const card = tile.closest('.product, [class*="product"], article') || tile.parentElement;
                        const titleEl = card ? card.querySelector('.tile-name, .product-name, h2, h3') : null;
                        const origEl = card ? card.querySelector('.more-price-details .value, del, .old-price') : null;
                        const linkEl = card ? card.querySelector('a.link-pdp, a[href*="/p/"], a[href]') : null;

                        // Also extract all prices from card text as fallback
                        const cardText = card ? card.innerText : '';
                        const priceRe = /(\\d{1,3}(?:\\.\\d{3})*,\\d{2})/g;
                        const textPrices = [];
                        let m;
                        while ((m = priceRe.exec(cardText)) !== null) {
                            const raw = m[1].replace(/\\./g, '').replace(',', '.');
                            const val = parseFloat(raw);
                            if (val > 15) textPrices.push(val);
                        }

                        items.push({
                            name: obj.name || '',
                            brand: obj.brand || '',
                            price: obj.price || '0',
                            title: titleEl ? titleEl.textContent.trim() : '',
                            origPrice: origEl ? origEl.textContent.trim() : '',
                            href: linkEl ? linkEl.getAttribute('href') : '',
                            textPrices: textPrices,
                        });
                    } catch(e) {}
                }
                return items;
            }""")

            for item in (data or []):
                title = item.get("title") or item.get("name", "")
                if not self._is_matching_product(title, product_model, product_brand):
                    continue

                storage = extract_storage_gb(title)
                is_bundle, bundle_desc = detect_bundle(title)

                # Try price from data-obj
                prezzo_promo = None
                try:
                    prezzo_promo = float(item.get("price", "0"))
                except ValueError:
                    pass

                # Fallback to text prices
                if not prezzo_promo or prezzo_promo < MIN_PRICE:
                    text_prices = [p for p in item.get("textPrices", []) if p > MIN_PRICE]
                    if text_prices:
                        prezzo_promo = min(text_prices)

                if not prezzo_promo or prezzo_promo < MIN_PRICE:
                    continue

                prezzo_originale = self._parse_price(item.get("origPrice", ""))

                # Fallback to text prices for original
                if prezzo_originale is None:
                    text_prices = sorted([p for p in item.get("textPrices", []) if p > prezzo_promo])
                    if text_prices:
                        prezzo_originale = text_prices[-1]

                if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                    prezzo_originale = listino_eur
                if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                    continue

                href = item.get("href", "")
                url = href if href and href.startswith("http") else (
                    f"https://www.euronics.it{href}" if href else fallback_url
                )

                sconto = self._calc_discount(prezzo_originale, prezzo_promo)
                if sconto > 70:
                    continue

                logger.info("[euronics][data-obj] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                            title[:60], prezzo_originale, prezzo_promo, sconto)

                results.append(PromoResult(
                    retailer="euronics", retailer_variant=None,
                    prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
                    sconto_percentuale=sconto, data_inizio=date.today(),
                    data_fine=None, url_fonte=url, promo_tag="Sconto Euronics",
                    storage_gb=storage, is_bundle=is_bundle, bundle_description=bundle_desc,
                ))

        except Exception as e:
            logger.warning("[euronics] data-obj extraction failed: %s", e)

        return results

    def _build_promo_from_item(
        self, item: dict, product_model: str, product_brand: str, listino_eur: float, fallback_url: str
    ) -> Optional[PromoResult]:
        """Build a PromoResult from a JS-extracted item dict."""
        title = item.get("title", "")
        if not self._is_matching_product(title, product_model, product_brand):
            return None

        storage = extract_storage_gb(title)
        is_bundle, bundle_desc = detect_bundle(title)

        prices = sorted([p for p in item.get("prices", []) if p > MIN_PRICE])
        if not prices:
            return None

        prezzo_promo = prices[0]
        prezzo_originale = prices[-1] if len(prices) > 1 and prices[-1] > prezzo_promo else None

        if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
            prezzo_originale = listino_eur
        if prezzo_originale is None or prezzo_originale <= prezzo_promo:
            return None

        sconto = self._calc_discount(prezzo_originale, prezzo_promo)
        if sconto > 70:
            return None

        href = item.get("href", "")
        url = href if href and href.startswith("http") else (
            f"https://www.euronics.it{href}" if href else fallback_url
        )

        logger.info("[euronics][item] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                    title[:60], prezzo_originale, prezzo_promo, sconto)

        return PromoResult(
            retailer="euronics", retailer_variant=None,
            prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
            sconto_percentuale=sconto, data_inizio=date.today(),
            data_fine=None, url_fonte=url, promo_tag="Sconto Euronics",
            storage_gb=storage, is_bundle=is_bundle, bundle_description=bundle_desc,
        )
