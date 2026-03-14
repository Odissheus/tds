"""
Report Agent — generates PDF reports using WeasyPrint + matplotlib.
"""
import base64
import io
import logging
import os
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

logger = logging.getLogger("tds.agent.report")


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


def generate_weekly_report(week: str, analysis: dict) -> str:
    """Generate the weekly PDF report. Returns the PDF file path."""
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
                "data_fine": str(promo.data_fine) if promo.data_fine else "—",
                "url_fonte": promo.url_fonte,
            })

        # Historical data for trend chart
        from sqlalchemy import func, distinct
        weekly_stats = (
            session.execute(
                select(
                    Promotion.settimana,
                    func.avg(Promotion.sconto_percentuale).label("avg_discount"),
                )
                .join(Product, Promotion.product_id == Product.id)
                .where(Product.is_google == True)
                .group_by(Promotion.settimana)
                .order_by(Promotion.settimana)
            )
            .all()
        )
        weekly_trend = [{"week": w[0], "avg_discount": round(float(w[1]), 1)} for w in weekly_stats]

    # Generate charts
    price_chart_b64 = _generate_price_chart(promos_data)
    trend_chart_b64 = _generate_discount_trend_chart(weekly_trend)

    # Categorize promos
    google_smartphone = [p for p in promos_data if p["is_google"] and p["category"] == "smartphone"]
    google_hearable_wearable = [p for p in promos_data if p["is_google"] and p["category"] in ("hearable", "wearable", "accessory")]
    google_bundles = [p for p in promos_data if p["is_google"] and p["category"] == "bundle"]
    comp_smartphone = [p for p in promos_data if not p["is_google"] and p["category"] == "smartphone"]
    comp_hearable_wearable = [p for p in promos_data if not p["is_google"] and p["category"] in ("hearable", "wearable")]
    eol_promos = [p for p in promos_data if p["tier"] == 2]

    # Load and render template
    template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates", "report_template.html")
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
        google_smartphone=google_smartphone,
        google_hearable_wearable=google_hearable_wearable,
        google_bundles=google_bundles,
        comp_smartphone=comp_smartphone,
        comp_hearable_wearable=comp_hearable_wearable,
        eol_promos=eol_promos,
        analysis=analysis,
        price_chart_b64=price_chart_b64,
        trend_chart_b64=trend_chart_b64,
    )

    pdf_filename = f"{now.strftime('%Y-%m-%d')}_tds_weekly.pdf"
    pdf_path = os.path.join(settings.REPORTS_DIR, pdf_filename)

    HTML(string=html_content).write_pdf(pdf_path)
    logger.info("PDF report generated: %s", pdf_path)

    # Save report record
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
