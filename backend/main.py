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


# Serve React frontend
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the React SPA dashboard."""
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    if os.path.exists(frontend_path):
        with open(frontend_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>TDS — Tech Deep Search | React SRL</h1><p>Frontend not found.</p>")
