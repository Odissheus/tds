"""
TDS Tech Deep Search — FastAPI entrypoint.
Property of React SRL.
"""
import logging
import os
import sys

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.config import settings

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("tds")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("TDS Tech Deep Search starting up — React SRL")

    # Start scheduler
    from backend.scheduler import setup_scheduler
    setup_scheduler()

    # Ensure reports directory exists
    os.makedirs(settings.REPORTS_DIR, exist_ok=True)

    logger.info("TDS ready at %s", settings.BASE_URL)
    yield
    logger.info("TDS shutting down")


app = FastAPI(
    title="TDS — Tech Deep Search",
    description="Business Intelligence system by React SRL",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (logo, assets)
_assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "assets")
if os.path.isdir(_assets_dir):
    app.mount("/static", StaticFiles(directory=_assets_dir), name="static")

# API routers
from backend.api.products import router as products_router
from backend.api.promotions import router as promotions_router
from backend.api.chat import router as chat_router
from backend.api.reports import router as reports_router
from backend.api.scraping import router as scraping_router
from backend.api.system import router as system_router

app.include_router(products_router)
app.include_router(promotions_router)
app.include_router(chat_router)
app.include_router(reports_router)
app.include_router(scraping_router)
app.include_router(system_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "TDS Tech Deep Search", "owner": "React SRL"}


@app.post("/api/test-email")
async def test_email():
    """Trigger immediate analysis + PDF + email to hardcoded recipients."""
    from backend.agents.analysis_agent import run_weekly_analysis, get_current_week_str
    from backend.agents.report_agent import generate_weekly_report
    from backend.agents.email_agent import send_weekly_report, _send_email
    import base64

    week = get_current_week_str()
    logger.info("TEST EMAIL: running analysis for %s", week)

    analysis = run_weekly_analysis(week)
    logger.info("TEST EMAIL: generating PDF for %s", week)

    pdf_path = generate_weekly_report(week, analysis)

    highlights = analysis.get("top_highlights", [
        "Test report generato manualmente",
        "Sistema TDS operativo",
        "Dati aggiornati alla settimana corrente",
    ])

    # Send to hardcoded test recipients
    test_recipients = ["tania.di.santo@hotmail.com", "daniele.pili@hotmail.it"]
    from datetime import date, timedelta, datetime, timezone
    iso_year, iso_week = week.split("-W")
    monday = date.fromisocalendar(int(iso_year), int(iso_week), 1)
    sunday = monday + timedelta(days=6)
    now = datetime.now(timezone.utc)

    subject = f"📱 TDS Report Pixel | Week {iso_week} — {monday.strftime('%d %b')} › {sunday.strftime('%d %b %Y')}"

    highlights_html = ""
    for h in highlights[:3]:
        highlights_html += f"<li style='margin-bottom:8px;'>{h}</li>"

    body_html = f"""
    <div style="font-family: 'Roboto', Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #4285F4; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 24px;">TDS — Tech Deep Search</h1>
            <p style="color: rgba(255,255,255,0.8); margin: 5px 0 0;">© React SRL</p>
        </div>
        <div style="background: white; padding: 30px; border: 1px solid #e0e0e0;">
            <h2 style="color: #333; margin-top: 0;">📱 Report Settimanale Pixel</h2>
            <p style="color: #666;">Settimana {iso_week} — {monday.strftime('%d %b')} › {sunday.strftime('%d %b %Y')}</p>
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #4285F4; margin-top: 0;">🔝 Top 3 Highlights</h3>
                <ol style="color: #333; padding-left: 20px;">{highlights_html}</ol>
            </div>
            <p style="color: #666; font-size: 14px;">Il report completo è in allegato come PDF.</p>
        </div>
        <div style="background: #f5f5f5; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid #e0e0e0; border-top: none;">
            <p style="color: #999; font-size: 12px; margin: 0;">
                TDS Tech Deep Search — React SRL<br>
                Report generato automaticamente | Dati: Euronics, Unieuro, MediaWorld, Amazon
            </p>
        </div>
    </div>
    """

    pdf_filename = f"TDS_PixelReport_{now.strftime('%Y-%m-%d')}.pdf"

    # Use SendGrid directly with test recipients
    if not settings.SENDGRID_API_KEY:
        return {"status": "error", "message": "SENDGRID_API_KEY not configured", "pdf_path": pdf_path}

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, To, Attachment, FileContent, FileName, FileType, Disposition

    message = Mail(
        from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
        to_emails=[To(email) for email in test_recipients],
        subject=subject,
        html_content=body_html,
    )

    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        attachment = Attachment(
            FileContent(base64.b64encode(pdf_data).decode()),
            FileName(pdf_filename),
            FileType("application/pdf"),
            Disposition("attachment"),
        )
        message.attachment = attachment

    try:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        logger.info("TEST EMAIL sent to %s (status: %d)", test_recipients, response.status_code)

        if response.status_code in (200, 201, 202):
            return {
                "status": "success",
                "message": f"Email inviata a {', '.join(test_recipients)}",
                "pdf_path": pdf_path,
                "sendgrid_status": response.status_code,
                "week": week,
            }
        else:
            return {
                "status": "error",
                "message": f"SendGrid ha risposto con status {response.status_code}",
                "pdf_path": pdf_path,
                "sendgrid_status": response.status_code,
                "week": week,
            }
    except Exception as e:
        logger.error("TEST EMAIL failed: %s", str(e))
        return {"status": "error", "message": str(e), "pdf_path": pdf_path}


# Serve React frontend
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the React SPA dashboard."""
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    if os.path.exists(frontend_path):
        with open(frontend_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>TDS — Tech Deep Search | React SRL</h1><p>Frontend not found.</p>")
