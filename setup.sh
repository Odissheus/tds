#!/bin/bash
set -euo pipefail

#############################################
# TDS — Tech Deep Search | Setup VPS Script
# Property of React SRL
# Target: Ubuntu 22.04 (Hetzner VPS)
#############################################

echo "======================================"
echo " TDS — Tech Deep Search | React SRL"
echo " Setup VPS Ubuntu 22.04"
echo "======================================"

# Update system
echo "[1/7] Aggiornamento sistema..."
apt-get update -y && apt-get upgrade -y

# Install Docker
echo "[2/7] Installazione Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo "Docker già installato."
fi

# Install Docker Compose plugin
echo "[3/7] Verifica Docker Compose plugin..."
if ! docker compose version &> /dev/null; then
    apt-get install -y docker-compose-plugin
else
    echo "Docker Compose plugin già disponibile."
fi

# Clone repo (or use current directory)
echo "[4/7] Preparazione progetto..."
PROJECT_DIR="/opt/tds"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Creazione directory progetto in $PROJECT_DIR"
    mkdir -p "$PROJECT_DIR"
    cp -r "$(dirname "$0")"/* "$PROJECT_DIR"/
fi
cd "$PROJECT_DIR"

# Setup .env
echo "[5/7] Configurazione .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANTE: Modifica il file .env con le tue chiavi API:"
    echo "   nano $PROJECT_DIR/.env"
    echo ""
    echo "   Variabili da configurare:"
    echo "   - ANTHROPIC_API_KEY"
    echo "   - SENDGRID_API_KEY"
    echo "   - EMAIL_TO"
    echo "   - SECRET_KEY (genera con: openssl rand -hex 32)"
    echo "   - BASE_URL"
    echo ""
else
    echo ".env già presente."
fi

# Start services
echo "[6/7] Avvio servizi Docker..."
docker compose up -d --build

# Wait for services
echo "Attesa avvio servizi..."
sleep 15

# Run migrations and seed
echo "[7/7] Esecuzione migrations e seed..."
docker compose exec -T app alembic upgrade head
docker compose exec -T app python seed.py

# Done
echo ""
echo "======================================"
echo " ✅ TDS — Tech Deep Search PRONTO!"
echo "======================================"
echo ""
echo " Dashboard:  http://$(hostname -I | awk '{print $1}'):8000"
echo " API Health: http://$(hostname -I | awk '{print $1}'):8000/api/health"
echo ""
echo " Servizi attivi:"
docker compose ps
echo ""
echo " © React SRL — TDS Tech Deep Search"
echo "======================================"
