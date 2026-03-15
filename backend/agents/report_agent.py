"""
Report Agent — generates PDF reports using WeasyPrint + matplotlib.
"""
import base64
import io
import logging
import os
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from jinja2 import Template
from sqlalchemy import select
from weasyprint import HTML

from backend.config import settings
from backend.database import sync_session_factory
from backend.models.product import Product
from backend.models.promotion import Promotion
from backend.models.report import Report, ReportTypeEnum

# These utilities live in base_scraper; we don't call them here because
# storage_gb / is_bundle are already populated on the Promotion model
# by the scraper pipeline.  Imported only so the dependency is explicit.
from backend.scrapers.base_scraper import extract_storage_gb, detect_bundle  # noqa: F401

logger = logging.getLogger("tds.agent.report")

# Canonical retailer keys used in the price grid columns
_RETAILER_KEYS = ("amazon", "euronics", "unieuro", "mediaworld")


def _get_week_dates(week_str: str) -> tuple:
    """Get Monday and Sunday dates from a week string like '2026-W11'."""
    year, week = week_str.split("-W")
    monday = datetime.strptime(f"{year}-W{int(week)}-1", "%Y-W%W-%w").date()
    if monday.year != int(year):
        monday = date.fromisocalendar(int(year), int(week), 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _generate_price_chart(promos_data: list) -> str:
    """Generate a bar chart comparing Pixel vs competitor prices, return base64."""
    if not promos_data:
        return ""

    fig, ax = plt.subplots(figsize=(10, 5))

    google_promos = [p for p in promos_data if p.get("is_google")]
    competitor_promos = [p for p in promos_data if not p.get("is_google")]

    labels = []
    google_prices = []
    competitor_prices = []

    price_ranges = [
        ("Budget (< 300€)", 0, 300),
        ("Mid (300-600€)", 300, 600),
        ("High (600-900€)", 600, 900),
        ("Premium (> 900€)", 900, 9999),
    ]

    for label, low, high in price_ranges:
        g_prices = [p["prezzo_promo"] for p in google_promos if low <= p["prezzo_promo"] < high]
        c_prices = [p["prezzo_promo"] for p in competitor_promos if low <= p["prezzo_promo"] < high]

        if g_prices or c_prices:
            labels.append(label)
            google_prices.append(sum(g_prices) / len(g_prices) if g_prices else 0)
            competitor_prices.append(sum(c_prices) / len(c_prices) if c_prices else 0)

    if not labels:
        plt.close(fig)
        return ""

    x = range(len(labels))
    width = 0.35

    bars1 = ax.bar([i - width / 2 for i in x], google_prices, width, label="Google Pixel", color="#4285F4")
    bars2 = ax.bar([i + width / 2 for i in x], competitor_prices, width, label="Competitor", color="#EA4335")

    ax.set_ylabel("Prezzo Medio Promo (€)", fontsize=10)
    ax.set_title("Prezzi Promo: Google Pixel vs Competitor", fontsize=12, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _generate_discount_trend_chart(weekly_data: list) -> str:
    """Generate a line chart of Google discount trends over weeks."""
    if not weekly_data or len(weekly_data) < 2:
        return ""

    fig, ax = plt.subplots(figsize=(10, 4))

    weeks = [d["week"] for d in weekly_data]
    avg_discounts = [d["avg_discount"] for d in weekly_data]

    ax.plot(weeks, avg_discounts, marker="o", color="#34A853", linewidth=2, markersize=6)
    ax.fill_between(weeks, avg_discounts, alpha=0.1, color="#34A853")

    ax.set_ylabel("Sconto Medio (%)", fontsize=10)
    ax.set_title("Trend Sconti Google Pixel", fontsize=12, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=45, fontsize=8)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ---------------------------------------------------------------------------
#  Helpers for the new grid-based weekly report
# ---------------------------------------------------------------------------

def _normalize_retailer(retailer: str) -> str:
    """Map retailer name to a canonical lowercase key."""
    r = retailer.strip().lower()
    for key in _RETAILER_KEYS:
        if key in r:
            return key
    return r


def _series_match(series: str, target: str) -> bool:
    """Check if a product series string matches 'Pixel 10' or 'Pixel 9'."""
    return target.lower() in series.lower()


def _build_price_grid(promos: list, products_map: dict, series_name: str) -> list:
    """
    Build a price-comparison grid for a given Pixel series.

    Groups non-bundle Google promos by (model, storage_gb).
    For each group, shows the best (lowest) price per retailer.

    Returns a list of grid-row dicts sorted by model then storage.
    """
    # bucket: (model, storage_gb) -> {retailer_key: lowest_price, ...}
    buckets: dict[tuple, dict] = defaultdict(lambda: {
        "listino": None,
        "prices": {},          # retailer_key -> lowest prezzo_promo
        "data_inizio": None,
        "data_fine": None,
    })

    for p in promos:
        product = products_map.get(str(p["product_id"]))
        if product is None:
            continue
        if not product.is_google:
            continue
        if product.category.value != "smartphone":
            continue
        if not _series_match(product.series, series_name):
            continue
        if p.get("is_bundle"):
            continue

        storage = p.get("storage_gb") or 0
        key = (product.model, storage)
        bucket = buckets[key]

        # Listino from product catalogue
        if bucket["listino"] is None and product.listino_eur:
            bucket["listino"] = product.listino_eur

        rkey = _normalize_retailer(p["retailer"])
        current = bucket["prices"].get(rkey)
        if current is None or p["prezzo_promo"] < current:
            bucket["prices"][rkey] = p["prezzo_promo"]

        # Track earliest data_inizio / latest data_fine
        di = p.get("data_inizio")
        if di and (bucket["data_inizio"] is None or di < bucket["data_inizio"]):
            bucket["data_inizio"] = di
        df = p.get("data_fine")
        if df and df != "\u2014":
            if bucket["data_fine"] is None or df > bucket["data_fine"]:
                bucket["data_fine"] = df

    # Convert buckets to grid rows
    grid = []
    for (model, storage), bucket in buckets.items():
        prices = bucket["prices"]
        if not prices:
            continue

        best_price = min(prices.values())
        best_retailer = min(prices, key=prices.get)

        listino = bucket["listino"]
        best_sconto = 0.0
        if listino and listino > 0:
            best_sconto = round((1 - best_price / listino) * 100, 1)

        grid.append({
            "model": model,
            "storage_gb": storage,
            "listino": listino,
            "amazon": prices.get("amazon"),
            "euronics": prices.get("euronics"),
            "unieuro": prices.get("unieuro"),
            "mediaworld": prices.get("mediaworld"),
            "best_price": best_price,
            "best_sconto": best_sconto,
            "best_retailer": best_retailer,
            "data_inizio": str(bucket["data_inizio"]) if bucket["data_inizio"] else "\u2014",
            "data_fine": str(bucket["data_fine"]) if bucket["data_fine"] else "\u2014",
        })

    # Sort: model name, then storage ascending
    grid.sort(key=lambda r: (r["model"], r["storage_gb"]))
    return grid


# ---------------------------------------------------------------------------
#  Main weekly report
# ---------------------------------------------------------------------------

def generate_weekly_report(week: str, analysis: dict) -> str:
    """Generate the weekly PDF report.  Returns the PDF file path."""
    monday, sunday = _get_week_dates(week)
    now = datetime.now(timezone.utc)

    os.makedirs(settings.REPORTS_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load data from DB
    # ------------------------------------------------------------------
    with sync_session_factory() as session:
        promotions = (
            session.execute(
                select(Promotion)
                .where(Promotion.settimana == week)
                .order_by(Promotion.retailer)
            )
            .scalars()
            .all()
        )

        products = session.execute(select(Product)).scalars().all()
        products_map = {str(p.id): p for p in products}

        # Build flat promo list with extra fields from the Promotion model
        promos_data = []
        for promo in promotions:
            product = products_map.get(str(promo.product_id))
            if not product:
                continue
            promos_data.append({
                "product_id": str(promo.product_id),
                "brand": product.brand,
                "model": product.model,
                "series": product.series,
                "category": product.category.value,
                "tier": product.tier,
                "is_google": product.is_google,
                "status": product.status.value,
                "retailer": promo.retailer,
                "retailer_variant": promo.retailer_variant,
                "prezzo_originale": promo.prezzo_originale,
                "prezzo_promo": promo.prezzo_promo,
                "sconto_percentuale": promo.sconto_percentuale,
                "data_inizio": str(promo.data_inizio),
                "data_fine": str(promo.data_fine) if promo.data_fine else "\u2014",
                "url_fonte": promo.url_fonte,
                "storage_gb": promo.storage_gb,
                "is_bundle": promo.is_bundle,
                "bundle_description": promo.bundle_description,
            })

        # Historical data for trend chart
        from sqlalchemy import func
        weekly_stats = (
            session.execute(
                select(
                    Promotion.settimana,
                    func.avg(Promotion.sconto_percentuale).label("avg_discount"),
                )
                .join(Product, Promotion.product_id == Product.id)
                .where(Product.is_google == True)  # noqa: E712
                .group_by(Promotion.settimana)
                .order_by(Promotion.settimana)
            )
            .all()
        )
        weekly_trend = [{"week": w[0], "avg_discount": round(float(w[1]), 1)} for w in weekly_stats]

    # ------------------------------------------------------------------
    # 2. Aggregate non-bundle promos: keep only lowest prezzo_promo
    #    per (product_id, retailer) — deduplicates colour variants.
    # ------------------------------------------------------------------
    best_by_product_retailer: dict[tuple, dict] = {}
    for p in promos_data:
        if p["is_bundle"]:
            continue
        key = (p["product_id"], _normalize_retailer(p["retailer"]))
        existing = best_by_product_retailer.get(key)
        if existing is None or p["prezzo_promo"] < existing["prezzo_promo"]:
            best_by_product_retailer[key] = p

    deduped = list(best_by_product_retailer.values())

    # ------------------------------------------------------------------
    # 3. Build grids
    # ------------------------------------------------------------------
    pixel10_grid = _build_price_grid(promos_data, products_map, "Pixel 10")
    pixel9_grid = _build_price_grid(promos_data, products_map, "Pixel 9")

    # ------------------------------------------------------------------
    # 4. Bundles
    # ------------------------------------------------------------------
    bundles = []
    for p in promos_data:
        if not p["is_bundle"]:
            continue
        bundles.append({
            "description": p["bundle_description"] or p["model"],
            "prezzo_promo": p["prezzo_promo"],
            "sconto_percentuale": p["sconto_percentuale"],
            "retailer": p["retailer"],
            "data_inizio": p["data_inizio"],
            "data_fine": p["data_fine"],
            "url_fonte": p["url_fonte"],
        })

    # ------------------------------------------------------------------
    # 5. Competitor tables
    # ------------------------------------------------------------------
    competitor_promos = [
        p for p in deduped
        if not p["is_google"] and p["category"] == "smartphone"
    ]
    competitor_flagship = [
        {
            "brand": p["brand"],
            "model": p["model"],
            "storage_gb": p["storage_gb"],
            "prezzo_promo": p["prezzo_promo"],
            "sconto_percentuale": p["sconto_percentuale"],
            "retailer": p["retailer"],
        }
        for p in competitor_promos
        if p["prezzo_promo"] > 800
    ]
    competitor_mid = [
        {
            "brand": p["brand"],
            "model": p["model"],
            "storage_gb": p["storage_gb"],
            "prezzo_promo": p["prezzo_promo"],
            "sconto_percentuale": p["sconto_percentuale"],
            "retailer": p["retailer"],
        }
        for p in competitor_promos
        if 400 <= p["prezzo_promo"] <= 800
    ]
    # Sort each list by discount descending
    competitor_flagship.sort(key=lambda x: x["sconto_percentuale"], reverse=True)
    competitor_mid.sort(key=lambda x: x["sconto_percentuale"], reverse=True)

    # ------------------------------------------------------------------
    # 6. Executive summary
    # ------------------------------------------------------------------
    google_deduped = [p for p in deduped if p["is_google"] and p["category"] == "smartphone"]

    # Pixel 10 price range for competitor alert threshold
    pixel10_prices = [
        p["prezzo_promo"]
        for p in google_deduped
        if _series_match(p.get("series", ""), "Pixel 10")
    ]
    p10_low = min(pixel10_prices) if pixel10_prices else 600
    p10_high = max(pixel10_prices) if pixel10_prices else 1200

    # competitor alerts: competitors with >20% discount in the Pixel 10 range
    competitor_alerts = []
    for cp in competitor_promos:
        if cp["sconto_percentuale"] > 20 and p10_low * 0.8 <= cp["prezzo_promo"] <= p10_high * 1.2:
            competitor_alerts.append(
                f"{cp['brand']} {cp['model']} a \u20ac{cp['prezzo_promo']:.0f} "
                f"(-{cp['sconto_percentuale']:.1f}%) su {cp['retailer']}"
            )

    # top3 Google promos by discount
    top3_sorted = sorted(google_deduped, key=lambda x: x["sconto_percentuale"], reverse=True)[:3]
    top3 = [
        {
            "model": t["model"],
            "storage_gb": t.get("storage_gb") or 0,
            "prezzo_promo": t["prezzo_promo"],
            "sconto_percentuale": t["sconto_percentuale"],
            "retailer": t["retailer"],
            "data_inizio": t["data_inizio"],
            "data_fine": t["data_fine"],
        }
        for t in top3_sorted
    ]

    executive_summary = {
        "total_pixel10_promos": len(pixel10_grid),
        "total_pixel9_promos": len(pixel9_grid),
        "top3": top3,
        "competitor_alerts": competitor_alerts,
    }

    # ------------------------------------------------------------------
    # 7. AI Insights (from analysis dict)
    # ------------------------------------------------------------------
    ai_insights = ""
    if analysis:
        # Try common keys the analysis dict might use
        ai_insights = (
            analysis.get("ai_insights")
            or analysis.get("insights")
            or analysis.get("pixel_smartphone", "")
        )
        # Truncate to ~250 words
        words = ai_insights.split()
        if len(words) > 250:
            ai_insights = " ".join(words[:250]) + " ..."

    # ------------------------------------------------------------------
    # 8. Render HTML template
    # ------------------------------------------------------------------
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "templates",
        "report_template.html",
    )
    with open(template_path, "r", encoding="utf-8") as f:
        template_str = f.read()

    template = Template(template_str)
    html_content = template.render(
        week=week,
        monday=monday.strftime("%d %B %Y"),
        sunday=sunday.strftime("%d %B %Y"),
        monday_short=monday.strftime("%d %b"),
        sunday_short=sunday.strftime("%d %b %Y"),
        generated_at=now.strftime("%d/%m/%Y %H:%M"),
        executive_summary=executive_summary,
        pixel10_grid=pixel10_grid,
        pixel9_grid=pixel9_grid,
        bundles=bundles,
        competitor_flagship=competitor_flagship,
        competitor_mid=competitor_mid,
        ai_insights=ai_insights,
    )

    # ------------------------------------------------------------------
    # 9. Generate PDF and save Report record
    # ------------------------------------------------------------------
    pdf_filename = f"{now.strftime('%Y-%m-%d')}_tds_weekly.pdf"
    pdf_path = os.path.join(settings.REPORTS_DIR, pdf_filename)

    HTML(string=html_content).write_pdf(pdf_path)
    logger.info("PDF report generated: %s", pdf_path)

    with sync_session_factory() as session:
        report = Report(
            title=f"TDS Weekly Report — {week}",
            type=ReportTypeEnum.weekly,
            settimana=week,
            pdf_path=pdf_path,
            generated_at=now,
            generated_by="scheduler",
        )
        session.add(report)
        session.commit()

    return pdf_path


def generate_custom_report(title: str, sections: list, week: str = None, generated_by: str = "tania_chat") -> str:
    """Generate a custom PDF report from chat. Returns PDF path."""
    if not week:
        now = datetime.now(timezone.utc)
        week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"

    monday, sunday = _get_week_dates(week)
    now = datetime.now(timezone.utc)

    os.makedirs(settings.REPORTS_DIR, exist_ok=True)

    with sync_session_factory() as session:
        promotions = (
            session.execute(
                select(Promotion)
                .where(Promotion.settimana == week)
                .order_by(Promotion.retailer)
            )
            .scalars()
            .all()
        )

        products = session.execute(select(Product)).scalars().all()
        products_map = {str(p.id): p for p in products}

        promos_data = []
        for promo in promotions:
            product = products_map.get(str(promo.product_id))
            if not product:
                continue
            promos_data.append({
                "brand": product.brand,
                "model": product.model,
                "category": product.category.value,
                "is_google": product.is_google,
                "retailer": promo.retailer,
                "prezzo_originale": promo.prezzo_originale,
                "prezzo_promo": promo.prezzo_promo,
                "sconto_percentuale": promo.sconto_percentuale,
            })

    # Simple custom report HTML
    sections_html = ""
    for section in sections:
        sections_html += f"<h2 style='color:#4285F4;'>{section.get('title', '')}</h2>"
        sections_html += f"<div>{section.get('content', '')}</div>"

    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
body {{ font-family: 'Roboto', sans-serif; margin: 40px; color: #333; }}
h1 {{ color: #4285F4; border-bottom: 3px solid #4285F4; padding-bottom: 10px; }}
h2 {{ color: #4285F4; margin-top: 30px; }}
.header {{ text-align: center; margin-bottom: 30px; }}
.brand {{ font-size: 14px; color: #666; }}
.footer {{ margin-top: 40px; padding-top: 20px; border-top: 2px solid #eee; font-size: 11px; color: #999; text-align: center; }}
</style></head><body>
<div class="header">
    <h1>TDS — Tech Deep Search</h1>
    <div class="brand">© React SRL | Report Custom — {now.strftime('%d/%m/%Y %H:%M')}</div>
    <div>Periodo: {monday.strftime('%d %B %Y')} — {sunday.strftime('%d %B %Y')}</div>
</div>
<h1>{title}</h1>
{sections_html}
<div class="footer">
TDS Tech Deep Search — Report generato automaticamente da React SRL | Dati rilevati su: Euronics, Unieuro, MediaWorld
</div>
</body></html>"""

    pdf_filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_tds_custom.pdf"
    pdf_path = os.path.join(settings.REPORTS_DIR, pdf_filename)

    HTML(string=html_content).write_pdf(pdf_path)
    logger.info("Custom PDF report generated: %s", pdf_path)

    with sync_session_factory() as session:
        report = Report(
            title=title,
            type=ReportTypeEnum.custom,
            settimana=week,
            pdf_path=pdf_path,
            generated_at=now,
            generated_by=generated_by,
        )
        session.add(report)
        session.commit()

    return pdf_path
