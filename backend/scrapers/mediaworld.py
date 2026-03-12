import logging
from datetime import date
from typing import List

from backend.scrapers.base_scraper import BaseScraper, PromoResult

logger = logging.getLogger("tds.scraper.mediaworld")


class MediaWorldScraper(BaseScraper):
    retailer_name = "mediaworld"

    async def search_product(self, product_model: str, product_brand: str) -> List[PromoResult]:
        """Search MediaWorld for a product."""
        results: List[PromoResult] = []
        page = await self.new_page()

        try:
            query = f"{product_brand} {product_model}"
            search_url = self.config["search_url"].format(query=query.replace(" ", "%20"))

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            product_cards = await page.query_selector_all(
                "div[data-testid='product-card'], .product-card, article.product-tile"
            )

            if not product_cards:
                product_cards = await page.query_selector_all(
                    ".search-product-card, .product-item, div.product"
                )

            for card in product_cards[:5]:
                try:
                    title_el = await card.query_selector(
                        "h2, h3, .product-title, .product-name, [data-testid='product-title']"
                    )
                    title_text = await title_el.inner_text() if title_el else ""

                    if not self._is_matching_product(title_text, product_model, product_brand):
                        continue

                    original_price_el = await card.query_selector(
                        ".old-price, .price-old, del, s, .was-price, .list-price"
                    )
                    promo_price_el = await card.query_selector(
                        ".new-price, .price-new, .sale-price, .current-price, .offer-price"
                    )

                    if not promo_price_el:
                        continue

                    promo_text = await promo_price_el.inner_text()
                    prezzo_promo = self._parse_price(promo_text)
                    if prezzo_promo is None:
                        continue

                    prezzo_originale = prezzo_promo
                    if original_price_el:
                        orig_text = await original_price_el.inner_text()
                        parsed_orig = self._parse_price(orig_text)
                        if parsed_orig and parsed_orig > prezzo_promo:
                            prezzo_originale = parsed_orig

                    if prezzo_originale <= prezzo_promo:
                        continue

                    link_el = await card.query_selector("a[href]")
                    url = ""
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href:
                            url = href if href.startswith("http") else f"{self.config['base_url']}{href}"

                    sconto = self._calc_discount(prezzo_originale, prezzo_promo)

                    results.append(
                        PromoResult(
                            retailer="mediaworld",
                            retailer_variant=None,
                            prezzo_originale=prezzo_originale,
                            prezzo_promo=prezzo_promo,
                            sconto_percentuale=sconto,
                            data_inizio=date.today(),
                            data_fine=None,
                            url_fonte=url or search_url,
                        )
                    )

                except Exception as e:
                    logger.debug("Error parsing MediaWorld card: %s", str(e))
                    continue

            # Check offers page
            try:
                await page.goto(self.config["promo_url"], wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                promo_cards = await page.query_selector_all(
                    "div[data-testid='product-card'], .product-card, article.product-tile"
                )

                for card in promo_cards[:20]:
                    try:
                        title_el = await card.query_selector("h2, h3, .product-title, .product-name")
                        title_text = await title_el.inner_text() if title_el else ""

                        if not self._is_matching_product(title_text, product_model, product_brand):
                            continue

                        original_price_el = await card.query_selector(".old-price, .price-old, del, s")
                        promo_price_el = await card.query_selector(
                            ".new-price, .price-new, .sale-price, .current-price"
                        )

                        if not promo_price_el:
                            continue

                        promo_text = await promo_price_el.inner_text()
                        prezzo_promo = self._parse_price(promo_text)
                        if prezzo_promo is None:
                            continue

                        prezzo_originale = prezzo_promo
                        if original_price_el:
                            orig_text = await original_price_el.inner_text()
                            parsed_orig = self._parse_price(orig_text)
                            if parsed_orig and parsed_orig > prezzo_promo:
                                prezzo_originale = parsed_orig

                        if prezzo_originale <= prezzo_promo:
                            continue

                        link_el = await card.query_selector("a[href]")
                        url = ""
                        if link_el:
                            href = await link_el.get_attribute("href")
                            if href:
                                url = href if href.startswith("http") else f"{self.config['base_url']}{href}"

                        sconto = self._calc_discount(prezzo_originale, prezzo_promo)

                        results.append(
                            PromoResult(
                                retailer="mediaworld",
                                retailer_variant=None,
                                prezzo_originale=prezzo_originale,
                                prezzo_promo=prezzo_promo,
                                sconto_percentuale=sconto,
                                data_inizio=date.today(),
                                data_fine=None,
                                url_fonte=url or self.config["promo_url"],
                            )
                        )

                    except Exception as e:
                        logger.debug("Error parsing MediaWorld promo card: %s", str(e))
                        continue

            except Exception as e:
                logger.warning("Error checking MediaWorld promo page: %s", str(e))

        finally:
            await page.close()

        return results

    def _is_matching_product(self, title: str, model: str, brand: str) -> bool:
        title_lower = title.lower()
        model_parts = model.lower().split()
        brand_lower = brand.lower()

        if brand_lower not in title_lower:
            return False

        match_count = sum(1 for part in model_parts if part in title_lower)
        return match_count >= len(model_parts) * 0.6
