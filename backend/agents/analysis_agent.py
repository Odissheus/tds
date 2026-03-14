"""
Analysis Agent — runs Friday 07:30, analyzes weekly promotions via Claude API.
"""
import json
import logging
import time
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select

from backend.config import settings
from backend.database import sync_session_factory
from backend.models.product import Product
from backend.models.promotion import Promotion

logger = logging.getLogger("tds.agent.analysis")

ANALYSIS_SYSTEM_PROMPT = """Sei un analista BI senior specializzato in consumer electronics per il mercato italiano, che lavora per React SRL sul sistema TDS Tech Deep Search. Il tuo interlocutore è Tania, responsabile Business Intelligence per il marketing di Google Pixel in Italia.

Analizza i dati di promozione della settimana e produci:
(1) Sintesi delle migliori offerte Google Pixel per retailer, divise per categoria — smartphone, earable, wearable, accessori, bundle
(2) Analisi promozioni competitor per fascia di prezzo equivalente ai Pixel attivi, anch'essa divisa per categoria
(3) Identificazione dei momenti in cui conviene spingere sul canale fisico, basata sui gap di prezzo tra Pixel e competitor nella stessa fascia
(4) Alert su prodotti EOL competitor in promozione anomala
(5) Insight strategici e raccomandazioni trade marketing per la settimana

Tono professionale, diretto, come una collega esperta. Parla sempre in italiano. Non usare eccessivi bullet point — scrivi in modo fluido e leggibile.

Restituisci il risultato come JSON con queste chiavi:
- "pixel_smartphone": analisi offerte Pixel smartphone
- "pixel_earable_wearable": analisi offerte Pixel earable, wearable, accessori
- "pixel_bundles": bundle rilevati
- "competitor_smartphone": analisi competitor smartphone
- "competitor_earable_wearable": analisi competitor earable e wearable
- "eol_alerts": prodotti EOL in promozione anomala
- "insights": insight strategici e raccomandazioni
- "top_highlights": array di 3 stringhe con i top highlights della settimana (per l'email)"""

# Fallback analysis when Claude API fails
FALLBACK_ANALYSIS = {
    "pixel_smartphone": "Analisi AI non disponibile — consultare i dati grezzi nel report.",
    "pixel_earable_wearable": "Analisi AI non disponibile.",
    "pixel_bundles": "Nessun bundle analizzato.",
    "competitor_smartphone": "Analisi AI non disponibile — consultare la dashboard per i dati competitor.",
    "competitor_earable_wearable": "Analisi AI non disponibile.",
    "eol_alerts": "Nessun alert EOL disponibile.",
    "insights": "Analisi AI non disponibile questa settimana. I dati grezzi sono inclusi nel report PDF.",
    "top_highlights": [
        "Report generato con dati grezzi (analisi AI non disponibile)",
        "Consultare la dashboard TDS per i dettagli",
        "Dati aggiornati alla settimana corrente",
    ],
}


def get_current_week_str() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"


def _build_promo_data(week: str) -> list:
    """Load promotions from DB and build the data list for analysis."""
    with sync_session_factory() as session:
        promotions = (
            session.execute(
                select(Promotion)
                .where(Promotion.settimana == week)
                .order_by(Promotion.sconto_percentuale.desc())
            )
            .scalars()
            .all()
        )

        products = session.execute(select(Product)).scalars().all()
        products_map = {str(p.id): p for p in products}

        promo_data = []
        for promo in promotions:
            product = products_map.get(str(promo.product_id))
            if not product:
                continue
            promo_data.append(
                {
                    "brand": product.brand,
                    "model": product.model,
                    "series": product.series,
                    "category": product.category.value,
                    "tier": product.tier,
                    "is_google": product.is_google,
                    "status": product.status.value,
                    "listino_eur": product.listino_eur,
                    "retailer": promo.retailer,
                    "retailer_variant": promo.retailer_variant,
                    "prezzo_originale": promo.prezzo_originale,
                    "prezzo_promo": promo.prezzo_promo,
                    "sconto_percentuale": promo.sconto_percentuale,
                    "data_inizio": str(promo.data_inizio),
                    "data_fine": str(promo.data_fine) if promo.data_fine else None,
                    "url_fonte": promo.url_fonte,
                }
            )

    return promo_data


