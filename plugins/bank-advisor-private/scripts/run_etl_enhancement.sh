#!/bin/bash
#
# ETL Enhancement Runner Script
# Loads ICAP, TDA, TASA_MN, and TASA_ME data into monthly_kpis table
#
# Usage:
#   ./scripts/run_etl_enhancement.sh           # Run in Docker container
#   ./scripts/run_etl_enhancement.sh --local   # Run locally (needs virtualenv)
#

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================="
echo "BankAdvisor ETL Enhancement"
echo "========================================="
echo ""

# Check if running with --local flag
if [ "$1" == "--local" ]; then
    echo "🏠 Running locally..."
    cd "$PROJECT_ROOT"

    # Check if virtualenv exists
    if [ ! -d "venv" ]; then
        echo "❌ Virtual environment not found. Please create it first:"
        echo "   python -m venv venv"
        echo "   source venv/bin/activate"
        echo "   pip install -r requirements.txt"
        exit 1
    fi

    # Activate virtualenv
    source venv/bin/activate

    # Set PYTHONPATH
    export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"

    # Run ETL
    python -m bankadvisor.etl_loader_enhanced

else
    echo "🐳 Running in Docker container..."

    # Check if container is running
    CONTAINER_NAME="octavios-chat-bajaware_invex-bank-advisor"

    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "❌ Container '$CONTAINER_NAME' is not running"
        echo "   Start it with: docker-compose up -d bank-advisor"
        exit 1
    fi

    # Run ETL in container
    docker exec -i "$CONTAINER_NAME" python -m bankadvisor.etl_loader_enhanced

fi

echo ""
echo "✅ ETL Enhancement completed!"
echo ""
echo "Verify results with:"
echo "  docker exec -i octavios-chat-bajaware_invex-postgres psql -U octavios -d bankadvisor -c \"SELECT COUNT(*), COUNT(icap_total), COUNT(tda_cartera_total), COUNT(tasa_mn), COUNT(tasa_me) FROM monthly_kpis;\""
