#!/bin/bash
# tests/integration/test_full_audit_flow.sh

echo "🧪 Test IPC-1: Full audit flow (Frontend → Backend → Capital414 → FileManager)"

if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"identifier":"demo@example.com","password":"Demo1234"}' | jq -r '.access_token')
fi

SESSION_ID="full_flow_test_$(date +%s)"

# 1. Upload PDF via Backend (Backend → FileManager)
UPLOAD_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/files/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@tests/fixtures/copiloto414_compliant.pdf" \
  -F "session_id=$SESSION_ID")

FILE_ID=$(echo $UPLOAD_RESPONSE | jq -r '.files[0].file_id')

if [ -z "$FILE_ID" ] || [ "$FILE_ID" == "null" ]; then
    echo "❌ FAIL: Upload failed"
    echo $UPLOAD_RESPONSE
    exit 1
fi

# 2. Send audit command via Chat (Backend → Capital414 via MCP)
CHAT_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"Auditar archivo: copiloto414_compliant.pdf\",
    \"session_id\": \"$SESSION_ID\",
    \"file_ids\": [\"$FILE_ID\"]
  }")

# 3. Extract audit result
# Structure might be metadata -> tool_invocations -> result -> id (artifact id)
ARTIFACT_ID=$(echo $CHAT_RESPONSE | jq -r '.metadata.tool_invocations[0].result.id')

if [ "$ARTIFACT_ID" == "null" ]; then
    # Fallback: maybe it's directly in the content or different structure
    echo "⚠️  Warning: Artifact ID not found in standard path. checking content..."
    echo $CHAT_RESPONSE | jq
    # If strict check fails, we exit
    echo "❌ FAIL: Artifact ID not found in response"
    exit 1
fi

# 4. Fetch artifact (audit report)
ARTIFACT=$(curl -s "http://localhost:8000/api/artifacts/$ARTIFACT_ID" \
  -H "Authorization: Bearer $TOKEN")

# 5. Assertions
# Check content field or findings
CONTENT=$(echo $ARTIFACT | jq -r '.content')

# Flexible check: look for "Auditoría" or "Reporte" or markdown headers
if [[ "$CONTENT" == *"Auditoría"* ]] || [[ "$CONTENT" == *"Reporte"* ]] || [[ "$CONTENT" == "# "* ]]; then
  echo "✅ PASS: Full audit flow works end-to-end (Artifact content verified)"
else
  echo "❌ FAIL: Audit flow incomplete. Content mismatch."
  echo "Content start: ${CONTENT:0:100}..."
  exit 1
fi
