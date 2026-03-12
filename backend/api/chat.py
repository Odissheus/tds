"""
Chat API — streaming LLM chat with tool_use for Tania.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session, sync_session_factory
from backend.models.product import Product
from backend.models.promotion import Promotion

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger("tds.api.chat")

CHAT_SYSTEM_PROMPT = """Sei l'assistente BI di TDS Tech Deep Search, sistema di React SRL. Aiuti Tania, responsabile BI per Google Pixel Italia, ad analizzare i dati di monitoraggio volantini dei retailer italiani (Euronics, Unieuro, MediaWorld).

Hai accesso ai dati di promozione settimanali per Google Pixel e tutti i competitor. Rispondi sempre in italiano, in modo professionale ma diretto.

Quando generi report PDF, strutturali in modo chiaro con le sezioni appropriate. Se Tania chiede di stampare o esportare qualcosa, usa sempre il tool generate_custom_report."""

TOOLS = [
    {
        "name": "get_promotions",
        "description": "Recupera le promozioni dal database, filtrando per brand, categoria, retailer e settimana.",
        "input_schema": {
            "type": "object",
            "properties": {
                "brand": {"type": "string", "description": "Filtra per brand (es. Google, Samsung)"},
                "category": {"type": "string", "description": "Filtra per categoria (smartphone, earable, wearable, accessory, bundle)"},
                "retailer": {"type": "string", "description": "Filtra per retailer (euronics, unieuro, mediaworld)"},
                "week": {"type": "string", "description": "Settimana ISO (es. 2026-W11). Default: settimana corrente."},
            },
        },
    },
    {
        "name": "get_price_history",
        "description": "Recupera lo storico prezzi di un prodotto specifico.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "UUID del prodotto"},
                "days": {"type": "integer", "description": "Numero di giorni di storico (default 90)"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "compare_competitors",
        "description": "Confronta un modello Pixel con competitor nella stessa fascia di prezzo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pixel_model": {"type": "string", "description": "Nome modello Pixel da confrontare"},
                "week": {"type": "string", "description": "Settimana ISO (default: corrente)"},
            },
            "required": ["pixel_model"],
        },
    },
    {
        "name": "get_products",
        "description": "Recupera i prodotti dal catalogo monitorato.",
        "input_schema": {
            "type": "object",
            "properties": {
                "brand": {"type": "string"},
                "category": {"type": "string"},
                "tier": {"type": "integer"},
                "is_google": {"type": "boolean"},
                "status": {"type": "string"},
            },
        },
    },
    {
        "name": "generate_custom_report",
        "description": "Genera un report PDF personalizzato con titolo e sezioni specifiche.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titolo del report"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                    "description": "Sezioni del report",
                },
                "week": {"type": "string", "description": "Settimana ISO (default: corrente)"},
            },
            "required": ["title", "sections"],
        },
    },
]


def _get_current_week() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"


def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call and return the result as a string."""
    with sync_session_factory() as session:
        if tool_name == "get_promotions":
            week = tool_input.get("week") or _get_current_week()
            query = (
                select(Promotion, Product)
                .join(Product, Promotion.product_id == Product.id)
                .where(Promotion.settimana == week)
            )
            if tool_input.get("brand"):
                query = query.where(Product.brand.ilike(f"%{tool_input['brand']}%"))
            if tool_input.get("category"):
                query = query.where(Product.category == tool_input["category"])
            if tool_input.get("retailer"):
                query = query.where(Promotion.retailer == tool_input["retailer"])

            results = session.execute(query).all()
            promos = []
            for promo, product in results:
                promos.append({
                    "brand": product.brand,
                    "model": product.model,
                    "category": product.category.value,
                    "retailer": promo.retailer,
                    "retailer_variant": promo.retailer_variant,
                    "prezzo_originale": promo.prezzo_originale,
                    "prezzo_promo": promo.prezzo_promo,
                    "sconto_percentuale": promo.sconto_percentuale,
                    "data_inizio": str(promo.data_inizio),
                    "data_fine": str(promo.data_fine) if promo.data_fine else None,
                    "url_fonte": promo.url_fonte,
                })
            return json.dumps(promos, ensure_ascii=False)

        elif tool_name == "get_price_history":
            from datetime import timedelta
            days = tool_input.get("days", 90)
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            results = session.execute(
                select(Promotion)
                .where(
                    Promotion.product_id == tool_input["product_id"],
                    Promotion.scraped_at >= cutoff,
                )
                .order_by(Promotion.scraped_at)
            ).scalars().all()

            history = [
                {
                    "retailer": p.retailer,
                    "prezzo_promo": p.prezzo_promo,
                    "sconto_percentuale": p.sconto_percentuale,
                    "settimana": p.settimana,
                    "data_inizio": str(p.data_inizio),
                }
                for p in results
            ]
            return json.dumps(history, ensure_ascii=False)

        elif tool_name == "compare_competitors":
            week = tool_input.get("week") or _get_current_week()
            pixel = session.execute(
                select(Product).where(
                    Product.model.ilike(f"%{tool_input['pixel_model']}%"),
                    Product.is_google == True,
                )
            ).scalar_one_or_none()

            if not pixel:
                return json.dumps({"error": f"Prodotto Pixel '{tool_input['pixel_model']}' non trovato"})

            price_range_low = (pixel.listino_eur or 0) * 0.7
            price_range_high = (pixel.listino_eur or 9999) * 1.3

            competitors = session.execute(
                select(Product).where(
                    Product.is_google == False,
                    Product.category == pixel.category,
                    Product.listino_eur >= price_range_low,
                    Product.listino_eur <= price_range_high,
                    Product.status != "disabled",
                )
            ).scalars().all()

            comp_promos = []
            for comp in competitors:
                promos = session.execute(
                    select(Promotion).where(
                        Promotion.product_id == comp.id,
                        Promotion.settimana == week,
                    )
                ).scalars().all()
                for p in promos:
                    comp_promos.append({
                        "brand": comp.brand,
                        "model": comp.model,
                        "listino": comp.listino_eur,
                        "retailer": p.retailer,
                        "prezzo_promo": p.prezzo_promo,
                        "sconto_percentuale": p.sconto_percentuale,
                    })

            pixel_promos = session.execute(
                select(Promotion).where(
                    Promotion.product_id == pixel.id,
                    Promotion.settimana == week,
                )
            ).scalars().all()

            result = {
                "pixel": {
                    "model": pixel.model,
                    "listino": pixel.listino_eur,
                    "promos": [
                        {"retailer": p.retailer, "prezzo_promo": p.prezzo_promo, "sconto": p.sconto_percentuale}
                        for p in pixel_promos
                    ],
                },
                "competitors": comp_promos,
            }
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "get_products":
            query = select(Product)
            if tool_input.get("brand"):
                query = query.where(Product.brand.ilike(f"%{tool_input['brand']}%"))
            if tool_input.get("category"):
                query = query.where(Product.category == tool_input["category"])
            if tool_input.get("tier"):
                query = query.where(Product.tier == tool_input["tier"])
            if tool_input.get("is_google") is not None:
                query = query.where(Product.is_google == tool_input["is_google"])
            if tool_input.get("status"):
                query = query.where(Product.status == tool_input["status"])

            products = session.execute(query.order_by(Product.brand, Product.model)).scalars().all()
            return json.dumps(
                [
                    {
                        "id": str(p.id),
                        "brand": p.brand,
                        "model": p.model,
                        "series": p.series,
                        "category": p.category.value,
                        "tier": p.tier,
                        "is_google": p.is_google,
                        "listino_eur": p.listino_eur,
                        "status": p.status.value,
                    }
                    for p in products
                ],
                ensure_ascii=False,
            )

        elif tool_name == "generate_custom_report":
            from backend.agents.report_agent import generate_custom_report

            pdf_path = generate_custom_report(
                title=tool_input["title"],
                sections=tool_input["sections"],
                week=tool_input.get("week"),
                generated_by="tania_chat",
            )
            return json.dumps({"status": "success", "pdf_path": pdf_path, "download_url": f"/api/reports/download/latest"})

        return json.dumps({"error": f"Tool '{tool_name}' non trovato"})


