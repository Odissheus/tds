"""
APScheduler — weekly schedule for scraping, analysis, report, email.
"""
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config import settings

logger = logging.getLogger("tds.scheduler")

scheduler = AsyncIOScheduler(timezone=settings.TZ)


def _trigger_scraping():
    """Trigger full scraping via Celery."""
    from backend.celery_app import run_scraping_task

    logger.info("Scheduler: triggering full scraping")
    run_scraping_task.delay()


def _trigger_analysis_and_report():
    """Trigger analysis + report generation via Celery."""
    from backend.celery_app import run_report_task

    logger.info("Scheduler: triggering analysis and report")
    run_report_task.delay()


def _trigger_email():
    """Trigger email sending via Celery."""
    from backend.celery_app import run_email_task

    logger.info("Scheduler: triggering email send")
    run_email_task.delay()


def setup_scheduler():
    """Configure all scheduled jobs."""

    # Wednesday 08:00 — full scraping
    scheduler.add_job(
        _trigger_scraping,
        CronTrigger(day_of_week="wed", hour=8, minute=0),
        id="scraping_wednesday",
        name="Scraping completo (mercoledì)",
        replace_existing=True,
    )

    # Thursday 08:00 — update scraping
    scheduler.add_job(
        _trigger_scraping,
        CronTrigger(day_of_week="thu", hour=8, minute=0),
        id="scraping_thursday",
        name="Scraping aggiornamento (giovedì)",
        replace_existing=True,
    )

    # Friday 07:30 — analysis + report
    scheduler.add_job(
        _trigger_analysis_and_report,
        CronTrigger(day_of_week="fri", hour=7, minute=30),
        id="analysis_report_friday",
        name="Analisi + Report PDF (venerdì)",
        replace_existing=True,
    )

    # Friday 08:00 — email
    scheduler.add_job(
        _trigger_email,
        CronTrigger(day_of_week="fri", hour=8, minute=0),
        id="email_friday",
        name="Invio email report (venerdì)",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler configured with %d jobs", len(scheduler.get_jobs()))

    for job in scheduler.get_jobs():
        logger.info("  Job: %s — next run: %s", job.name, job.next_run_time)
