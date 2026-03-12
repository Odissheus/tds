"""
Scraping API — manual triggers.
"""
import logging

from fastapi import APIRouter, HTTPException

from backend.celery_app import run_scraping_task, run_single_scraping_task

router = APIRouter(prefix="/api/scrape", tags=["scraping"])
logger = logging.getLogger("tds.api.scraping")


@router.post("/{product_id}")
async def scrape_single_product(product_id: str):
    """Trigger scraping for a single product."""
    task = run_single_scraping_task.delay(product_id)
    return {
        "status": "queued",
        "task_id": str(task.id),
        "product_id": product_id,
        "message": f"Scraping avviato per prodotto {product_id}",
    }


@router.post("/full")
async def scrape_all():
    """Trigger full scraping for all products."""
    task = run_scraping_task.delay()
    return {
        "status": "queued",
        "task_id": str(task.id),
        "message": "Scraping completo avviato per tutti i prodotti",
    }


@router.get("/status/{task_id}")
async def scrape_status(task_id: str):
    """Check scraping task status."""
    from backend.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }
