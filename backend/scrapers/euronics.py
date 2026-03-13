"""
Euronics.it scraper — based on real HTML structure captured March 2026.

Search URL: https://www.euronics.it/search?q={query}
Card selector: .product-grid .product
Title: .tile-name
Promo price: .discount .price-formatted
Original price: .more-price-details .value
Link: a.link-pdp
data-obj JSON: {"name", "id", "price", "brand", "category"}
"""
import json
import logging
from datetime import date
from typing import List, Optional

from backend.scrapers.base_scraper import BaseScraper, PromoResult

logger = logging.getLogger("tds.scraper.euronics")


class EuronicsScraper(BaseScraper):
    retailer_name = "euronics"

    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        results: List[PromoResult] = []
        page = await self.new_page()

        try:
            query = f"{product_brand} {product_model}"
            # IMPORTANT: Euronics uses ?q= not ?query=
            search_url = f"https://www.euronics.it/search?q={query.replace(' ', '+')}"

            logger.info("[euronics] Navigating to: %s", search_url)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            await self._dismiss_cookies(page)

            # Real selector: .product-grid .product
            cards = await page.query_selector_all(".product-grid .product")
            logger.info("[euronics] Found %d product cards for '%s'", len(cards), query)

            for card in cards[:12]:
                promo = await self._extract_card(card, product_model, product_brand, listino_eur, search_url)
                if promo:
                    results.append(promo)

            # JS fallback: extract from data-obj attributes
            if not results:
                logger.info("[euronics] CSS extraction found nothing, trying data-obj fallback")
                results = await self._extract_from_data_obj(page, product_model, product_brand, listino_eur, search_url)

        finally:
            await page.close()

        logger.info("[euronics] Total results for '%s %s': %d", product_brand, product_model, len(results))
        return results

    async def _extract_card(
        self, card, product_model: str, product_brand: str, listino_eur: float, fallback_url: str
    ) -> Optional[PromoResult]:
        try:
            # Title from .tile-name
            title_el = await card.query_selector(".tile-name")
            title = (await title_el.inner_text()).strip() if title_el else ""

            if not self._is_matching_product(title, product_model, product_brand):
                return None

            logger.info("[euronics] Matched: %s", title[:80])

            # Promo price from .discount .price-formatted
            prezzo_promo = None
            price_el = await card.query_selector(".discount .price-formatted")
            if price_el:
                prezzo_promo = self._parse_price(await price_el.inner_text())

            # Fallback: try data-obj JSON
            if prezzo_promo is None:
                tile = await card.query_selector(".new-product-tile")
                if tile:
                    data_obj = await tile.get_attribute("data-obj")
                    if data_obj:
                        try:
                            obj = json.loads(data_obj)
                            prezzo_promo = float(obj.get("price", 0))
                        except (json.JSONDecodeError, ValueError):
                            pass

            if not prezzo_promo or prezzo_promo < 10:
                return None

            # Original price from .more-price-details .value
            prezzo_originale = None
            orig_el = await card.query_selector(".more-price-details .value")
            if orig_el:
                prezzo_originale = self._parse_price(await orig_el.inner_text())

            if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                prezzo_originale = listino_eur

            if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                return None

            # Link from a.link-pdp
            url = fallback_url
            link_el = await card.query_selector("a.link-pdp")
            if link_el:
                href = await link_el.get_attribute("href")
                if href:
                    url = href if href.startswith("http") else f"https://www.euronics.it{href}"

            sconto = self._calc_discount(prezzo_originale, prezzo_promo)

            logger.info("[euronics] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                        title[:60], prezzo_originale, prezzo_promo, sconto)

            return PromoResult(
                retailer="euronics", retailer_variant=None,
                prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
                sconto_percentuale=sconto, data_inizio=date.today(),
                data_fine=None, url_fonte=url, promo_tag="Sconto Euronics",
            )
        except Exception as e:
            logger.debug("[euronics] Error parsing card: %s", e)
            return None

    async def _extract_from_data_obj(
        self, page, product_model: str, product_brand: str, listino_eur: float, fallback_url: str
    ) -> List[PromoResult]:
        """Fallback: extract product data from data-obj JSON attributes."""
        results = []
        try:
            data = await page.evaluate("""() => {
                const tiles = document.querySelectorAll('.new-product-tile[data-obj]');
                const items = [];
                for (const tile of tiles) {
                    try {
                        const obj = JSON.parse(tile.getAttribute('data-obj'));
                        const card = tile.closest('.product');
                        const titleEl = card ? card.querySelector('.tile-name') : null;
                        const origEl = card ? card.querySelector('.more-price-details .value') : null;
                        const linkEl = card ? card.querySelector('a.link-pdp') : null;
                        items.push({
                            name: obj.name || '',
                            brand: obj.brand || '',
                            price: obj.price || '0',
                            title: titleEl ? titleEl.textContent.trim() : '',
                            origPrice: origEl ? origEl.textContent.trim() : '',
                            href: linkEl ? linkEl.getAttribute('href') : '',
                        });
                    } catch(e) {}
                }
                return items;
            }""")

            for item in (data or []):
                title = item.get("title") or item.get("name", "")
                if not self._is_matching_product(title, product_model, product_brand):
                    continue

                prezzo_promo = None
                try:
                    prezzo_promo = float(item.get("price", "0"))
                except ValueError:
                    continue
                if not prezzo_promo or prezzo_promo < 10:
                    continue

                prezzo_originale = self._parse_price(item.get("origPrice", ""))
                if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                    prezzo_originale = listino_eur
                if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                    continue

                href = item.get("href", "")
                url = href if href and href.startswith("http") else (
                    f"https://www.euronics.it{href}" if href else fallback_url
                )

                sconto = self._calc_discount(prezzo_originale, prezzo_promo)
                logger.info("[euronics][data-obj] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                            title[:60], prezzo_originale, prezzo_promo, sconto)

                results.append(PromoResult(
                    retailer="euronics", retailer_variant=None,
                    prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
                    sconto_percentuale=sconto, data_inizio=date.today(),
                    data_fine=None, url_fonte=url, promo_tag="Sconto Euronics",
                ))

        except Exception as e:
            logger.warning("[euronics] data-obj extraction failed: %s", e)

        return results
