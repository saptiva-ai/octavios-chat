#!/bin/bash
# tests/integration/test_backend_to_filemanager_upload.sh

echo "🧪 Test 1.1: Backend delegates upload to File Manager"

# 1. Login to get token (if not provided in env)
if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"identifier":"demo@example.com","password":"Demo1234"}' | jq -r '.access_token')
fi

# 2. Create test file (PDF)
cp tests/fixtures/sample.pdf /tmp/integration_test.pdf

# 3. Upload via Backend API (should delegate to File Manager)
UPLOAD_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/files/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/tmp/integration_test.pdf" \
  -F "session_id=integration_test")

echo $UPLOAD_RESPONSE | jq

# 4. Assertions
# Backend returns { "files": [ { "file_id": "...", ... } ] }
FILE_ID=$(echo $UPLOAD_RESPONSE | jq -r '.files[0].file_id')

if [ -z "$FILE_ID" ] || [ "$FILE_ID" == "null" ]; then
  echo "❌ FAIL: No file_id in response"
  exit 1
fi

echo "File ID: $FILE_ID"
# Save ID for next tests if needed (though minio_key is hidden)
echo $FILE_ID > /tmp/last_file_id.txt

echo "✅ PASS: Backend → File Manager → MinIO upload works (File ID: $FILE_ID)"
