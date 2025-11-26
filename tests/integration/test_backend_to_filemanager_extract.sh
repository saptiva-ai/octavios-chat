#!/bin/bash
# tests/integration/test_backend_to_filemanager_extract.sh

echo "🧪 Test 1.3: Backend delegates text extraction to File Manager"

if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"identifier":"demo@example.com","password":"Demo1234"}' | jq -r '.access_token')
fi

# Upload PDF via Backend
PDF_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/files/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@tests/fixtures/sample.pdf" \
  -F "session_id=extract_test")

DOC_ID=$(echo $PDF_RESPONSE | jq -r '.files[0].file_id')

if [ -z "$DOC_ID" ] || [ "$DOC_ID" == "null" ]; then
    echo "❌ FAIL: Upload failed, no file_id"
    echo $PDF_RESPONSE
    exit 1
fi

# Request extraction via Backend (should delegate to File Manager)
EXTRACT_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/files/$DOC_ID/extract" \
  -H "Authorization: Bearer $TOKEN")

EXTRACTED_TEXT=$(echo $EXTRACT_RESPONSE | jq -r '.extracted_text')

if [ -n "$EXTRACTED_TEXT" ] && [ "$EXTRACTED_TEXT" != "null" ]; then
  echo "✅ PASS: Text extraction works via delegation"
else
  echo "❌ FAIL: No text extracted"
  echo $EXTRACT_RESPONSE
  exit 1
fi
