#!/usr/bin/env bash
#
# Test script for Document Audit validation API
#
# Usage:
#   ./scripts/test_validation.sh /path/to/document.pdf [client_name]
#
# Example:
#   ./scripts/test_validation.sh ~/Documents/report.pdf Banamex
#

set -e

PDF_PATH="${1:-}"
CLIENT_NAME="${2:-TestClient}"
API_BASE="${API_BASE:-http://localhost:8001}"
CLIENT_NAME_ENCODED=$(jq -rn --arg v "$CLIENT_NAME" '$v|@uri')

if [ -z "$PDF_PATH" ]; then
    echo "Usage: $0 <pdf_path> [client_name]"
    echo ""
    echo "Example:"
    echo "  $0 ~/Documents/report.pdf Banamex"
    exit 1
fi

if [ ! -f "$PDF_PATH" ]; then
    echo "Error: PDF file not found: $PDF_PATH"
    exit 1
fi

echo "=========================================="
echo "Document Audit - Validation Test"
echo "=========================================="
echo "PDF: $PDF_PATH"
echo "Client: $CLIENT_NAME"
echo "API: $API_BASE"
echo ""

# Step 1: Login and get token
echo "[1/4] Authenticating..."
TOKEN=$(curl -s -X POST "$API_BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '''{"identifier": "demo", "password": "Demo1234"}''' \
  | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "Error: Authentication failed. Is the API running? (make dev)"
    exit 1
fi

echo "✓ Authenticated"
echo ""

# Get user ID
echo "[1.5/4] Getting user ID..."
USER_ID=$(curl -s -X GET "$API_BASE/api/auth/me" \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.id')

if [ -z "$USER_ID" ] || [ "$USER_ID" = "null" ]; then
    echo "Error: Failed to get user ID"
    exit 1
fi
echo "✓ User ID: $USER_ID"
echo ""

# Create chat session
echo "[1.7/4] Creating chat session..."
CHAT_ID=$(curl -s -X POST "$API_BASE/api/conversations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '''{}''' \
  | jq -r '.id')

if [ -z "$CHAT_ID" ] || [ "$CHAT_ID" = "null" ]; then
    echo "Error: Failed to create chat session"
    exit 1
fi
echo "✓ Chat ID: $CHAT_ID"
echo ""

# Step 2: Upload PDF
echo "[2/4] Uploading PDF..."
UPLOAD_RESPONSE=$(curl -s -X POST "$API_BASE/api/files/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@$PDF_PATH")

DOC_ID=$(echo "$UPLOAD_RESPONSE" | jq -r '.files[0].file_id // .document_id')

if [ -z "$DOC_ID" ] || [ "$DOC_ID" = "null" ]; then
    echo "Error: Upload failed"
    echo "$UPLOAD_RESPONSE" | jq .
    exit 1
fi

echo "✓ Uploaded: $DOC_ID"
echo ""

# Step 3: Wait for processing
echo "[3/4] Waiting for document processing..."
for i in {1..30}; do
    STATUS=$(curl -s "$API_BASE/api/documents/$DOC_ID" \
      -H "Authorization: Bearer $TOKEN" \
      | jq -r '.status')

    if [ "$STATUS" = "ready" ] || [ "$STATUS" = "READY" ]; then
        echo "✓ Document ready"
        break
    elif [ "$STATUS" = "failed" ] || [ "$STATUS" = "FAILED" ]; then
        echo "Error: Document processing failed"
        exit 1
    fi

    echo "  Status: $STATUS (waiting... $i/30)"
    sleep 2
done

if [ "$STATUS" != "ready" ] && [ "$STATUS" != "READY" ]; then
    echo "Error: Timeout waiting for document processing"
    exit 1
fi

echo ""

# Step 4: Run validation
echo "[4/4] Running validation..."
VALIDATION_RESPONSE=$(curl -s -X POST \
  "$API_BASE/api/review/validate?doc_id=$DOC_ID&client_name=$CLIENT_NAME_ENCODED" \
  -H "Authorization: Bearer $TOKEN")

echo "$VALIDATION_RESPONSE" | jq .

# Parse results (support legacy and current schema)
JOB_ID=$(echo "$VALIDATION_RESPONSE" | jq -r '.job_id // .metadata.job_id // "N/A"')
STATUS_VALUE=$(echo "$VALIDATION_RESPONSE" | jq -r '.status // .metadata.status // "unknown"')
TOTAL_FINDINGS=$(echo "$VALIDATION_RESPONSE" | jq '.summary.total_findings // .metadata.summary.total_findings // 0')
DURATION_MS=$(echo "$VALIDATION_RESPONSE" | jq -r '.summary.total_duration_ms // .metadata.summary.validation_duration_ms // "N/A"')

echo ""
echo "=========================================="
echo "Results Summary"
echo "=========================================="
echo "Job ID: $JOB_ID"
echo "Status: $STATUS_VALUE"
echo "Total findings: $TOTAL_FINDINGS"
echo "Processing time: $DURATION_MS ms"
echo ""

# Exit with error if critical findings
if [ "$STATUS_VALUE" != "completed" ] && [ "$STATUS_VALUE" != "done" ]; then
    echo "⚠️  VALIDATION FAILED"
    exit 1
else
    echo "✓ No critical issues"
    exit 0
fi
