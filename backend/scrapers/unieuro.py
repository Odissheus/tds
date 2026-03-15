"""
Unieuro.it scraper — based on real HTML structure captured March 2026.

Unieuro uses an Angular/Ionic SPA. URL-based search returns 404.
Must navigate to homepage, type in search input, press Enter.

Product card: app-product
Title: .product-description (p element)
Prices: extracted from card innerText (format: "Ora\n€ 539,90\nPrezzo consigliato 769,90")
Link: a.product-link-title[href]
"""
import logging
import re
from datetime import date
from typing import List, Optional

from backend.scrapers.base_scraper import BaseScraper, PromoResult, extract_storage_gb, detect_bundle

logger = logging.getLogger("tds.scraper.unieuro")

# Regex for Italian prices
PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")


class UnieuroScraper(BaseScraper):
    retailer_name = "unieuro"

    async def search_product(
        self, product_model: str, product_brand: str, listino_eur: float = 0
    ) -> List[PromoResult]:
        results: List[PromoResult] = []
        page = await self.new_page()

        try:
            query = f"{product_brand} {product_model}"

            # Navigate to homepage first — URL-based search returns 404
            logger.info("[unieuro] Navigating to homepage to search for '%s'", query)
            await page.goto("https://www.unieuro.it", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Dismiss cookies
            try:
                cookie_btn = await page.query_selector("text=Accetta tutti i cookie")
                if cookie_btn:
                    await cookie_btn.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Find search input and type query
            search_input = await page.query_selector('input[placeholder="Cosa cerchi?"]')
            if not search_input:
                logger.warning("[unieuro] Search input not found")
                return results

            await search_input.click()
            await page.wait_for_timeout(500)
            await search_input.fill(query)
            await page.wait_for_timeout(2000)
            await search_input.press("Enter")
            await page.wait_for_timeout(8000)

            logger.info("[unieuro] After search, URL: %s", page.url)

            # Extract products via JS — Angular SPA with app-product components
            data = await page.evaluate("""(args) => {
                const [brand, model] = args;
                const brandLower = brand.toLowerCase();
                const modelParts = model.toLowerCase().split(' ');
                const cards = document.querySelectorAll('app-product');
                const results = [];

                for (const card of cards) {
                    const titleEl = card.querySelector('.product-description');
                    const title = titleEl ? titleEl.textContent.trim() : '';
                    const titleLower = title.toLowerCase();

                    // Check match
                    if (!titleLower.includes(brandLower)) continue;
                    const matchCount = modelParts.filter(p => titleLower.includes(p)).length;
                    if (matchCount < Math.max(1, modelParts.length * 0.5)) continue;

                    // Extract prices from card text
                    const text = card.innerText || '';
                    const priceRe = /(\d{1,3}(?:\.\d{3})*,\d{2})/g;
                    const prices = [];
                    let m;
                    while ((m = priceRe.exec(text)) !== null) {
                        const raw = m[1].replace(/\./g, '').replace(',', '.');
                        const val = parseFloat(raw);
                        if (val > 10) prices.push(val);
                    }

                    // Extract link
                    const linkEl = card.querySelector('a.product-link-title, a[href*="pid"]');
                    const href = linkEl ? linkEl.getAttribute('href') : '';

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

            logger.info("[unieuro] JS extraction found %d matching products", len(data or []))

            for item in (data or []):
                title = item.get("title", "")
                storage = extract_storage_gb(title)
                is_bundle, bundle_desc = detect_bundle(title)

                # Filter out installment prices (< €15) and sort
                prices = sorted([p for p in item.get("prices", []) if p >= 15])
                if not prices:
                    continue

                prezzo_promo = prices[0]
                prezzo_originale = prices[-1] if len(prices) > 1 and prices[-1] > prezzo_promo else None

                if prezzo_originale is None and listino_eur and listino_eur > prezzo_promo:
                    prezzo_originale = listino_eur

                if prezzo_originale is None or prezzo_originale <= prezzo_promo:
                    continue

                sconto = self._calc_discount(prezzo_originale, prezzo_promo)

                # Skip implausible discounts (>60% usually means installment price was grabbed)
                if sconto > 60:
                    logger.info("[unieuro] SKIPPED (discount too high %.1f%%): %s",
                                sconto, item.get("title", "")[:60])
                    continue

                href = item.get("href", "")
                url = href if href and href.startswith("http") else (
                    f"https://www.unieuro.it{href}" if href else "https://www.unieuro.it"
                )

                logger.info("[unieuro] PROMO: %s | %.2f -> %.2f (%.1f%%)",
                            item.get("title", "")[:60], prezzo_originale, prezzo_promo, sconto)

                results.append(PromoResult(
                    retailer="unieuro", retailer_variant=None,
                    prezzo_originale=prezzo_originale, prezzo_promo=prezzo_promo,
                    sconto_percentuale=sconto, data_inizio=date.today(),
                    data_fine=None, url_fonte=url, promo_tag="Sconto Unieuro",
                    storage_gb=storage, is_bundle=is_bundle, bundle_description=bundle_desc,
                ))

        finally:
            await page.close()

        logger.info("[unieuro] Total results for '%s %s': %d", product_brand, product_model, len(results))
        return results
