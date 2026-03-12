# TDS — Tech Deep Search

**Business Intelligence system for monitoring Italian consumer electronics retail promotions.**
Property of **React SRL**.

## Overview

TDS monitors weekly promotions on **Euronics**, **Unieuro**, and **MediaWorld** for Google Pixel and competitor products (Samsung, Apple, Honor, OPPO, Xiaomi, Redmi, POCO, Motorola). It generates weekly PDF reports with AI-powered analysis and sends them via email.

## Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn
- **Scraping**: Playwright (headless Chromium)
- **Database**: PostgreSQL 16 (SQLAlchemy + Alembic)
- **Job Queue**: Celery + Redis
- **Scheduler**: APScheduler
- **PDF**: WeasyPrint + matplotlib
- **Email**: SendGrid
- **AI**: Claude API (claude-sonnet-4-20250514)
- **Frontend**: React 18 + Tailwind CSS (single-file JSX)

## Prerequisites

- Docker + Docker Compose
- A VPS with at least 2GB RAM (Hetzner recommended)
- Anthropic API key
- SendGrid API key

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `SENDGRID_API_KEY` | SendGrid API key |
| `EMAIL_TO` | Comma-separated recipient emails |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `BASE_URL` | Public URL of the dashboard |
| `SECRET_KEY` | Random secret (generate with `openssl rand -hex 32`) |
| `TZ` | Timezone (default: `Europe/Rome`) |

## Quick Start (VPS)

```bash
# On a fresh Ubuntu 22.04 VPS:
chmod +x setup.sh
sudo ./setup.sh
```

This will install Docker, build containers, run migrations, and seed the database.

## Manual Setup

```bash
# 1. Start services
docker compose up -d --build

# 2. Run migrations
docker compose exec app alembic upgrade head

# 3. Seed product catalog
docker compose exec app python seed.py
```

## Deploy with Coolify

1. Create a new project in Coolify
2. Connect your Git repo
3. Set build pack to "Docker Compose"
4. Add environment variables in Coolify settings
5. Deploy

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard SPA |
| `/api/health` | GET | Health check |
| `/api/products` | GET/POST | Product CRUD |
| `/api/products/{id}` | PATCH | Update product |
| `/api/products/suggest` | POST | AI product suggestion |
| `/api/products/import-batch` | POST | AI batch import |
| `/api/promotions` | GET | List promotions (filters: week, brand, category, retailer) |
| `/api/chat/stream` | POST | Streaming chat with Claude |
| `/api/reports` | GET | List reports |
| `/api/reports/download/{id}` | GET | Download PDF |
| `/api/reports/generate` | POST | Generate custom report |
| `/api/scrape/{product_id}` | POST | Trigger single product scrape |
| `/api/scrape/full` | POST | Trigger full scrape |
| `/api/system/status` | GET | System status |
| `/api/system/logs` | GET | Scrape logs |

## Scheduled Jobs

| Day | Time | Action |
|---|---|---|
| Wednesday | 08:00 | Full scraping (all products × all retailers) |
| Thursday | 08:00 | Update scraping (check promo changes) |
| Friday | 07:30 | AI analysis + PDF report generation |
| Friday | 08:00 | Email report to recipients |

## Architecture

```
[Scheduler] → [Celery Queue] → [Workers]
                                   ↓
[Playwright Scrapers] → [PostgreSQL] ← [FastAPI REST API]
                                           ↓
[Claude AI Analysis] → [WeasyPrint PDF] → [SendGrid Email]
                                           ↓
                                    [React Dashboard]
```

---

**TDS — Tech Deep Search | © React SRL**
