#!/bin/bash
#
# Smoke Test Pre-Demo - BankAdvisor Analytics
#
# Quick validation script to run before the demo.
#
# Usage:
#   ./scripts/smoke_demo_bank_analytics.sh [HOST] [PORT]
#
# Examples:
#   ./scripts/smoke_demo_bank_analytics.sh                    # Default: localhost:8001
#   ./scripts/smoke_demo_bank_analytics.sh demo.server.com    # Custom host
#   ./scripts/smoke_demo_bank_analytics.sh localhost 8080     # Custom port
#
# Exit codes:
#   0 = All checks passed (🟢 safe to demo)
#   1 = Some checks failed (🔴 DO NOT demo)
#

set -e  # Exit on error

# Default values
HOST="${1:-localhost}"
PORT="${2:-8001}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "🚦 SMOKE TEST PRE-DEMO - BankAdvisor Analytics"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "Target: http://${HOST}:${PORT}"
echo "Time:   $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

# Check if Python script exists
if [ ! -f "scripts/smoke_demo_bank_analytics.py" ]; then
    echo -e "${RED}❌ Error: smoke_demo_bank_analytics.py not found${NC}"
    exit 1
fi

# Check if requests library is installed
if ! python -c "import requests" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Warning: 'requests' library not installed${NC}"
    echo "Installing requests..."
    pip install requests -q
fi

# Run Python smoke test
python scripts/smoke_demo_bank_analytics.py \
    --host "$HOST" \
    --port "$PORT" \
    --save-json "docs/smoke_test_results_$(date +%Y%m%d_%H%M%S).json"

EXIT_CODE=$?

echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}🟢 ALL CHECKS PASSED - SAFE TO DEMO${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review the demo script: docs/DEMO_SCRIPT_2025-12-03.md"
    echo "  2. Have the queries ready: grep '\"' docs/DEMO_SCRIPT_2025-12-03.md | head -10"
    echo "  3. Start docker logs in another terminal: docker logs -f bank-advisor-mcp"
    echo ""
else
    echo -e "${RED}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}🔴 SOME CHECKS FAILED - DO NOT DEMO UNTIL FIXED${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Check server logs: docker logs bank-advisor-mcp | tail -50"
    echo "  2. Verify database has data: docker exec bank-advisor-mcp psql -U postgres -d invex_bankadvisor -c 'SELECT COUNT(*) FROM monthly_kpis;'"
    echo "  3. Check ETL status: curl http://${HOST}:${PORT}/health | jq .etl"
    echo "  4. Re-run ETL if needed: docker exec bank-advisor-mcp python -m bankadvisor.etl_runner"
    echo ""
fi

exit $EXIT_CODE
