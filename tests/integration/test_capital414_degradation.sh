#!/bin/bash
# tests/integration/test_capital414_degradation.sh

echo "🧪 Test R-2: Capital414 down - Backend handles gracefully"

if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"identifier":"demo@example.com","password":"Demo1234"}' | jq -r '.access_token')
fi

# 1. Stop Capital414
echo "Stopping file-auditor..."
docker compose -f infra/docker-compose.yml stop file-auditor

# 2. Try audit command via Backend
# Should not crash the backend, but return a polite error message via chat or HTTP error
echo "Sending audit request..."
CHAT_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"Auditar archivo: test.pdf\",
    \"session_id\": \"degradation_test\"
  }")

echo "Response received."

# 3. Backend should still be healthy
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/health")

if [ "$HTTP_CODE" == "200" ]; then
  echo "✅ PASS: Backend survived Capital414 being down (Health check OK)"
else
  echo "❌ FAIL: Backend crashed or unhealthy (HTTP $HTTP_CODE)"
  # Restart before exiting to restore state
  docker compose -f infra/docker-compose.yml start file-auditor
  exit 1
fi

# 4. Restart Capital414
echo "Restarting file-auditor..."
docker compose -f infra/docker-compose.yml start file-auditor
echo "Waiting for capital414 recovery..."
sleep 10 # Give it time to start