def _select_top_promos(promo_data: list, limit: int) -> list:
    """Select the top N promos by discount, ensuring Google products are included."""
    google = [p for p in promo_data if p["is_google"]]
    competitor = [p for p in promo_data if not p["is_google"]]

    # Take all Google promos (usually fewer) + fill remaining with top competitor
    selected = google[:limit]
    remaining = limit - len(selected)
    if remaining > 0:
        selected.extend(competitor[:remaining])

    return selected


def _call_claude(promo_data: list, week: str, total_count: int) -> dict:
    """Call Claude API with the given promo data. Returns parsed analysis dict."""
    user_message = f"""Ecco le top {len(promo_data)} promozioni con sconto maggiore per la settimana {week} (su {total_count} totali rilevate):

{json.dumps(promo_data, indent=2, ensure_ascii=False)}

Totale promozioni rilevate: {total_count}
Di cui Google Pixel: {sum(1 for p in promo_data if p['is_google'])}
Di cui competitor: {sum(1 for p in promo_data if not p['is_google'])}

Analizza questi dati e produci il report strutturato come specificato."""

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=4096,
        system=ANALYSIS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = response.content[0].text

    try:
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
        else:
            json_str = response_text.strip()

        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse Claude response as JSON, using raw text")
        return {
            "pixel_smartphone": response_text,
            "pixel_earable_wearable": "",
            "pixel_bundles": "",
            "competitor_smartphone": "",
            "competitor_earable_wearable": "",
            "eol_alerts": "",
            "insights": "",
            "top_highlights": ["Analisi settimanale completata", "Vedi report PDF per dettagli", ""],
        }


def run_weekly_analysis(week: str = None) -> dict:
    """Run the weekly analysis using Claude API.

    Sends only top 20 promos by discount to avoid rate limits.
    If rate-limited, retries once with top 10 after 60s.
    If all API calls fail, returns fallback data so reports still generate.
    """
    if not week:
        week = get_current_week_str()

    logger.info("Running weekly analysis for %s", week)

    promo_data = _build_promo_data(week)

    if not promo_data:
        logger.warning("No promotions found for week %s", week)
        return {
            "pixel_smartphone": "Nessuna promozione Pixel smartphone rilevata questa settimana.",
            "pixel_earable_wearable": "Nessuna promozione Pixel earable/wearable rilevata.",
            "pixel_bundles": "Nessun bundle rilevato.",
            "competitor_smartphone": "Nessuna promozione competitor smartphone rilevata.",
            "competitor_earable_wearable": "Nessuna promozione competitor earable/wearable rilevata.",
            "eol_alerts": "Nessun alert EOL.",
            "insights": "Dati insufficienti per insight questa settimana.",
            "top_highlights": [
                "Nessuna promozione rilevata questa settimana",
                "Verificare lo stato degli scraper",
                "Controllare la disponibilità dei siti retailer",
            ],
        }

    total_count = len(promo_data)

    # First attempt: top 20 promos
    top_promos = _select_top_promos(promo_data, 20)
    logger.info("Sending %d/%d promos to Claude API (top by discount)", len(top_promos), total_count)

    try:
        analysis = _call_claude(top_promos, week, total_count)
        logger.info("Weekly analysis completed for %s", week)
        return analysis

    except anthropic.RateLimitError as e:
        logger.warning("Rate limited by Anthropic API, waiting 60s then retrying with fewer promos: %s", e)
        time.sleep(60)

        # Retry with top 10
        top_promos_small = _select_top_promos(promo_data, 10)
        logger.info("Retry: sending %d/%d promos to Claude API", len(top_promos_small), total_count)

        try:
            analysis = _call_claude(top_promos_small, week, total_count)
            logger.info("Weekly analysis completed on retry for %s", week)
            return analysis
        except Exception as e2:
            logger.error("Claude API retry also failed: %s", e2)
            return FALLBACK_ANALYSIS

    except Exception as e:
        logger.error("Claude API call failed: %s", e)
        return FALLBACK_ANALYSIS
