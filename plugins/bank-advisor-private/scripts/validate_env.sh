#!/bin/bash
# validate_env.sh - Environment readiness check for NL2SQL validation
# Run before starting real-world testing

set -e

echo "🔍 NL2SQL Environment Validation"
echo "=================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASS=0
FAIL=0
WARN=0

check_pass() {
    echo -e "${GREEN}✅ $1${NC}"
    ((PASS++))
}

check_fail() {
    echo -e "${RED}❌ $1${NC}"
    ((FAIL++))
}

check_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    ((WARN++))
}

echo "1. Checking Qdrant..."
if docker ps | grep -q qdrant; then
    check_pass "Qdrant is running"

    # Check collections
    COLLECTIONS=$(curl -s http://localhost:6333/collections | jq -r '.result.collections[].name' 2>/dev/null || echo "")
    if echo "$COLLECTIONS" | grep -q "bankadvisor_schema"; then
        check_pass "RAG collections exist (already seeded)"
    else
        check_warn "RAG collections not found (need to run seed script)"
    fi
else
    check_fail "Qdrant is NOT running (docker-compose up qdrant)"
fi
echo ""

echo "2. Checking PostgreSQL..."
if docker ps | grep -q postgres; then
    check_pass "PostgreSQL is running"

    # Check data
    ROW_COUNT=$(docker exec postgres psql -U postgres -d octavios_dev -tAc \
        "SELECT COUNT(*) FROM monthly_kpis WHERE fecha >= '2024-01-01';" 2>/dev/null || echo "0")

    if [ "$ROW_COUNT" -gt 100 ]; then
        check_pass "Database has recent data ($ROW_COUNT rows for 2024)"
    elif [ "$ROW_COUNT" -gt 0 ]; then
        check_warn "Database has limited data ($ROW_COUNT rows for 2024)"
    else
        check_fail "Database is empty or not accessible"
    fi
else
    check_fail "PostgreSQL is NOT running (docker-compose up postgres)"
fi
echo ""

echo "3. Checking SAPTIVA API Key..."
API_KEY_VAR="SAPTIVA_API_KEY"
if [ -f "../../apps/backend/.env" ]; then
    if grep -q "${API_KEY_VAR}=sk-" ../../apps/backend/.env 2>/dev/null; then
        check_pass "SAPTIVA API key is configured"
    elif grep -q "${API_KEY_VAR}=" ../../apps/backend/.env 2>/dev/null; then
        check_warn "SAPTIVA API key exists but may not be valid"
    else
        check_fail "SAPTIVA API key is NOT configured"
    fi
else
    check_warn "Backend .env file not found"
fi
echo ""

echo "4. Checking Python Environment..."
if [ -d ".venv" ]; then
    check_pass "Virtual environment exists (.venv)"

    source .venv/bin/activate

    # Check key dependencies
    if python -c "import qdrant_client" 2>/dev/null; then
        check_warn "qdrant_client installed locally (should use backend's)"
    fi

    if python -c "import pytest" 2>/dev/null; then
        check_pass "pytest is installed"
    else
        check_warn "pytest not installed (pip install pytest)"
    fi

    deactivate
else
    check_fail "Virtual environment NOT found (python -m venv .venv)"
fi
echo ""

echo "5. Checking Backend Services..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    check_pass "Backend API is running (port 8000)"
else
    check_warn "Backend API is NOT running (needed for E2E tests)"
fi

if curl -s http://localhost:3000 > /dev/null 2>&1; then
    check_pass "Frontend is running (port 3000)"
else
    check_warn "Frontend is NOT running (needed for visual validation)"
fi
echo ""

echo "6. Checking Test Files..."
EXPECTED_TESTS=(
    "src/bankadvisor/tests/unit/test_sql_validator.py"
    "src/bankadvisor/tests/unit/test_sql_generation_service.py"
    "src/bankadvisor/tests/unit/test_nl2sql_context_service.py"
    "src/bankadvisor/tests/integration/test_nl2sql_e2e.py"
)

for test_file in "${EXPECTED_TESTS[@]}"; do
    if [ -f "$test_file" ]; then
        check_pass "Found $test_file"
    else
        check_fail "Missing $test_file"
    fi
done
echo ""

echo "7. Checking Documentation..."
EXPECTED_DOCS=(
    "docs/NL2SQL_PHASE4_COMPLETE.md"
    "docs/NL2SQL_VALIDATION_ROADMAP.md"
    "docs/NEXT_SESSION_CHECKLIST.md"
)

for doc_file in "${EXPECTED_DOCS[@]}"; do
    if [ -f "$doc_file" ]; then
        check_pass "Found $doc_file"
    else
        check_fail "Missing $doc_file"
    fi
done
echo ""

# Summary
echo "=================================="
echo "Summary:"
echo -e "${GREEN}✅ Passed: $PASS${NC}"
echo -e "${YELLOW}⚠️  Warnings: $WARN${NC}"
echo -e "${RED}❌ Failed: $FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    if [ $WARN -eq 0 ]; then
        echo -e "${GREEN}🎉 Environment is ready for validation testing!${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠️  Environment is mostly ready, but has some warnings.${NC}"
        echo "Review warnings above before proceeding."
        exit 0
    fi
else
    echo -e "${RED}❌ Environment is NOT ready for validation testing.${NC}"
    echo "Fix the failed checks above before proceeding."
    exit 1
fi
