#!/bin/bash
# tests/integration/test_minio_outage.sh

echo "🧪 Test R-3: MinIO down - File Manager returns proper error"

# 1. Stop MinIO
echo "Stopping minio..."
docker compose -f infra/docker-compose.yml stop minio

# 2. Try upload via File Manager
# Expecting 503 or 500, but handled.
echo "Attempting upload..."
UPLOAD_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST http://localhost:8001/upload \
  -F "file=@tests/fixtures/sample.pdf" \
  -F "user_id=outage_test")

HTTP_CODE=$(echo "$UPLOAD_RESPONSE" | grep HTTP_CODE | cut -d: -f2)

echo "HTTP Code: $HTTP_CODE"

# 3. Should return 503 Service Unavailable or 500 Internal Server Error (handled)
if [ "$HTTP_CODE" == "503" ] || [ "$HTTP_CODE" == "500" ]; then
  echo "✅ PASS: File Manager handled outage (returned $HTTP_CODE)"
else
  echo "❌ FAIL: Unexpected HTTP code: $HTTP_CODE"
  # Restart minio
  docker compose -f infra/docker-compose.yml start minio
  exit 1
fi

# 4. Restart MinIO
echo "Restarting minio..."
docker compose -f infra/docker-compose.yml start minio
echo "Waiting for minio recovery..."
sleep 10

# 5. Verify upload works again
UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:8001/upload \
  -F "file=@tests/fixtures/sample.pdf" \
  -F "user_id=outage_test")

MINIO_KEY=$(echo $UPLOAD_RESPONSE | jq -r '.minio_key')

if [ -n "$MINIO_KEY" ] && [ "$MINIO_KEY" != "null" ]; then
  echo "✅ PASS: File Manager recovered after MinIO restart"
else
  echo "❌ FAIL: Upload still failing after restart"
  echo $UPLOAD_RESPONSE
  exit 1
fi
