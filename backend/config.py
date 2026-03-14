import os
from typing import List


class Settings:
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    EMAIL_TO: List[str] = [
        e.strip() for e in os.getenv("EMAIL_TO", "tania@example.com").split(",") if e.strip()
    ]
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://tds:password@postgres:5432/tds")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")
    TZ: str = os.getenv("TZ", "Europe/Rome")
    REPORTS_DIR: str = "/data/reports"
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    EMAIL_FROM: str = os.getenv("SENDGRID_FROM_EMAIL", "tds@reactsrl.com")
    EMAIL_FROM_NAME: str = "TDS Tech Deep Search"


settings = Settings()
