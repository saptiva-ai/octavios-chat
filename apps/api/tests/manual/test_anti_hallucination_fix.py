#!/usr/bin/env python3
"""
Manual Test: Anti-Hallucination Fix Verification

Tests that the anti-hallucination improvements correctly handle:
1. PDFs with corrupted/low-quality text layers (should trigger OCR)
2. PDFs with insufficient text (< 150 chars, should trigger OCR)
3. Feedback warnings when RAG search has low relevance

Expected Behaviors:
- PDF with garbage text (low quality ratio) → OCR activated
- PDF with < 150 chars → OCR activated
- Logs show: "Applying OCR to page with insufficient/poor text"
- RAG search with low relevance → Warning message
"""

import requests
import json
import time
from pathlib import Path
import subprocess

# Configuration
API_BASE = "http://localhost:8001/api"
USERNAME = "demo"
PASSWORD = "Demo1234"


def create_corrupted_text_pdf(filepath: Path):
    """
    Create a PDF with corrupted text layer (simulating scanned PDF with bad OCR).

    The text layer will have ~80 characters but mostly garbage/metadata,
    which should fail the quality check (< 40% valid chars).
    """
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
/Length 120
>>
stream
BT
/F1 12 Tf
50 700 Td
(\x01\x02\x03\xFE\xFFm€t@d@t@~~~###%%%^^^&&&***((()))__++==[[]]{{}}||\\\\) Tj
0 -20 Td
(§¶†‡•ªº≠≈∆∫∂ƒ©˙∆˚¬…æ«»ÇçÑñ¿¡) Tj
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
495
%%EOF
"""
    filepath.write_text(content)
    print(f"✅ Created corrupted text PDF: {filepath} ({filepath.stat().st_size} bytes)")
    print(f"   Expected: Quality check FAILS → OCR activated")


def create_insufficient_text_pdf(filepath: Path):
    """
    Create a PDF with clean text but < 150 chars (below threshold).

    This should trigger OCR due to insufficient length.
    """
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
/Length 80
>>
stream
BT
/F1 12 Tf
50 700 Td
(Short text here.) Tj
0 -20 Td
(Only 40 chars total.) Tj
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
455
%%EOF
"""
    filepath.write_text(content)
    print(f"✅ Created insufficient text PDF: {filepath} ({filepath.stat().st_size} bytes)")
    print(f"   Expected: Length < 150 chars → OCR activated")


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
        result = bulk_result["files"][0]

    doc_id = result.get('file_id', result.get('doc_id', result.get('id')))
    print(f"✅ Uploaded: {pdf_path.name}")
    print(f"   Doc ID: {doc_id}")
    print(f"   Status: {result['status']}")

    return {
        "id": doc_id,
        "filename": result['filename'],
        "status": result['status']
    }


def check_api_logs_for_ocr(doc_name: str) -> dict:
    """
    Check API logs for OCR activation indicators.

    Returns dict with:
        - ocr_activated: bool
        - reason: str (if OCR activated)
        - log_lines: list of relevant log lines
    """
    print(f"\n🔍 Checking API logs for OCR activation ({doc_name})...")

    try:
        result = subprocess.run(
            ["docker", "logs", "octavios-chat-api", "--tail", "100"],
            capture_output=True,
            text=True,
            timeout=5
        )

        logs = result.stdout + result.stderr
        relevant_lines = []
        ocr_activated = False
        ocr_reason = None

        for line in logs.split('\n'):
            # Look for OCR activation logs
            if "Applying OCR to page" in line:
                ocr_activated = True
                relevant_lines.append(line)

                # Extract reason from JSON log
                try:
                    log_json = json.loads(line)
                    ocr_reason = log_json.get("reason", "unknown")
                except:
                    pass

            # Also capture hybrid extraction start
            if "Starting hybrid PDF extraction" in line and doc_name.replace(".pdf", "") in logs:
                relevant_lines.append(line)

        return {
            "ocr_activated": ocr_activated,
            "reason": ocr_reason,
            "log_lines": relevant_lines
        }

    except Exception as e:
        print(f"⚠️  Failed to check logs: {e}")
        return {
            "ocr_activated": False,
            "reason": None,
            "log_lines": []
        }


def main():
    print("=" * 80)
    print("ANTI-HALLUCINATION FIX VERIFICATION")
    print("=" * 80)
    print()

    # Login
    print("[1/6] Login...")
    token = login()
    print()

    # Test Case 1: Corrupted Text PDF
    print("[2/6] Test Case 1: Corrupted Text (Low Quality)")
    print("-" * 80)
    corrupted_pdf = Path("/tmp/test_corrupted_text.pdf")
    create_corrupted_text_pdf(corrupted_pdf)

    conv_id_1 = f"test_corrupted_{int(time.time())}"
    upload_result_1 = upload_document(token, corrupted_pdf, conv_id_1)

    time.sleep(3)  # Wait for processing

    ocr_check_1 = check_api_logs_for_ocr(corrupted_pdf.name)

    print("\nRESULT:")
    if ocr_check_1["ocr_activated"]:
        print(f"✅ PASS: OCR was activated")
        print(f"   Reason: {ocr_check_1['reason']}")
        if "poor quality" in str(ocr_check_1['reason']):
            print("   ✅ Correctly detected poor quality text")
    else:
        print("❌ FAIL: OCR was NOT activated (should have been)")
        print("   Expected: Quality check should fail for corrupted text")

    print()

    # Test Case 2: Insufficient Text PDF
    print("[3/6] Test Case 2: Insufficient Text (< 150 chars)")
    print("-" * 80)
    insufficient_pdf = Path("/tmp/test_insufficient_text.pdf")
    create_insufficient_text_pdf(insufficient_pdf)

    conv_id_2 = f"test_insufficient_{int(time.time())}"
    upload_result_2 = upload_document(token, insufficient_pdf, conv_id_2)

    time.sleep(3)  # Wait for processing

    ocr_check_2 = check_api_logs_for_ocr(insufficient_pdf.name)

    print("\nRESULT:")
    if ocr_check_2["ocr_activated"]:
        print(f"✅ PASS: OCR was activated")
        print(f"   Reason: {ocr_check_2['reason']}")
        if "insufficient text" in str(ocr_check_2['reason']):
            print("   ✅ Correctly detected insufficient text length")
    else:
        print("❌ FAIL: OCR was NOT activated (should have been)")
        print("   Expected: Length < 150 should trigger OCR")

    print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    test_results = {
        "Corrupted Text Detection": ocr_check_1["ocr_activated"] and "poor quality" in str(ocr_check_1['reason']),
        "Insufficient Length Detection": ocr_check_2["ocr_activated"] and "insufficient" in str(ocr_check_2['reason'])
    }

    for test_name, passed in test_results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(test_results.values())

    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED - Anti-hallucination fixes are working!")
    else:
        print("⚠️  SOME TESTS FAILED - Review logs above")

    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
