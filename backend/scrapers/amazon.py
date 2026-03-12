"""
Amazon.it scraper — Playwright with anti-bot measures.
Uses realistic user-agent, random delays, and stealth techniques.
"""
import asyncio
import logging
import random
from datetime import date
from typing import List, Optional

from backend.scrapers.base_scraper import BaseScraper, PromoResult, RETAILERS

logger = logging.getLogger("tds.scraper.amazon")

# Register Amazon in RETAILERS
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


class AmazonScraper(BaseScraper):
    retailer_name = "amazon"

    async def init_browser(self):
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        self.browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        self._pw = pw

    async def new_page(self):
        if not self.browser:
            await self.init_browser()

        ua = random.choice(USER_AGENTS)
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=ua,
            locale="it-IT",
            timezone_id="Europe/Rome",
            extra_http_headers={
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
            },
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['it-IT', 'it', 'en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()
        page.set_default_timeout(30000)
        return page

    async def _random_delay(self):
        delay = random.uniform(2.0, 5.0)
        await asyncio.sleep(delay)

    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        results: List[PromoResult] = []
        page = await self.new_page()

        try:
            # --- Search page ---
            query = f"{product_brand} {product_model}"
            search_url = self.config["search_url"].format(query=query.replace(" ", "+"))

            logger.info("[amazon] Navigating to: %s", search_url)
            await page.goto(search_url, wait_until="networkidle", timeout=45000)
            await self._random_delay()

            # Handle CAPTCHA
            if await page.query_selector("#captchacharacters"):
                logger.warning("[amazon] CAPTCHA detected, skipping %s %s", product_brand, product_model)
                return results

            # Accept cookies
            await self._dismiss_cookies(page)
            await self._log_page_state(page, "search")

            product_cards = await page.query_selector_all(
                "div[data-component-type='s-search-result']"
            )
            logger.info("[amazon] Found %d search result cards", len(product_cards))

            for card in product_cards[:8]:
                try:
                    title_el = await card.query_selector("h2 a span, h2 span.a-text-normal")
                    title_text = await title_el.inner_text() if title_el else ""

                    if not self._is_matching_product(title_text, product_model, product_brand):
                        continue

                    logger.info("[amazon] Matched product: %s", title_text[:80])

                    # Promo price (current price, not struck through)
                    whole_price_el = await card.query_selector(
                        "span.a-price:not([data-a-strike]) span.a-offscreen"
                    )
                    # Original price (struck through)
                    original_price_el = await card.query_selector(
                        "span.a-price[data-a-strike] span.a-offscreen, "
                        "span.a-text-price span.a-offscreen"
                    )

                    if not whole_price_el:
                        # Fallback: try any price element
                        whole_price_el = await card.query_selector("span.a-offscreen")
                        if not whole_price_el:
                            logger.info("[amazon] No price found for: %s", title_text[:60])
                            continue

                    promo_text = await whole_price_el.inner_text()
                    prezzo_promo = self._parse_price(promo_text)
                    if prezzo_promo is None:
                        continue

                    prezzo_originale = None
                    if original_price_el:
                        orig_text = await original_price_el.inner_text()
                        parsed_orig = self._parse_price(orig_text)
                        if parsed_orig and parsed_orig > prezzo_promo:
                            prezzo_originale = parsed_orig

                    # Fallback to DB listino
                    if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                        prezzo_originale = listino_eur

                    if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                        logger.info("[amazon] No discount for: %s (promo=%.2f)", title_text[:60], prezzo_promo)
                        continue

                    link_el = await card.query_selector("h2 a")
                    url = ""
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href:
                            url = href if href.startswith("http") else f"https://www.amazon.it{href}"

                    sconto = self._calc_discount(prezzo_originale, prezzo_promo)
                    promo_tag = await self._detect_promo_tag(card)

                    logger.info(
                        "[amazon] PROMO FOUND: %s | %.2f -> %.2f (%.1f%% off) tag=%s",
                        title_text[:60], prezzo_originale, prezzo_promo, sconto, promo_tag,
                    )

                    results.append(
                        PromoResult(
                            retailer="amazon",
                            retailer_variant=None,
                            prezzo_originale=prezzo_originale,
                            prezzo_promo=prezzo_promo,
                            sconto_percentuale=sconto,
                            data_inizio=date.today(),
                            data_fine=None,
                            url_fonte=url or search_url,
                            promo_tag=promo_tag,
                        )
                    )

                except Exception as e:
                    logger.debug("[amazon] Error parsing search card: %s", e)
                    continue

            # --- JS fallback if CSS found nothing ---
            if not results:
                logger.info("[amazon] CSS selectors found nothing, trying JS extraction")
                js_products = await self._js_extract_products(page, product_model, product_brand)
                logger.info("[amazon] JS extraction found %d matches", len(js_products))
                for jp in js_products[:5]:
                    promo = self._build_promo_from_js(jp, listino_eur, search_url)
                    if promo:
                        results.append(promo)

            # --- Deals page ---
            await self._random_delay()

            try:
                logger.info("[amazon] Checking deals page: %s", self.config["promo_url"])
                await page.goto(self.config["promo_url"], wait_until="networkidle", timeout=45000)
                await self._random_delay()
                await self._log_page_state(page, "deals")

                deal_cards = await page.query_selector_all(
                    "div[data-testid='deal-card'], div.DealCard-module, div[class*='DealCard']"
                )
                logger.info("[amazon] Found %d deal cards", len(deal_cards))

                for card in deal_cards[:20]:
                    try:
                        title_el = await card.query_selector(
                            "span[class*='Title'], a[class*='title'], span.a-truncate-full"
                        )
                        title_text = await title_el.inner_text() if title_el else ""

                        if not self._is_matching_product(title_text, product_model, product_brand):
                            continue

                        price_el = await card.query_selector(
                            "span[class*='price'], span.a-price span.a-offscreen"
                        )
                        if not price_el:
                            continue

                        price_text = await price_el.inner_text()
                        prezzo_promo = self._parse_price(price_text)
                        if prezzo_promo is None:
                            continue

                        orig_el = await card.query_selector(
                            "span[class*='strikethrough'], span.a-text-price span.a-offscreen"
                        )
                        prezzo_originale = None
                        if orig_el:
                            orig_text = await orig_el.inner_text()
                            parsed_orig = self._parse_price(orig_text)
                            if parsed_orig and parsed_orig > prezzo_promo:
                                prezzo_originale = parsed_orig

                        if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                            prezzo_originale = listino_eur

                        if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                            continue

                        link_el = await card.query_selector("a[href]")
                        url = ""
                        if link_el:
                            href = await link_el.get_attribute("href")
                            if href:
                                url = href if href.startswith("http") else f"https://www.amazon.it{href}"

                        sconto = self._calc_discount(prezzo_originale, prezzo_promo)
                        promo_tag = await self._detect_promo_tag(card)

                        logger.info(
                            "[amazon] DEAL FOUND: %s | %.2f -> %.2f (%.1f%%) tag=%s",
                            title_text[:60], prezzo_originale, prezzo_promo, sconto, promo_tag,
                        )

                        results.append(
                            PromoResult(
                                retailer="amazon",
                                retailer_variant=None,
                                prezzo_originale=prezzo_originale,
                                prezzo_promo=prezzo_promo,
                                sconto_percentuale=sconto,
                                data_inizio=date.today(),
                                data_fine=None,
                                url_fonte=url or self.config["promo_url"],
                                promo_tag=promo_tag,
                            )
                        )

                    except Exception as e:
                        logger.debug("[amazon] Error parsing deal card: %s", e)
                        continue

            except Exception as e:
                logger.warning("[amazon] Error on deals page: %s", e)

        finally:
            await page.close()

        logger.info("[amazon] Total results for '%s %s': %d", product_brand, product_model, len(results))
        return results

    def _build_promo_from_js(self, jp: dict, listino_eur: float, fallback_url: str) -> Optional[PromoResult]:
        prices = []
        for raw in jp.get("prices", []):
            p = self._parse_price(raw)
            if p:
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
        url = jp.get("href", "") or fallback_url

        logger.info("[amazon][JS] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                    jp.get("title", "")[:60], prezzo_originale, prezzo_promo, sconto)

        return PromoResult(
            retailer="amazon",
            retailer_variant=None,
            prezzo_originale=prezzo_originale,
            prezzo_promo=prezzo_promo,
            sconto_percentuale=sconto,
            data_inizio=date.today(),
            data_fine=None,
            url_fonte=url,
            promo_tag="Sconto Amazon",
        )

    async def _detect_promo_tag(self, card) -> Optional[str]:
        tag_selectors = [
            ("span.a-badge-text", None),
            ("span[data-a-badge-type]", None),
            ("span[class*='deal-badge']", None),
            ("span[class*='coupon']", "Coupon"),
            ("span[class*='lightning']", "Offerta Lampo"),
            ("span[class*='Badge']", None),
        ]

        for selector, default_text in tag_selectors:
            el = await card.query_selector(selector)
            if el:
                text = await el.inner_text()
                text = text.strip()
                if text:
                    text_lower = text.lower()
                    if "lampo" in text_lower or "lightning" in text_lower:
                        return "Offerta Lampo"
                    elif "coupon" in text_lower:
                        return "Coupon"
                    elif "black friday" in text_lower:
                        return "Black Friday"
                    elif "prime" in text_lower:
                        return "Prime Deal"
                    elif "spring" in text_lower or "primavera" in text_lower:
                        return "Spring Deal"
                    elif "offerta" in text_lower or "deal" in text_lower:
                        return "Offerta del giorno"
                    return text[:50]
                elif default_text:
                    return default_text

        pct_el = await card.query_selector("span[class*='savingsPercentage'], span.a-color-price")
        if pct_el:
            pct_text = await pct_el.inner_text()
            if "%" in pct_text:
                return "Sconto Amazon"

        return None
