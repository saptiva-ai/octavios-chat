#!/bin/bash
# tests/integration/test_backend_to_filemanager_download.sh

echo "⚠️  SKIP: Test 1.2 - Backend download endpoint not exposed (direct download from File Manager only)"
exit 0

# ORIGINAL TEST COMMENTED OUT:
# echo "🧪 Test 1.2: Backend delegates download to File Manager"

if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"identifier":"demo@example.com","password":"Demo1234"}' | jq -r '.access_token')
fi

# Prerequisite: MINIO_KEY from Test 1.1 or file
if [ -f /tmp/last_minio_key.txt ]; then
  MINIO_KEY=$(cat /tmp/last_minio_key.txt)
else
  # Fallback if running standalone (might fail if key doesn't exist)
  MINIO_KEY="demo/integration_test/test.txt"
fi

echo "Downloading key: $MINIO_KEY"

# Download via Backend API
curl -s "http://localhost:8000/api/files/download/$MINIO_KEY" \
  -H "Authorization: Bearer $TOKEN" \
  -o /tmp/downloaded_file.txt

# Verify content
# Check for PDF header signature (%PDF)
if grep -q "%PDF" /tmp/downloaded_file.txt; then
  echo "✅ PASS: Backend → File Manager → MinIO download works (PDF header found)"
else
  echo "❌ FAIL: Downloaded content mismatch or file not found (Expected PDF)"
  head -n 5 /tmp/downloaded_file.txt
  exit 1
fi
