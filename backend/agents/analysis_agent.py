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

ANALYSIS_SYSTEM_PROMPT = """Sei un analista BI senior per React SRL, sistema TDS Tech Deep Search. Il report è per il team marketing Google Pixel Italia.

Analizza i dati di promozione settimanale e produci:
- 3 insight strategici su opportunità/rischi per Google Pixel 10 e Pixel 9 rispetto ai competitor
- 1 raccomandazione concreta per il team trade marketing
- Tono professionale business, zero linguaggio tecnico, zero allarmi di sistema
- Max 250 parole totali

Restituisci JSON con:
- "ai_insights": testo unico con i 3 insight + 1 raccomandazione (max 250 parole, italiano)
- "top_highlights": array di 3 stringhe brevi per l'email (max 15 parole ciascuna)"""

# Fallback analysis when Claude API fails
FALLBACK_ANALYSIS = {
    "ai_insights": "Analisi AI non disponibile questa settimana. Consultare i dati nel report PDF.",
    "top_highlights": [
        "Report generato con dati grezzi",
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
            "ai_insights": response_text,
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
            "ai_insights": "Nessuna promozione rilevata questa settimana. Dati insufficienti per l'analisi.",
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
