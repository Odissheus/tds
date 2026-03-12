import logging
from datetime import date
from typing import List, Optional

from backend.scrapers.base_scraper import BaseScraper, PromoResult

logger = logging.getLogger("tds.scraper.unieuro")

CARD_SELECTORS = [
    "div[class*='product-card']",
    "article[class*='product']",
    "div[class*='ProductCard']",
    "div[data-product-id]",
    "div[class*='product-tile']",
    "li[class*='product']",
    ".search-result-item",
    ".product-list__item",
]

TITLE_SELECTORS = [
    "h2 a", "h3 a", "h2", "h3", "h4",
    "[class*='product-title']", "[class*='product-name']",
    "[class*='ProductTitle']", "[class*='ProductName']",
    "a.product-link", "a[title]",
]

PROMO_PRICE_SELECTORS = [
    "[class*='new-price']", "[class*='price--new']",
    "[class*='sale-price']", "[class*='current-price']",
    "[class*='final-price']", "[class*='special-price']",
    "[class*='Price'] strong", "span[class*='price']:not(del span)",
]

ORIG_PRICE_SELECTORS = [
    "[class*='old-price']", "[class*='price--old']",
    "[class*='original-price']", "[class*='list-price']",
    "del", "s",
    "[class*='was-price']", "[class*='strikethrough']",
]


class UnieuroScraper(BaseScraper):
    retailer_name = "unieuro"

    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        results: List[PromoResult] = []
        page = await self.new_page()

        try:
            query = f"{product_brand} {product_model}"
            search_url = self.config["search_url"].format(query=query.replace(" ", "+"))

            logger.info("[unieuro] Navigating to: %s", search_url)
            await page.goto(search_url, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(3000)

            await self._dismiss_cookies(page)
            await self._log_page_state(page, "search")

            # Strategy 1: CSS selectors
            cards = await self._find_cards(page)
            logger.info("[unieuro] CSS strategy found %d cards for '%s'", len(cards), query)

            for card in cards[:10]:
                promo = await self._extract_from_card(card, product_model, product_brand, listino_eur, search_url)
                if promo:
                    results.append(promo)

            # Strategy 2: JS fallback
            if not results:
                logger.info("[unieuro] CSS found nothing, trying JS extraction")
                js_products = await self._js_extract_products(page, product_model, product_brand)
                logger.info("[unieuro] JS extraction found %d matches", len(js_products))
                for jp in js_products[:5]:
                    promo = self._build_promo_from_js(jp, listino_eur, search_url)
                    if promo:
                        results.append(promo)

            # Check offers page
            try:
                logger.info("[unieuro] Checking offers page: %s", self.config["promo_url"])
                await page.goto(self.config["promo_url"], wait_until="networkidle", timeout=45000)
                await page.wait_for_timeout(3000)
                await self._log_page_state(page, "offers")

                cards = await self._find_cards(page)
                logger.info("[unieuro] Offers page found %d cards", len(cards))

                for card in cards[:20]:
                    promo = await self._extract_from_card(
                        card, product_model, product_brand, listino_eur, self.config["promo_url"]
                    )
                    if promo:
                        results.append(promo)

                if not results:
                    js_products = await self._js_extract_products(page, product_model, product_brand)
                    for jp in js_products[:5]:
                        promo = self._build_promo_from_js(jp, listino_eur, self.config["promo_url"])
                        if promo:
                            results.append(promo)

            except Exception as e:
                logger.warning("[unieuro] Error on offers page: %s", e)

        finally:
            await page.close()

        logger.info("[unieuro] Total results for '%s %s': %d", product_brand, product_model, len(results))
        return results

    async def _find_cards(self, page) -> list:
        for selector in CARD_SELECTORS:
            try:
                cards = await page.query_selector_all(selector)
                if cards:
                    return cards
            except Exception:
                continue
        return []

    async def _extract_from_card(
        self, card, product_model: str, product_brand: str, listino_eur: float, fallback_url: str
    ) -> Optional[PromoResult]:
        try:
            title_text = ""
            for sel in TITLE_SELECTORS:
                try:
                    el = await card.query_selector(sel)
                    if el:
                        title_text = (await el.inner_text()).strip()
                        if title_text:
                            break
                except Exception:
                    continue

            if not self._is_matching_product(title_text, product_model, product_brand):
                return None

            logger.info("[unieuro] Matched product: %s", title_text[:80])

            prezzo_promo = None
            for sel in PROMO_PRICE_SELECTORS:
                try:
                    el = await card.query_selector(sel)
                    if el:
                        text = await el.inner_text()
                        prezzo_promo = self._parse_price(text)
                        if prezzo_promo:
                            break
                except Exception:
                    continue

            if prezzo_promo is None:
                try:
                    card_text = await card.inner_text()
                    prices = self._extract_prices_from_text(card_text)
                    if prices:
                        prezzo_promo = min(prices)
                except Exception:
                    pass

            if prezzo_promo is None:
                return None

            prezzo_originale = None
            for sel in ORIG_PRICE_SELECTORS:
                try:
                    el = await card.query_selector(sel)
                    if el:
                        text = await el.inner_text()
                        p = self._parse_price(text)
                        if p and p > prezzo_promo:
                            prezzo_originale = p
                            break
                except Exception:
                    continue

            if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                prezzo_originale = listino_eur

            if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                return None

            url = fallback_url
            try:
                link_el = await card.query_selector("a[href]")
                if link_el:
                    href = await link_el.get_attribute("href")
                    if href:
                        url = href if href.startswith("http") else f"{self.config['base_url']}{href}"
            except Exception:
                pass

            sconto = self._calc_discount(prezzo_originale, prezzo_promo)

            logger.info(
                "[unieuro] PROMO FOUND: %s | %.2f -> %.2f (%.1f%% off)",
                title_text[:60], prezzo_originale, prezzo_promo, sconto,
            )

            return PromoResult(
                retailer="unieuro",
                retailer_variant=None,
                prezzo_originale=prezzo_originale,
                prezzo_promo=prezzo_promo,
                sconto_percentuale=sconto,
                data_inizio=date.today(),
                data_fine=None,
                url_fonte=url,
            )

        except Exception as e:
            logger.debug("[unieuro] Error parsing card: %s", e)
            return None

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

        logger.info("[unieuro][JS] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                    jp.get("title", "")[:60], prezzo_originale, prezzo_promo, sconto)

        return PromoResult(
            retailer="unieuro",
            retailer_variant=None,
            prezzo_originale=prezzo_originale,
            prezzo_promo=prezzo_promo,
            sconto_percentuale=sconto,
            data_inizio=date.today(),
            data_fine=None,
            url_fonte=url,
        )