class ChatRequest(BaseModel):
    message: str
    conversation_history: list = []


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint with Claude tool_use."""

    messages = []
    for msg in request.conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": request.message})

    async def generate():
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        current_messages = list(messages)
        max_iterations = 10

        for _ in range(max_iterations):
            response = client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=4096,
                system=CHAT_SYSTEM_PROMPT,
                tools=TOOLS,
                messages=current_messages,
            )

            has_tool_use = False
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    yield f"data: {json.dumps({'type': 'text', 'content': block.text})}\n\n"
                elif block.type == "tool_use":
                    has_tool_use = True
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': block.name, 'input': block.input})}\n\n"

                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                    if block.name == "generate_custom_report":
                        result_data = json.loads(result)
                        if result_data.get("status") == "success":
                            yield f"data: {json.dumps({'type': 'pdf_ready', 'pdf_path': result_data['pdf_path']})}\n\n"

            if not has_tool_use:
                break

            current_messages.append({"role": "assistant", "content": response.content})
            current_messages.append({"role": "user", "content": tool_results})

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("")
async def chat_sync(request: ChatRequest):
    """Non-streaming chat endpoint (fallback)."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    messages = []
    for msg in request.conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": request.message})

    current_messages = list(messages)
    full_response = ""

    for _ in range(10):
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            system=CHAT_SYSTEM_PROMPT,
            tools=TOOLS,
            messages=current_messages,
        )

        has_tool_use = False
        tool_results = []

        for block in response.content:
            if block.type == "text":
                full_response += block.text
            elif block.type == "tool_use":
                has_tool_use = True
                result = _execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        if not has_tool_use:
            break

        current_messages.append({"role": "assistant", "content": response.content})
        current_messages.append({"role": "user", "content": tool_results})

    return {"response": full_response}
