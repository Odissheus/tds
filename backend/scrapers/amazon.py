"""
Amazon.it scraper — Playwright with anti-bot measures.
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

# Minimum plausible price for consumer electronics (filters out ratings, shipping, etc.)
MIN_PRICE_EUR = 15.0
# Maximum plausible discount — anything above this is likely a parsing error
MAX_DISCOUNT_PCT = 70.0


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
        """Strip tracking parameters from Amazon URLs to keep them short."""
        if not url or "amazon" not in url:
            return url
        # Amazon product URLs: /dp/ASIN/... — strip everything after ref=
        match = re.match(r'(https?://www\.amazon\.\w+/[^?]*?/dp/[A-Z0-9]{10})', url)
        if match:
            return match.group(1)
        # Fallback: strip query string
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query="", fragment=""))[:2000]

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

            product_cards = await page.query_selector_all("div[data-component-type='s-search-result']")
            logger.info("[amazon] Found %d search result cards", len(product_cards))

            for card in product_cards[:8]:
                try:
                    title_el = await card.query_selector("h2 a span, h2 span.a-text-normal")
                    title_text = await title_el.inner_text() if title_el else ""

                    if not self._is_matching_product(title_text, product_model, product_brand):
                        continue

                    storage = extract_storage_gb(title_text)
                    is_bundle, bundle_desc = detect_bundle(title_text)

                    logger.info("[amazon] Matched product: %s", title_text[:80])

                    # Extract prices using JS from within the card to avoid grabbing ratings
                    price_data = await self._extract_prices_js(card)
                    if not price_data:
                        logger.info("[amazon] No price data for: %s", title_text[:60])
                        continue

                    prezzo_promo = price_data.get("promo")
                    prezzo_originale = price_data.get("original")

                    if prezzo_promo is None or prezzo_promo < MIN_PRICE_EUR:
                        logger.info("[amazon] Price too low (%.2f) for: %s — likely not a real price",
                                   prezzo_promo or 0, title_text[:60])
                        continue

                    # Fallback to DB listino
                    if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                        prezzo_originale = listino_eur

                    if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                        logger.info("[amazon] No discount for: %s (promo=%.2f, orig=%s)",
                                   title_text[:60], prezzo_promo, prezzo_originale)
                        continue

                    sconto = self._calc_discount(prezzo_originale, prezzo_promo)

                    # Sanity check: reject implausible discounts
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
        Only looks inside .a-price containers to avoid grabbing review scores."""
        try:
            data = await card.evaluate("""(el) => {
                const result = {};

                // Current price: first .a-price that is NOT struck through
                const priceEls = el.querySelectorAll('span.a-price:not([data-a-strike="true"])');
                for (const p of priceEls) {
                    // Get the whole+fraction parts, not .a-offscreen (which can be ambiguous)
                    const whole = p.querySelector('.a-price-whole');
                    const frac = p.querySelector('.a-price-fraction');
                    if (whole) {
                        const wholeText = whole.textContent.replace(/[^0-9.]/g, '');
                        const fracText = frac ? frac.textContent.replace(/[^0-9]/g, '') : '00';
                        const price = parseFloat(wholeText + '.' + fracText);
                        if (price > 10) {
                            result.promo = price;
                            break;
                        }
                    }
                }

                // Original/struck-through price
                const strikeEls = el.querySelectorAll('span.a-price[data-a-strike="true"], span.a-text-price');
                for (const s of strikeEls) {
                    const offscreen = s.querySelector('.a-offscreen');
                    if (offscreen) {
                        const text = offscreen.textContent.replace('€', '').replace(/\\s/g, '').replace('.', '').replace(',', '.');
                        const price = parseFloat(text);
                        if (price > 10 && (!result.promo || price > result.promo)) {
                            result.original = price;
                            break;
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

        prices = []
        for raw in jp.get("prices", []):
            p = self._parse_price(raw)
            if p and p >= MIN_PRICE_EUR:
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
