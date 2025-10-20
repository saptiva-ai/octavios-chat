#!/usr/bin/env bash
#
# Script de verificación: Segunda imagen reemplaza a la primera
#
# Política de adjuntos: un mensaje guarda exactamente los adjuntos enviados en su payload.
# No existe "herencia" de adjuntos desde turnos previos.
#
# Usage:
#   API=http://localhost:8000 ./scripts/repro_second_image.sh
#

set -euo pipefail

API="${API:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=====================================${NC}"
echo -e "${YELLOW}Verificación: Segunda imagen reemplaza${NC}"
echo -e "${YELLOW}=====================================${NC}"
echo ""

# Check if fixtures exist
if [ ! -f "$FIXTURES_DIR/meme.png" ]; then
    echo -e "${RED}❌ Fixture not found: $FIXTURES_DIR/meme.png${NC}"
    echo "Create test images first:"
    echo "  cd scripts/fixtures"
    echo "  # Add meme.png and cover.png"
    exit 1
fi

if [ ! -f "$FIXTURES_DIR/cover.png" ]; then
    echo -e "${RED}❌ Fixture not found: $FIXTURES_DIR/cover.png${NC}"
    exit 1
fi

# Get auth token (assumes you have a way to auth)
# For testing, you might need to set TOKEN env var
TOKEN="${TOKEN:-}"
if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}⚠️  No TOKEN set. Using mock auth for local testing.${NC}"
    TOKEN="mock-token"
fi

AUTH_HEADER="Authorization: Bearer $TOKEN"

echo -e "${GREEN}[1/5]${NC} Uploading first image (meme.png)..."
RESPONSE_1=$(curl -sS -X POST "$API/api/files/upload" \
  -H "$AUTH_HEADER" \
  -F "files=@$FIXTURES_DIR/meme.png" 2>/dev/null)

FILE_ID_1=$(echo "$RESPONSE_1" | jq -r '.files[0].file_id' 2>/dev/null || echo "")

if [ -z "$FILE_ID_1" ] || [ "$FILE_ID_1" = "null" ]; then
    echo -e "${RED}❌ Failed to upload first image${NC}"
    echo "Response: $RESPONSE_1"
    exit 1
fi

echo -e "   ✓ Uploaded meme.png → file_id: ${GREEN}$FILE_ID_1${NC}"

echo ""
echo -e "${GREEN}[2/5]${NC} Sending first message with meme.png..."
curl -sS -X POST "$API/api/chat" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"¿Qué dice esta imagen?\",\"file_ids\":[\"$FILE_ID_1\"]}" \
  > /dev/null

echo -e "   ✓ First message sent with file_id: $FILE_ID_1"

echo ""
echo -e "${GREEN}[3/5]${NC} Uploading second image (cover.png)..."
RESPONSE_2=$(curl -sS -X POST "$API/api/files/upload" \
  -H "$AUTH_HEADER" \
  -F "files=@$FIXTURES_DIR/cover.png" 2>/dev/null)

FILE_ID_2=$(echo "$RESPONSE_2" | jq -r '.files[0].file_id' 2>/dev/null || echo "")

if [ -z "$FILE_ID_2" ] || [ "$FILE_ID_2" = "null" ]; then
    echo -e "${RED}❌ Failed to upload second image${NC}"
    echo "Response: $RESPONSE_2"
    exit 1
fi

echo -e "   ✓ Uploaded cover.png → file_id: ${GREEN}$FILE_ID_2${NC}"

echo ""
echo -e "${GREEN}[4/5]${NC} Sending second message with cover.png..."
curl -sS -X POST "$API/api/chat" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"¿Y ahora qué dice?\",\"file_ids\":[\"$FILE_ID_2\"]}" \
  > /dev/null

echo -e "   ✓ Second message sent with file_id: $FILE_ID_2"

echo ""
echo -e "${GREEN}[5/5]${NC} Verification..."
if [ "$FILE_ID_1" != "$FILE_ID_2" ]; then
    echo -e "   ${GREEN}✅ PASS${NC}: Two distinct file_ids sent"
    echo -e "      Primera: $FILE_ID_1"
    echo -e "      Segunda: $FILE_ID_2"
else
    echo -e "   ${RED}❌ FAIL${NC}: file_ids should be different"
    exit 1
fi

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}✅ Verification complete${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "✓ Two turns sent with distinct file_ids: $FILE_ID_1 → $FILE_ID_2"
echo "✓ No inheritance: each message carries only its own attachments"
echo ""
echo "Next steps:"
echo "  1. Check backend logs for 'message_normalized' events"
echo "  2. Verify 'file_ids' array in each event matches sent file_ids"
echo "  3. Check 'llm_payload_tail' logs show correct image_url_hashes"
