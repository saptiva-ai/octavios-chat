#!/bin/bash
# tests/integration/test_backend_to_capital414_mcp.sh

echo "🧪 Test 2.1: Backend invokes Capital414 audit via MCP"

if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"identifier":"demo@example.com","password":"Demo1234"}' | jq -r '.access_token')
fi

# 1. Upload PDF to File Manager first (Direct upload to plugin to get key)
UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:8001/upload \
  -F "file=@tests/fixtures/copiloto414_compliant.pdf" \
  -F "user_id=audit_test" \
  -F "session_id=mcp_test")

MINIO_KEY=$(echo $UPLOAD_RESPONSE | jq -r '.minio_key')

if [ -z "$MINIO_KEY" ] || [ "$MINIO_KEY" == "null" ]; then
    echo "❌ FAIL: Direct upload to File Manager failed"
    echo $UPLOAD_RESPONSE
    exit 1
fi

# 2. Invoke audit via Backend Chat API (should use MCP to Capital414)
CHAT_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"Auditar archivo: copiloto414_compliant.pdf\",
    \"session_id\": \"mcp_test_$(date +%s)\",
    \"file_ids\": [\"$MINIO_KEY\"]
  }")

# 3. Assertions
TOOL_INVOCATIONS=$(echo $CHAT_RESPONSE | jq '.metadata.tool_invocations')

if [ "$TOOL_INVOCATIONS" == "null" ] || [ -z "$TOOL_INVOCATIONS" ]; then
  echo "❌ FAIL: No tool_invocations in response"
  echo "Full response: $CHAT_RESPONSE"
  exit 1
fi

# Check if result contains the tool name (checking result string or structure)
# The result might be a JSON object or string, checking for presence of 'audit_document_full'
# Adjusting logic to be flexible
echo "Tool Invocations: $TOOL_INVOCATIONS"

if echo "$TOOL_INVOCATIONS" | grep -q "audit_document_full"; then
  echo "✅ PASS: Backend → Capital414 MCP invocation works (found audit_document_full)"
else
  # Try checking the tool name field specifically
  TOOL_NAME=$(echo $CHAT_RESPONSE | jq -r '.metadata.tool_invocations[0].tool_name')
  if [ "$TOOL_NAME" == "audit_document_full" ]; then
      echo "✅ PASS: Backend → Capital414 MCP invocation works (tool_name match)"
  else
      echo "❌ FAIL: MCP tool not invoked correctly. Found: $TOOL_NAME"
      exit 1
  fi
fi
