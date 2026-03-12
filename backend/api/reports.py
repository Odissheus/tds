"""
Reports API — list, download, generate custom reports.
"""
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.models.report import Report

router = APIRouter(prefix="/api/reports", tags=["reports"])
logger = logging.getLogger("tds.api.reports")


class ReportOut(BaseModel):
    id: str
    title: str
    type: str
    settimana: str
    pdf_path: str
    generated_at: str
    generated_by: str

    class Config:
        from_attributes = True


class CustomReportRequest(BaseModel):
    title: str
    sections: list
    week: Optional[str] = None


@router.get("", response_model=List[ReportOut])
async def list_reports(
    session: AsyncSession = Depends(get_async_session),
):
    """List all generated reports."""
    result = await session.execute(select(Report).order_by(Report.generated_at.desc()))
    reports = result.scalars().all()

    return [
        ReportOut(
            id=str(r.id),
            title=r.title,
            type=r.type.value,
            settimana=r.settimana,
            pdf_path=r.pdf_path,
            generated_at=r.generated_at.isoformat(),
            generated_by=r.generated_by,
        )
        for r in reports
    ]


@router.get("/download/{report_id}")
async def download_report(
    report_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Download a report PDF."""
    import uuid

    result = await session.execute(select(Report).where(Report.id == uuid.UUID(report_id)))
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if not os.path.exists(report.pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    filename = os.path.basename(report.pdf_path)
    return FileResponse(
        path=report.pdf_path,
        filename=filename,
        media_type="application/pdf",
    )


@router.post("/generate")
async def generate_custom_report(data: CustomReportRequest):
    """Generate a custom PDF report."""
    from backend.agents.report_agent import generate_custom_report as gen_report

    try:
        pdf_path = gen_report(
            title=data.title,
            sections=data.sections,
            week=data.week,
            generated_by="tania_chat",
        )
        return {"status": "success", "pdf_path": pdf_path}
    except Exception as e:
        logger.error("Failed to generate custom report: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
