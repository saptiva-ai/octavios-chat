#!/bin/bash
# tests/integration/test_filemanager_restart_resilience.sh

echo "🧪 Test R-1: File Manager restart resilience"

if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"identifier":"demo@example.com","password":"Demo1234"}' | jq -r '.access_token')
fi

# Create a large dummy file (10MB) to ensure upload takes enough time to interrupt
dd if=/dev/urandom of=/tmp/large_file.bin bs=1M count=10 2>/dev/null

# 1. Start upload en background
(curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/tmp/large_file.bin" \
  -F "session_id=resilience_test" > /tmp/upload_result.json 2>&1) &

UPLOAD_PID=$!

echo "Upload started (PID: $UPLOAD_PID)..."

# 2. Wait 1 second and restart File Manager
sleep 1
echo "Restarting file-manager..."
docker compose -f infra/docker-compose.yml restart file-manager

# 3. Wait for upload to finish
wait $UPLOAD_PID
UPLOAD_EXIT_CODE=$?

echo "Upload process finished with exit code: $UPLOAD_EXIT_CODE"

# 4. Check result - logic:
# Ideally, curl should fail (non-zero exit) OR return a 502/503 error in the json.
# If it managed to finish before restart, the test is inconclusive but not failed.
# If it failed, we confirmed interruption.

if [ $UPLOAD_EXIT_CODE -ne 0 ]; then
    echo "✅ Upload interrupted/failed as expected during restart."
else
    # Check response content for error
    RESP=$(cat /tmp/upload_result.json)
    if [[ "$RESP" == *"error"* ]] || [[ "$RESP" == *"502"* ]] || [[ "$RESP" == *"503"* ]]; then
        echo "✅ Upload failed with error response as expected."
    else
        echo "⚠️  Upload finished successfully? Either too fast or restart delayed."
    fi
fi

# 5. Verify File Manager is healthy again
echo "Waiting for file-manager recovery..."
# Loop check for 30 seconds
for i in {1..30}; do
    HEALTH=$(curl -s http://localhost:8001/health | jq -r '.status' 2>/dev/null)
    if [ "$HEALTH" == "healthy" ]; then
        echo "✅ PASS: File Manager recovered after restart"
        rm /tmp/large_file.bin
        exit 0
    fi
    sleep 1
done

echo "❌ FAIL: File Manager not healthy after 30s"
rm /tmp/large_file.bin
exit 1
