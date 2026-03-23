"""
Amazon.it scraper — Playwright with anti-bot measures.
Improved price extraction with stricter validation for consumer electronics.
"""
import asyncio
import logging
import random
import re
from datetime import date
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

from backend.scrapers.base_scraper import BaseScraper, PromoResult, RETAILERS, extract_storage_gb, detect_bundle

logger = logging.getLogger("tds.scraper.amazon")

RETAILERS["amazon"] = {
    "base_url": "https://www.amazon.it",
    "search_url": "https://www.amazon.it/s?k={query}",
    "promo_url": "https://www.amazon.it/deals",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# Price bounds for consumer electronics
MIN_PRICE_EUR = 50.0
MAX_PRICE_EUR = 2500.0
# Maximum plausible discount
MAX_DISCOUNT_PCT = 70.0
# Words indicating refurbished/used products
REFURB_KEYWORDS = ["ricondizionato", "usato", "renewed", "refurbished", "rigenerato", "seconda mano"]


class AmazonScraper(BaseScraper):
    retailer_name = "amazon"

    async def init_browser(self):
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        self.browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        self._pw = pw

    async def new_page(self):
        if not self.browser:
            await self.init_browser()
        ua = random.choice(USER_AGENTS)
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=ua, locale="it-IT", timezone_id="Europe/Rome",
            extra_http_headers={"Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7", "DNT": "1"},
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)
        page = await context.new_page()
        page.set_default_timeout(30000)
        return page

    async def _random_delay(self):
        await asyncio.sleep(random.uniform(2.0, 5.0))

    @staticmethod
    def _clean_amazon_url(url: str) -> str:
        """Strip tracking parameters from Amazon URLs."""
        if not url or "amazon" not in url:
            return url
        match = re.match(r'(https?://www\.amazon\.\w+/[^?]*?/dp/[A-Z0-9]{10})', url)
        if match:
            return match.group(1)
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query="", fragment=""))[:2000]

    def _is_matching_product_strict(self, title: str, model: str, brand: str) -> bool:
        """Strict matching: brand must be present, >70% of model words must match."""
        if not title:
            return False
        title_lower = title.lower()
        brand_lower = brand.lower()
        if brand_lower not in title_lower:
            return False
        model_parts = model.lower().split()
        if not model_parts:
            return False
        match_count = sum(1 for part in model_parts if part in title_lower)
        # Require >70% match
        return match_count >= max(1, len(model_parts) * 0.7)

    def _is_refurbished(self, title: str) -> bool:
        """Check if title indicates a refurbished/used product."""
        title_lower = title.lower()
        return any(kw in title_lower for kw in REFURB_KEYWORDS)

    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        results: List[PromoResult] = []
        page = await self.new_page()

        try:
            query = f"{product_brand} {product_model}"
            search_url = self.config["search_url"].format(query=query.replace(" ", "+"))

            logger.info("[amazon] Navigating to: %s", search_url)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await self._random_delay()

            if await page.query_selector("#captchacharacters"):
                logger.warning("[amazon] CAPTCHA detected, skipping %s %s", product_brand, product_model)
                return results

            await self._dismiss_cookies(page)
            await self._log_page_state(page, "search")

            # Only select main search results with data-asin (not sponsored)
            product_cards = await page.query_selector_all(
                "div[data-component-type='s-search-result'][data-asin]"
            )
            logger.info("[amazon] Found %d search result cards", len(product_cards))

            for card in product_cards[:10]:
                try:
                    # Skip sponsored results
                    sponsored = await card.query_selector(
                        "[data-component-type='sp-sponsored-result'], .puis-sponsored-label-text, "
                        "span.a-color-secondary:has-text('Sponsorizzato')"
                    )
                    if sponsored:
                        continue

                    title_el = await card.query_selector("h2 a span, h2 span.a-text-normal")
                    title_text = await title_el.inner_text() if title_el else ""

                    if not self._is_matching_product_strict(title_text, product_model, product_brand):
                        continue

                    # Check for refurbished
                    is_refurb = self._is_refurbished(title_text)

                    storage = extract_storage_gb(title_text)
                    is_bundle, bundle_desc = detect_bundle(title_text)

                    logger.info("[amazon] Matched product: %s (refurb=%s)", title_text[:80], is_refurb)

                    # Extract prices using JS
                    price_data = await self._extract_prices_js(card)
                    if not price_data:
                        logger.info("[amazon] No price data for: %s", title_text[:60])
                        continue

                    prezzo_promo = price_data.get("promo")
                    prezzo_originale = price_data.get("original")

                    # Validate price range
                    if prezzo_promo is None or prezzo_promo < MIN_PRICE_EUR or prezzo_promo > MAX_PRICE_EUR:
                        logger.info("[amazon] Price out of range (%.2f) for: %s",
                                   prezzo_promo or 0, title_text[:60])
                        continue

                    # Skip refurbished if price is suspiciously low (>50% below listino)
                    if is_refurb and listino_eur and prezzo_promo < listino_eur * 0.5:
                        logger.info("[amazon] SKIP refurbished with low price (%.2f vs listino %.2f): %s",
                                   prezzo_promo, listino_eur, title_text[:60])
                        continue

                    # Fallback to DB listino
                    if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                        prezzo_originale = listino_eur

                    if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                        logger.info("[amazon] No discount for: %s (promo=%.2f, orig=%s)",
                                   title_text[:60], prezzo_promo, prezzo_originale)
                        continue

                    # Validate original price range too
                    if prezzo_originale > MAX_PRICE_EUR * 1.5:
                        logger.info("[amazon] Original price too high (%.2f): %s",
                                   prezzo_originale, title_text[:60])
                        continue

                    sconto = self._calc_discount(prezzo_originale, prezzo_promo)

                    if sconto > MAX_DISCOUNT_PCT:
                        logger.warning(
                            "[amazon] REJECTED implausible discount %.1f%% for %s (%.2f -> %.2f)",
                            sconto, title_text[:60], prezzo_originale, prezzo_promo,
                        )
                        continue

                    link_el = await card.query_selector("h2 a")
                    url = ""
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href:
                            raw_url = href if href.startswith("http") else f"https://www.amazon.it{href}"
                            url = self._clean_amazon_url(raw_url)

                    promo_tag = await self._detect_promo_tag(card)

                    logger.info(
                        "[amazon] PROMO FOUND: %s | %.2f -> %.2f (%.1f%%) tag=%s",
                        title_text[:60], prezzo_originale, prezzo_promo, sconto, promo_tag,
                    )

                    results.append(PromoResult(
                        retailer="amazon", retailer_variant=None,
                        prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
                        sconto_percentuale=sconto, data_inizio=date.today(),
                        data_fine=None, url_fonte=url or search_url, promo_tag=promo_tag,
                        storage_gb=storage, is_bundle=is_bundle, bundle_description=bundle_desc,
                    ))

                except Exception as e:
                    logger.debug("[amazon] Error parsing search card: %s", e)
                    continue

            # JS fallback if CSS found nothing
            if not results:
                logger.info("[amazon] CSS found nothing, trying JS extraction")
                js_products = await self._js_extract_products(page, product_model, product_brand)
                logger.info("[amazon] JS found %d matches", len(js_products))
                for jp in js_products[:5]:
                    promo = self._build_promo_from_js(jp, listino_eur, search_url)
                    if promo:
                        results.append(promo)

        finally:
            await page.close()

        logger.info("[amazon] Total results for '%s %s': %d", product_brand, product_model, len(results))
        return results

    async def _extract_prices_js(self, card) -> Optional[dict]:
        """Extract prices from an Amazon search result card using JS.
        Uses .a-price-whole + .a-price-fraction for precise extraction."""
        try:
            data = await card.evaluate("""(el) => {
                const result = {};

                // Current price: first .a-price NOT struck through, within main result area
                // Avoid sponsored overlays and rating elements
                const priceEls = el.querySelectorAll('span.a-price:not([data-a-strike="true"])');
                for (const p of priceEls) {
                    // Skip if inside a ratings or review section
                    const parent = p.closest('[class*="rating"], [class*="review"], [class*="star"]');
                    if (parent) continue;

                    const whole = p.querySelector('.a-price-whole');
                    const frac = p.querySelector('.a-price-fraction');
                    if (whole) {
                        // Clean: remove dots (thousands sep) and non-digits
                        let wholeText = whole.textContent.replace(/[^0-9]/g, '');
                        const fracText = frac ? frac.textContent.replace(/[^0-9]/g, '') : '00';
                        if (wholeText) {
                            const price = parseFloat(wholeText + '.' + fracText);
                            if (price >= 50 && price <= 2500) {
                                result.promo = price;
                                break;
                            }
                        }
                    }
                }

                // Original/struck-through price
                const strikeEls = el.querySelectorAll(
                    'span.a-price[data-a-strike="true"], span.a-text-price[data-a-strike="true"]'
                );
                for (const s of strikeEls) {
                    const offscreen = s.querySelector('.a-offscreen');
                    if (offscreen) {
                        // Parse Italian format: €1.299,99 -> 1299.99
                        let text = offscreen.textContent
                            .replace('€', '').replace(/\s/g, '')
                            .replace(/\./g, '').replace(',', '.');
                        const price = parseFloat(text);
                        if (price >= 50 && price <= 3750 && (!result.promo || price > result.promo)) {
                            result.original = price;
                            break;
                        }
                    }
                }

                // Fallback: try .a-text-price (non-struck)
                if (!result.original) {
                    const textPriceEls = el.querySelectorAll('span.a-text-price:not(:empty)');
                    for (const tp of textPriceEls) {
                        const off = tp.querySelector('.a-offscreen');
                        if (off) {
                            let text = off.textContent
                                .replace('€', '').replace(/\s/g, '')
                                .replace(/\./g, '').replace(',', '.');
                            const price = parseFloat(text);
                            if (price >= 50 && price <= 3750 && (!result.promo || price > result.promo)) {
                                result.original = price;
                                break;
                            }
                        }
                    }
                }

                return (result.promo) ? result : null;
            }""")
            return data
        except Exception as e:
            logger.debug("[amazon] JS price extraction failed: %s", e)
            return None

    def _build_promo_from_js(self, jp: dict, listino_eur: float, fallback_url: str) -> Optional[PromoResult]:
        title = jp.get("title", "")
        storage = extract_storage_gb(title)
        is_bundle, bundle_desc = detect_bundle(title)

        # Check refurbished
        if self._is_refurbished(title):
            if listino_eur and any(
                self._parse_price(raw) and self._parse_price(raw) < listino_eur * 0.5
                for raw in jp.get("prices", [])
            ):
                return None

        prices = []
        for raw in jp.get("prices", []):
            p = self._parse_price(raw)
            if p and MIN_PRICE_EUR <= p <= MAX_PRICE_EUR:
                prices.append(p)
        if not prices:
            return None
        prezzo_promo = min(prices)
        prezzo_originale = max(prices) if len(prices) > 1 and max(prices) > prezzo_promo else None
        if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
            prezzo_originale = listino_eur
        if prezzo_originale is None or prezzo_originale <= prezzo_promo:
            return None
        sconto = self._calc_discount(prezzo_originale, prezzo_promo)
        if sconto > MAX_DISCOUNT_PCT:
            return None
        url = self._clean_amazon_url(jp.get("href", "")) or fallback_url
        logger.info("[amazon][JS] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                    jp.get("title", "")[:60], prezzo_originale, prezzo_promo, sconto)
        return PromoResult(
            retailer="amazon", retailer_variant=None,
            prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
            sconto_percentuale=sconto, data_inizio=date.today(),
            data_fine=None, url_fonte=url, promo_tag="Sconto Amazon",
            storage_gb=storage, is_bundle=is_bundle, bundle_description=bundle_desc,
        )

    async def _detect_promo_tag(self, card) -> Optional[str]:
        tag_selectors = [
            ("span.a-badge-text", None),
            ("span[data-a-badge-type]", None),
            ("span[class*='coupon']", "Coupon"),
            ("span[class*='lightning']", "Offerta Lampo"),
        ]
        for selector, default_text in tag_selectors:
            try:
                el = await card.query_selector(selector)
                if el:
                    text = (await el.inner_text()).strip()
                    if text:
                        tl = text.lower()
                        if "lampo" in tl or "lightning" in tl:
                            return "Offerta Lampo"
                        elif "coupon" in tl:
                            return "Coupon"
                        elif "prime" in tl:
                            return "Prime Deal"
                        elif "offerta" in tl or "deal" in tl:
                            return "Offerta del giorno"
                        return text[:50]
                    elif default_text:
                        return default_text
            except Exception:
                continue

        try:
            pct_el = await card.query_selector("span[class*='savingsPercentage']")
            if pct_el:
                pct_text = await pct_el.inner_text()
                if "%" in pct_text:
                    return "Sconto Amazon"
        except Exception:
            pass

        return None
