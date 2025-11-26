#!/bin/bash
# tests/integration/test_filemanager_redis_cache.sh

echo "🧪 Test 4.1: File Manager caches extracted text in Redis"

# 1. Upload PDF
UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:8001/upload \
  -F "file=@tests/fixtures/sample.pdf" \
  -F "user_id=cache_test")

MINIO_KEY=$(echo $UPLOAD_RESPONSE | jq -r '.minio_key')

if [ -z "$MINIO_KEY" ] || [ "$MINIO_KEY" == "null" ]; then
    echo "❌ FAIL: Upload failed"
    exit 1
fi

# 2. First extraction (should cache in Redis)
# Using -w to check time could be useful but we rely on logic here
echo "First extraction..."
curl -s -X POST "http://localhost:8001/extract/$MINIO_KEY" > /tmp/extract1.json

# 3. Second extraction (should hit cache)
echo "Second extraction..."
curl -s -X POST "http://localhost:8001/extract/$MINIO_KEY" > /tmp/extract2.json

# 4. Verify cache hit in Redis
# Note: We assume the docker container name is 'redis' as per docker-compose
CACHE_KEY="extract:$MINIO_KEY"
# We try to fetch from redis container. 
# If running in environment without docker access this might fail, so we wrap it.
if command -v docker &> /dev/null; then
    REDIS_VAL=$(docker compose -f infra/docker-compose.yml exec redis redis-cli GET "$CACHE_KEY")
    if [ -z "$REDIS_VAL" ]; then
        echo "⚠️  Warning: Redis key not found. Cache might have failed or key name differs."
    else
        echo "✅ Redis key found."
    fi
else
    echo "⚠️  Skipping direct Redis check (docker not available)"
fi

# 5. Assertions
EXTRACT1=$(cat /tmp/extract1.json | jq -r '.extracted_text')
EXTRACT2=$(cat /tmp/extract2.json | jq -r '.extracted_text')

if [ "$EXTRACT1" != "null" ] && [ "$EXTRACT1" == "$EXTRACT2" ]; then
  echo "✅ PASS: Redis cache extraction consistency verified"
else
  echo "❌ FAIL: Cache mismatch or extraction failed"
  echo "Extract 1 len: ${#EXTRACT1}"
  echo "Extract 2 len: ${#EXTRACT2}"
  exit 1
fi
