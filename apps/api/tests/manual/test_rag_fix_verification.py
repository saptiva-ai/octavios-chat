#!/usr/bin/env python3
"""
Manual Test: RAG Fix Verification
Tests that document segmentation works synchronously for small files after MinIO migration fix.

Expected Behavior:
1. Upload PDF → text extracted → status=ready
2. Chat with document_ids → IngestFilesTool processes sync
3. Segmentation completes BEFORE GetRelevantSegmentsTool lookup
4. AI responds with document context (NOT "No document provided")
"""

import requests
import json
import time
from pathlib import Path

# Configuration
API_BASE = "http://localhost:8001/api"
USERNAME = "demo"
PASSWORD = "Demo1234"

def create_test_pdf(filepath: Path):
    """Create a test PDF with known content."""
    content = """%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 200
>>
stream
BT
/F1 12 Tf
50 700 Td
(TEST DOCUMENT - RAG FIX VERIFICATION) Tj
0 -20 Td
(This document contains information about ClientProject's main product.) Tj
0 -20 Td
(Our flagship product is called OCTAVIOS CHAT.) Tj
0 -20 Td
(It was launched on January 15, 2025.) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000315 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
565
%%EOF
"""
    filepath.write_text(content)
    print(f"✅ Created test PDF: {filepath} ({filepath.stat().st_size} bytes)")


def login() -> str:
    """Login and return JWT token."""
    response = requests.post(
        f"{API_BASE}/auth/login",
        json={"identifier": USERNAME, "password": PASSWORD}
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    print(f"✅ Logged in as {USERNAME}")
    return token


def upload_document(token: str, pdf_path: Path, conversation_id: str) -> dict:
    """Upload document and return response."""
    with open(pdf_path, "rb") as f:
        files = {"files": (pdf_path.name, f, "application/pdf")}
        data = {"conversation_id": conversation_id}
        headers = {"Authorization": f"Bearer {token}"}

        response = requests.post(
            f"{API_BASE}/files/upload",
            headers=headers,
            files=files,
            data=data
        )
        response.raise_for_status()
        bulk_result = response.json()

        # Extract first file from bulk response
        result = bulk_result["files"][0]
        print(f"DEBUG: Response = {json.dumps(result, indent=2)}")

    doc_id = result.get('file_id', result.get('doc_id', result.get('id')))
    print(f"✅ Uploaded document: {doc_id}")
    print(f"   Filename: {result['filename']}")
    print(f"   Size: {result.get('bytes', result.get('size_bytes', 'unknown'))} bytes")
    print(f"   Status: {result['status']}")

    # Return normalized result
    return {
        "id": doc_id,
        "filename": result['filename'],
        "status": result['status']
    }


def send_chat_message(token: str, conversation_id: str, document_ids: list, query: str) -> dict:
    """Send chat message with document context."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "message": query,
        "conversation_id": conversation_id,
        "model": "SAPTIVA_CORTEX",
        "stream": False,  # Non-streaming for easier testing
        "document_ids": document_ids
    }

    print(f"\n📤 Sending chat message:")
    print(f"   Query: {query}")
    print(f"   Document IDs: {document_ids}")

    response = requests.post(
        f"{API_BASE}/chat",
        headers=headers,
        json=payload
    )
    response.raise_for_status()
    result = response.json()

    return result


def main():
    print("=" * 80)
    print("TEST: RAG Fix Verification (MinIO Migration + Sync Processing)")
    print("=" * 80)
    print()

    # Step 1: Login
    print("[1/5] Login...")
    token = login()
    print()

    # Step 2: Create test PDF
    print("[2/5] Create test PDF...")
    test_pdf = Path("/tmp/test_rag_fix_verification.pdf")
    create_test_pdf(test_pdf)
    print()

    # Step 3: Upload document
    print("[3/5] Upload document...")
    conversation_id = f"test_rag_fix_{int(time.time())}"
    upload_result = upload_document(token, test_pdf, conversation_id)
    doc_id = upload_result["id"]
    print()

    # Step 4: Wait for processing (should be instant with sync processing)
    print("[4/5] Wait 2 seconds for sync processing...")
    time.sleep(2)
    print("✅ Wait complete")
    print()

    # Step 5: Send chat message with document context
    print("[5/5] Send chat message with document context...")
    query = "¿Cuál es el producto principal de ClientProject según el documento?"

    try:
        chat_result = send_chat_message(token, conversation_id, [doc_id], query)

        print("\n" + "=" * 80)
        print("FULL RESPONSE DATA:")
        print("=" * 80)
        print(json.dumps(chat_result, indent=2))
        print()

        print("=" * 80)
        print("RESPONSE TEXT:")
        print("=" * 80)
        print(chat_result.get("response", ""))
        print()

        # Validation
        response_text = chat_result.get("response", "").lower()

        print("=" * 80)
        print("VALIDATION:")
        print("=" * 80)

        if "no se ha proporcionado" in response_text or "no document" in response_text:
            print("❌ FAILED: AI says no document was provided")
            print("   This means segments were NOT ready when GetRelevantSegmentsTool ran")
            return False

        if "octavios chat" in response_text:
            print("✅ PASSED: AI correctly identified 'OCTAVIOS CHAT' from document")
            print("   This confirms:")
            print("   - Document was downloaded from MinIO")
            print("   - Text was extracted successfully")
            print("   - Segmentation completed synchronously")
            print("   - Segments were available for RAG")
            return True

        print("⚠️  UNCLEAR: AI responded but didn't mention expected content")
        print("   Response may be valid but unexpected")
        return None

    except Exception as e:
        print(f"\n❌ FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
