"""
Product Agent — uses Claude API to auto-complete product details.
"""
import json
import logging

import anthropic

from backend.config import settings

logger = logging.getLogger("tds.agent.product")

SUGGEST_PROMPT = """Dato questo prodotto consumer electronics: '{model_name_raw}' del brand '{brand}', restituisci SOLO un JSON con i campi:
- series: la serie di appartenenza (es. "Galaxy S25", "Pixel 10", "iPhone 17")
- model: nome completo corretto del modello
- category: una tra smartphone|earable|wearable|accessory|bundle
- listino_eur: prezzo di listino italiano stimato in float
- tier_suggested: 1 se è un prodotto attivamente commercializzato nel 2025-2026, 2 se è EOL o in uscita di catalogo
- notes: stringa breve con motivazione del tier suggerito

Nessun testo fuori dal JSON."""

BATCH_IMPORT_PROMPT = """Ricevi una lista di prodotti consumer electronics in formato libero. Per ciascun prodotto, restituisci un array JSON dove ogni elemento ha:
- brand: il brand del prodotto
- series: la serie di appartenenza
- model: nome completo corretto
- category: una tra smartphone|earable|wearable|accessory|bundle
- listino_eur: prezzo di listino italiano stimato in float
- tier_suggested: 1 se attivamente commercializzato 2025-2026, 2 se EOL
- is_google: true se è un prodotto Google Pixel, false altrimenti
- notes: breve motivazione

Lista prodotti:
{product_list}

Restituisci SOLO l'array JSON, nessun testo aggiuntivo."""


def suggest_product(brand: str, model_name_raw: str) -> dict:
    """Use Claude to suggest product details."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = SUGGEST_PROMPT.format(brand=brand, model_name_raw=model_name_raw)

    try:
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()

        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
        else:
            json_str = response_text

        result = json.loads(json_str)
        logger.info("Product suggestion for '%s %s': %s", brand, model_name_raw, result)
        return result

    except Exception as e:
        logger.error("Product suggestion failed: %s", str(e))
        return {
            "series": "",
            "model": model_name_raw,
            "category": "smartphone",
            "listino_eur": 0,
            "tier_suggested": 1,
            "notes": f"Suggerimento automatico non disponibile: {str(e)}",
        }


def batch_import_suggest(product_list_text: str) -> list:
    """Use Claude to parse and suggest details for a batch of products."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = BATCH_IMPORT_PROMPT.format(product_list=product_list_text)

    try:
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()

        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
        else:
            json_str = response_text

        result = json.loads(json_str)
        if not isinstance(result, list):
            result = [result]

        logger.info("Batch import suggestion: %d products parsed", len(result))
        return result

    except Exception as e:
        logger.error("Batch import suggestion failed: %s", str(e))
        return []
