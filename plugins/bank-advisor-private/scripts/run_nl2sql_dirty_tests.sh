#!/bin/bash
# NL2SQL Dirty Data Test Runner (BA-QA-001)
#
# Runs hostile query tests against the NL2SQL pipeline.
# Supports both local and Docker execution modes.
#
# Usage:
#   ./scripts/run_nl2sql_dirty_tests.sh [options]
#
# Options:
#   --local       Run against local dev server (default: localhost:8000)
#   --docker      Run against Docker compose services
#   --url URL     Custom RPC endpoint URL
#   --null-only   Run only BA-NULL-001 tests
#   --injection   Run only injection prevention tests
#   --verbose     Show detailed output
#   --help        Show this help message

set -e

# Default configuration
RPC_URL="${BANKADVISOR_RPC_URL:-http://localhost:8000/rpc}"
PYTEST_ARGS="-m nl2sql_dirty"
VERBOSE=""

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${GREEN}"
    echo "=================================================="
    echo "  NL2SQL Dirty Data / Hostile Query Test Suite"
    echo "  (BA-QA-001)"
    echo "=================================================="
    echo -e "${NC}"
}

print_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --local       Run against local dev server (default)"
    echo "  --docker      Run against Docker compose services"
    echo "  --url URL     Custom RPC endpoint URL"
    echo "  --null-only   Run only BA-NULL-001 NULL handling tests"
    echo "  --injection   Run only SQL injection prevention tests"
    echo "  --verbose     Show detailed test output"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --local --verbose"
    echo "  $0 --docker --null-only"
    echo "  $0 --url http://api.example.com/rpc"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            RPC_URL="http://localhost:8000/rpc"
            shift
            ;;
        --docker)
            RPC_URL="http://localhost:8000/rpc"
            echo -e "${YELLOW}Note: Ensure Docker services are running with 'docker compose up -d'${NC}"
            shift
            ;;
        --url)
            RPC_URL="$2"
            shift 2
            ;;
        --null-only)
            PYTEST_ARGS="-m 'nl2sql_dirty and ba_null_001'"
            echo -e "${YELLOW}Running only BA-NULL-001 tests${NC}"
            shift
            ;;
        --injection)
            PYTEST_ARGS="-m nl2sql_dirty -k injection"
            echo -e "${YELLOW}Running only injection prevention tests${NC}"
            shift
            ;;
        --verbose)
            VERBOSE="-v --tb=short"
            shift
            ;;
        --help)
            print_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            print_usage
            exit 1
            ;;
    esac
done

print_header

# Change to plugin directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PLUGIN_DIR"

echo "Configuration:"
echo "  RPC Endpoint: $RPC_URL"
echo "  Plugin Dir:   $PLUGIN_DIR"
echo ""

# Export RPC URL for tests
export BANKADVISOR_RPC_URL="$RPC_URL"

# Check if server is reachable
echo -n "Checking server connectivity... "
if curl -s --max-time 5 "$RPC_URL" > /dev/null 2>&1 || curl -s --max-time 5 "${RPC_URL%/rpc}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}Warning: Server may not be reachable${NC}"
    echo "Continuing anyway - tests will report connection errors if server is down."
fi
echo ""

# Check hostile queries file exists
HOSTILE_QUERIES_PATH="$PLUGIN_DIR/tests/data/hostile_queries.json"
if [[ ! -f "$HOSTILE_QUERIES_PATH" ]]; then
    echo -e "${RED}Error: Hostile queries file not found: $HOSTILE_QUERIES_PATH${NC}"
    exit 1
fi

QUERY_COUNT=$(python3 -c "import json; print(len(json.load(open('$HOSTILE_QUERIES_PATH'))['queries']))" 2>/dev/null || echo "?")
echo "Hostile queries loaded: $QUERY_COUNT"
echo ""

# Run tests
echo -e "${GREEN}Running tests...${NC}"
echo "pytest $PYTEST_ARGS $VERBOSE"
echo ""

# Activate virtual environment if available
if [[ -d "$PLUGIN_DIR/.venv" ]]; then
    source "$PLUGIN_DIR/.venv/bin/activate"
fi

# Run pytest
cd "$PLUGIN_DIR/src"
python -m pytest bankadvisor/tests/integration/test_nl2sql_dirty_data.py $PYTEST_ARGS $VERBOSE --tb=short 2>&1 | tee /tmp/nl2sql_dirty_results.log

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "=================================================="
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
else
    echo -e "${RED}Some tests failed. Exit code: $EXIT_CODE${NC}"
fi
echo "=================================================="
echo ""
echo "Full results saved to: /tmp/nl2sql_dirty_results.log"

exit $EXIT_CODE
