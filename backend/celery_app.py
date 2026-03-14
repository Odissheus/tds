"""
Celery configuration and tasks.
"""
import asyncio
import logging

from celery import Celery

from backend.config import settings

logger = logging.getLogger("tds.celery")

celery_app = Celery(
    "tds",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.TZ,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="tds.run_scraping")
def run_scraping_task():
    """Run full scraping for all products."""
    from backend.agents.scraper_agent import run_full_scraping

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_full_scraping())
        return result
    finally:
        loop.close()


@celery_app.task(name="tds.run_single_scraping")
def run_single_scraping_task(product_id: str):
    """Run scraping for a single product."""
    from backend.agents.scraper_agent import run_scraping_for_product

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_scraping_for_product(product_id))
        return result
    finally:
        loop.close()


@celery_app.task(name="tds.run_analysis")
def run_analysis_task(week: str = None):
    """Run weekly analysis."""
    from backend.agents.analysis_agent import run_weekly_analysis

    return run_weekly_analysis(week)


@celery_app.task(name="tds.run_report")
def run_report_task(week: str = None):
    """Generate weekly report."""
    from backend.agents.analysis_agent import run_weekly_analysis, get_current_week_str, FALLBACK_ANALYSIS
    from backend.agents.report_agent import generate_weekly_report

    if not week:
        week = get_current_week_str()

    try:
        analysis = run_weekly_analysis(week)
    except Exception as e:
        logger.error("Analysis failed (%s), generating report with fallback data", e)
        analysis = FALLBACK_ANALYSIS

    pdf_path = generate_weekly_report(week, analysis)
    return {"week": week, "pdf_path": pdf_path, "analysis_keys": list(analysis.keys())}


@celery_app.task(name="tds.run_email")
def run_email_task(week: str = None):
    """Send weekly report email."""
    from backend.agents.analysis_agent import get_current_week_str
    from backend.agents.email_agent import send_weekly_report
    from backend.database import sync_session_factory
    from backend.models.report import Report
    from sqlalchemy import select

    if not week:
        week = get_current_week_str()

    with sync_session_factory() as session:
        report = session.execute(
            select(Report).where(Report.settimana == week).order_by(Report.generated_at.desc())
        ).scalar_one_or_none()

    if not report:
        logger.error("No report found for week %s", week)
        return {"error": f"No report found for week {week}"}

    highlights = ["Report settimanale generato", "Dati aggiornati", "Consulta la dashboard per dettagli"]

    success = send_weekly_report(report.pdf_path, week, highlights)
    return {"success": success, "week": week}
