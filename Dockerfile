# ---- Build stage ----
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.11-slim-bookworm

WORKDIR /app

# Update package lists first (separate layer for better caching)
RUN apt-get update --fix-missing

# WeasyPrint and Playwright system dependencies
RUN apt-get install -y --no-install-recommends --fix-missing \
    libpq5 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libffi-dev \
    libglib2.0-0 \
    fonts-liberation \
    fonts-dejavu-core \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libasound2-dev \
    libatomic1 \
    libcups2 \
    libdbus-1-3 \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages
COPY --from=builder /install /usr/local

# Install Playwright and Chromium browser (after all system deps)
RUN playwright install chromium --with-deps

# Copy application code
COPY . .

# Create reports directory
RUN mkdir -p /data/reports

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV TZ=Europe/Rome

EXPOSE 8000

# Default command: run FastAPI with Uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--access-log"]
