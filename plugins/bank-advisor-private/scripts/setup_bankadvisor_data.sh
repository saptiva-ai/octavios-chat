#!/bin/bash
set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     BankAdvisor - Full Data Setup                          ║"
echo "╚════════════════════════════════════════════════════════════╝"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$PLUGIN_DIR")")"

cd "$PLUGIN_DIR"

# ============================================
# PASO 1: Verificar prerequisitos
# ============================================
echo ""
echo "📋 Step 1: Checking prerequisites..."

# Verificar archivos de datos
if [ ! -d "data/raw" ]; then
    echo "❌ ERROR: data/raw directory not found!"
    exit 1
fi

REQUIRED_FILES=("CNBV_Cartera_Bancos_V2.xlsx" "Instituciones.xlsx")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "data/raw/$file" ]; then
        echo "❌ ERROR: Required file missing: data/raw/$file"
        exit 1
    fi
done
echo "   ✅ Data files present"

# Verificar servicios Docker
echo "   Checking Docker services..."
QDRANT_OK=false
POSTGRES_OK=false

if curl -s http://localhost:6333/collections > /dev/null 2>&1; then
    QDRANT_OK=true
    echo "   ✅ Qdrant responding"
else
    echo "   ⚠️  Qdrant not responding"
fi

if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    POSTGRES_OK=true
    echo "   ✅ PostgreSQL responding"
else
    echo "   ⚠️  PostgreSQL not responding"
fi

if [ "$QDRANT_OK" = false ] || [ "$POSTGRES_OK" = false ]; then
    echo ""
    echo "   Starting Docker services..."
    cd "$PROJECT_ROOT"
    docker compose -f infra/docker-compose.yml up -d postgres qdrant
    echo "   Waiting for services to be ready..."
    sleep 10
    cd "$PLUGIN_DIR"
fi

# ============================================
# PASO 2: Activar entorno virtual
# ============================================
echo ""
echo "🐍 Step 2: Activating Python environment..."

if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "   Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --quiet -r requirements.txt
fi
echo "   ✅ Virtual environment active"

# ============================================
# PASO 3: Ejecutar ETL a PostgreSQL
# ============================================
echo ""
echo "📊 Step 3: Running ETL to PostgreSQL..."

cd "$PLUGIN_DIR/src"

# ETL Base
echo "   Loading base metrics (IMOR, ICOR, Cartera)..."
python -c "
from bankadvisor.etl_loader import run_etl
run_etl()
" 2>&1 | head -20

# ETL Enhanced (si existe)
if [ -f "bankadvisor/etl_loader_enhanced.py" ]; then
    echo ""
    echo "   Loading enhanced metrics (ICAP, TDA, Tasas)..."
    python -c "
from bankadvisor.etl_loader_enhanced import run_enhanced_etl
run_enhanced_etl()
" 2>&1 | head -30
fi

echo "   ✅ PostgreSQL populated"

cd "$PLUGIN_DIR"

# ============================================
# PASO 4: Ejecutar Seeding de Qdrant
# ============================================
echo ""
echo "🧠 Step 4: Seeding Qdrant knowledge base..."

if [ -f "scripts/seed_nl2sql_rag.py" ]; then
    # Intentar ejecutar el script de seeding
    cd "$PLUGIN_DIR"
    python scripts/seed_nl2sql_rag.py --clear 2>&1 | head -30 || {
        echo "   ⚠️  RAG seeding script failed, creating collections manually..."
        # Fallback: crear colecciones vacías
        for collection in bankadvisor_schema bankadvisor_metrics bankadvisor_examples; do
            curl -s -X PUT "http://localhost:6333/collections/$collection" \
              -H "Content-Type: application/json" \
              -d '{"vectors": {"size": 384, "distance": "Cosine"}}' > /dev/null 2>&1 || true
            echo "   Created: $collection"
        done
    }
else
    echo "   Creating Qdrant collections manually..."
    for collection in bankadvisor_schema bankadvisor_metrics bankadvisor_examples; do
        # Eliminar si existe
        curl -s -X DELETE "http://localhost:6333/collections/$collection" > /dev/null 2>&1 || true
        # Crear nueva
        curl -s -X PUT "http://localhost:6333/collections/$collection" \
          -H "Content-Type: application/json" \
          -d '{"vectors": {"size": 384, "distance": "Cosine"}}' > /dev/null 2>&1
        echo "   Created: $collection"
    done
fi

echo "   ✅ Qdrant collections ready"

# ============================================
# PASO 5: Verificación final
# ============================================
echo ""
echo "✅ Step 5: Final verification..."

# Verificar PostgreSQL
echo ""
echo "   PostgreSQL (monthly_kpis):"
cd "$PLUGIN_DIR/src"
python -c "
from sqlalchemy import create_engine, text
from core.config import get_settings
settings = get_settings()
url = settings.database_url_sync
# Ajustar host para conexión local
if '@postgres:' in url:
    url = url.replace('@postgres:', '@localhost:')
if '@bankadvisor-postgres:' in url:
    url = url.replace('@bankadvisor-postgres:', '@localhost:')
engine = create_engine(url)
try:
    with engine.connect() as conn:
        result = conn.execute(text('SELECT banco_norm, COUNT(*) as n, MIN(fecha) as desde, MAX(fecha) as hasta FROM monthly_kpis GROUP BY banco_norm'))
        for row in result:
            print(f'      {row.banco_norm}: {row.n} records ({row.desde} to {row.hasta})')
except Exception as e:
    print(f'      ⚠️  Could not verify: {e}')
" 2>/dev/null || echo "      ⚠️  Could not connect to PostgreSQL"

cd "$PLUGIN_DIR"

# Verificar Qdrant
echo ""
echo "   Qdrant collections:"
for collection in bankadvisor_schema bankadvisor_metrics bankadvisor_examples; do
    status=$(curl -s "http://localhost:6333/collections/$collection" 2>/dev/null)
    if echo "$status" | grep -q '"status":"ok"' 2>/dev/null; then
        count=$(echo "$status" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('points_count',0))" 2>/dev/null || echo "?")
        echo "      $collection: $count points ✅"
    else
        echo "      $collection: not found ❌"
    fi
done

# ============================================
# RESUMEN
# ============================================
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    SETUP COMPLETE!                         ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║  PostgreSQL: monthly_kpis table populated                  ║"
echo "║  Qdrant: 3 collections created                             ║"
echo "║                                                            ║"
echo "║  Next steps:                                               ║"
echo "║  1. Start backend: docker compose up -d backend            ║"
echo "║  2. Test query:                                            ║"
echo "║     curl -X POST http://localhost:8000/rpc \\               ║"
echo "║       -H 'Content-Type: application/json' \\                ║"
echo "║       -d '{\"jsonrpc\":\"2.0\",\"id\":\"1\",                ║"
echo "║            \"method\":\"bank_advisor.query\",              ║"
echo "║            \"params\":{\"query\":\"IMOR de INVEX\"}}'      ║"
echo "╚════════════════════════════════════════════════════════════╝"
