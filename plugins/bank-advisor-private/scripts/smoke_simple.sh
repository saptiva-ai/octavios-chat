#!/bin/bash
#
# Smoke Test SIMPLE - Valida que el servidor responda
#
# Este script hace queries básicas y verifica que:
# 1. El servidor esté UP
# 2. El healthcheck funcione
# 3. El endpoint /rpc responda (aunque sea con clarificación)
# 4. No haya errores 500
#

set -e

HOST="${1:-localhost}"
PORT="${2:-8002}"
BASE_URL="http://$HOST:$PORT"

echo "================================================================================"
echo "🚦 SMOKE TEST SIMPLE - BankAdvisor"
echo "================================================================================"
echo "Target: $BASE_URL"
echo ""

# Test 1: Health Check
echo "[1/3] Testing /health endpoint..."
HEALTH_STATUS=$(curl -s "$BASE_URL/health" | jq -r '.status' 2>/dev/null || echo "FAIL")

if [ "$HEALTH_STATUS" = "healthy" ]; then
    echo "    ✅ Health check PASSED"
else
    echo "    ❌ Health check FAILED (status: $HEALTH_STATUS)"
    exit 1
fi

# Test 2: RPC endpoint responds
echo "[2/3] Testing /rpc endpoint..."
RPC_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/rpc" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "bank_analytics", "arguments": {"metric_or_query": "IMOR", "mode": "dashboard"}}}')

HTTP_CODE=$(echo "$RPC_RESPONSE" | tail -1)
RESPONSE_BODY=$(echo "$RPC_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "    ✅ RPC endpoint responds HTTP 200"

    # Check if response has valid JSON-RPC structure
    HAS_RESULT=$(echo "$RESPONSE_BODY" | jq -r 'has("result")' 2>/dev/null || echo "false")
    if [ "$HAS_RESULT" = "true" ]; then
        echo "    ✅ RPC response has valid structure"
    else
        echo "    ⚠️  RPC response missing 'result' field"
    fi
else
    echo "    ❌ RPC endpoint FAILED (HTTP $HTTP_CODE)"
    echo "    Response: $RESPONSE_BODY"
    exit 1
fi

# Test 3: Database has data
echo "[3/3] Checking database..."
DB_COUNT=$(docker exec octavios-chat-bajaware_invex-postgres psql -U octavios -d bankadvisor -t -c "SELECT COUNT(*) FROM monthly_kpis;" 2>/dev/null | tr -d ' ' || echo "0")

if [ "$DB_COUNT" -gt "0" ]; then
    echo "    ✅ Database has $DB_COUNT records"
else
    echo "    ❌ Database is empty or not accessible"
    exit 1
fi

echo ""
echo "================================================================================"
echo "🟢 BASIC SMOKE TEST PASSED"
echo "================================================================================"
echo ""
echo "Server is responding correctly. Ready for detailed testing."
echo ""
