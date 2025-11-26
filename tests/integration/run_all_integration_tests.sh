#!/bin/bash
# tests/integration/run_all_integration_tests.sh

set -e  # Exit on first failure

echo "🚀 Running Integration Test Suite for Plugin-First Architecture"
echo "================================================================"

export COMPOSE_PROJECT_NAME=octavios-chat-capital414

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED_TESTS=()
PASSED_TESTS=()

run_test() {
  TEST_NAME=$1
  TEST_SCRIPT=$2

  echo -e "\n${YELLOW}▶ Running: $TEST_NAME${NC}"

  if bash "$TEST_SCRIPT"; then
    echo -e "${GREEN}✅ PASSED: $TEST_NAME${NC}"
    PASSED_TESTS+=("$TEST_NAME")
  else
    echo -e "${RED}❌ FAILED: $TEST_NAME${NC}"
    FAILED_TESTS+=("$TEST_NAME")
  fi
}

# Prerequisites
echo "📋 Prerequisites check..."
if ! curl -s http://localhost:8000/api/health > /dev/null; then
  echo "❌ Backend not running. Run 'make dev' first."
  exit 1
fi

# Get auth token
export TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier":"demo@example.com","password":"Demo1234"}' | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
  echo "❌ Failed to get auth token. Check demo user exists."
  exit 1
fi

echo "✅ Prerequisites OK"
echo ""

# Run test suites
run_test "Backend → FileManager Upload" "tests/integration/test_backend_to_filemanager_upload.sh"
run_test "Backend → FileManager Download" "tests/integration/test_backend_to_filemanager_download.sh"
run_test "Backend → FileManager Extract" "tests/integration/test_backend_to_filemanager_extract.sh"
run_test "Backend → Capital414 MCP" "tests/integration/test_backend_to_capital414_mcp.sh"
run_test "Full Audit Flow" "tests/integration/test_full_audit_flow.sh"
run_test "FileManager Redis Cache" "tests/integration/test_filemanager_redis_cache.sh"

# Resilience tests
run_test "FileManager Restart Resilience" "tests/integration/test_filemanager_restart_resilience.sh"
run_test "Capital414 Degradation" "tests/integration/test_capital414_degradation.sh"
run_test "MinIO Outage Handling" "tests/integration/test_minio_outage.sh"

# Performance tests (optional)
if [ "$RUN_PERF_TESTS" == "true" ]; then
  run_test "FileManager Throughput" "tests/integration/test_filemanager_throughput.sh"
fi

# Summary
echo ""
echo "================================================================"
echo "📊 Test Summary"
echo "================================================================"
echo -e "${GREEN}Passed: ${#PASSED_TESTS[@]}${NC}"
echo -e "${RED}Failed: ${#FAILED_TESTS[@]}${NC}"

if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
  echo ""
  echo -e "${RED}Failed tests:${NC}"
  for test in "${FAILED_TESTS[@]}"; do
    echo "  - $test"
  done
  exit 1
else
  echo ""
  echo -e "${GREEN}🎉 All integration tests passed!${NC}"
  exit 0
fi
