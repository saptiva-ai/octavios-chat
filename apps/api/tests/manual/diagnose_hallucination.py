#!/usr/bin/env python3
"""
Comprehensive hallucination diagnosis script.

This script will:
1. Check if prompts are loading correctly
2. Inspect what text is being extracted from the problematic PDF
3. Verify what context is being sent to the LLM
4. Test if the system prompt is being applied
"""

import requests
import json
import time
import subprocess

API_BASE = "http://localhost:8001/api"
USERNAME = "demo"
PASSWORD = "Demo1234"


def login() -> str:
    """Login and return JWT token."""
    response = requests.post(
        f"{API_BASE}/auth/login",
        json={"identifier": USERNAME, "password": PASSWORD}
    )
    response.raise_for_status()
    return response.json()["access_token"]


def check_prompt_registry():
    """Check if prompt registry has the anti-hallucination rules."""
    print("=" * 80)
    print("CHECKING PROMPT REGISTRY")
    print("=" * 80)

    try:
        result = subprocess.run(
            ["docker", "exec", "octavios-chat-api",
             "cat", "/app/prompts/registry.yaml"],
            capture_output=True,
            text=True,
            timeout=5
        )

        registry = result.stdout

        # Check for key anti-hallucination phrases
        checks = {
            "Zero hallucinations rule": "CERO ALUCINACIONES - LEE ESTO CUIDADOSAMENTE" in registry,
            "No [entidad] placeholder": "NUNCA uses placeholders como" in registry,
            "Explicit content check": "EXPLÍCITAMENTE y LITERALMENTE presente" in registry,
            "Corrupted doc handling": "No puedo leer el contenido del documento" in registry
        }

        print("\nPrompt Registry Checks:")
        for check_name, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"{status} {check_name}")

        if not all(checks.values()):
            print("\n⚠️  PROBLEM: Prompt registry doesn't have all anti-hallucination rules!")
            print("   The prompts may not have been updated correctly.")
            return False

        print("\n✅ All anti-hallucination rules found in prompt registry")
        return True

    except Exception as e:
        print(f"❌ Failed to check prompt registry: {e}")
        return False


def check_document_extraction(token: str, filename: str):
    """Check what text was actually extracted from a document."""
    print("\n" + "=" * 80)
    print(f"CHECKING DOCUMENT: {filename}")
    print("=" * 80)

    try:
        # Search for the document in MongoDB via API
        result = subprocess.run(
            ["docker", "exec", "octavios-chat-api", "python", "-c", f"""
from pymongo import MongoClient
import json

client = MongoClient('mongodb://mongodb:27017/octavios')
db = client.octavios

doc = db.documents.find_one({{'filename': '{filename}'}}, sort=[('created_at', -1)])

if doc:
    pages = doc.get('pages', [])
    total_text = ''
    for page in pages:
        total_text += page.get('text_md', '') + '\\n'

    print(json.dumps({{
        'found': True,
        'status': doc.get('status'),
        'total_pages': len(pages),
        'total_chars': len(total_text.strip()),
        'text_preview': total_text.strip()[:500]
    }}))
else:
    print(json.dumps({{'found': False}}))

client.close()
"""],
            capture_output=True,
            text=True,
            timeout=10
        )

        data = json.loads(result.stdout.strip())

        if not data.get('found'):
            print(f"❌ Document '{filename}' not found in database")
            print("   The user may not have uploaded it yet")
            return None

        print(f"\n📄 Document Status: {data['status']}")
        print(f"   Pages: {data['total_pages']}")
        print(f"   Total characters: {data['total_chars']}")

        text_preview = data.get('text_preview', '')

        print(f"\n📝 Extracted Text Preview (first 500 chars):")
        print("-" * 80)
        print(text_preview if text_preview else "(EMPTY)")
        print("-" * 80)

        # Diagnosis
        print("\n🔍 DIAGNOSIS:")
        if data['total_chars'] == 0:
            print("❌ CRITICAL: NO TEXT EXTRACTED")
            print("   This explains the hallucinations - LLM has no content to reference")
            print("   Recommendations:")
            print("   1. Check if PDF is image-only (no text layer)")
            print("   2. Verify OCR is working")
            print("   3. Check extraction logs")
        elif data['total_chars'] < 150:
            print(f"⚠️  WARNING: Very little text ({data['total_chars']} chars < 150 threshold)")
            print("   OCR should have been triggered but may have failed")
        elif not text_preview or len(text_preview.split()) < 10:
            print("⚠️  WARNING: Text looks corrupted or nonsensical")
            print("   Quality checks may have failed")
        else:
            print("✅ Text extraction looks OK")
            print(f"   Found {len(text_preview.split())} words in preview")

        return data

    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse response: {e}")
        print(f"Raw output: {result.stdout}")
        return None
    except Exception as e:
        print(f"❌ Failed to check document: {e}")
        return None


def check_rag_context_in_logs():
    """Check what context is actually being sent to the LLM in recent requests."""
    print("\n" + "=" * 80)
    print("CHECKING RAG CONTEXT IN LOGS")
    print("=" * 80)

    try:
        result = subprocess.run(
            ["docker", "logs", "octavios-chat-api", "--tail", "500"],
            capture_output=True,
            text=True,
            timeout=5
        )

        logs = result.stdout + result.stderr

        # Look for document context injection
        found_context = False
        for line in logs.split('\n'):
            if "Added document context to prompt" in line:
                found_context = True
                print("\n✅ Found document context injection:")
                try:
                    log_json = json.loads(line)
                    print(f"   Context length: {log_json.get('context_length', 'unknown')} chars")
                    print(f"   Has images: {log_json.get('has_images', False)}")
                    print(f"   Has PDFs: {log_json.get('has_pdfs', False)}")
                except:
                    print(f"   {line[:200]}")

        if not found_context:
            print("⚠️  No document context injection found in recent logs")
            print("   Either no RAG queries were made, or context is empty")

        # Look for system prompt issues
        for line in logs.split('\n'):
            if "[entidad]" in line:
                print(f"\n❌ FOUND '[entidad]' in logs:")
                print(f"   {line[:300]}")
                print("   This suggests the prompt still has the placeholder!")

    except Exception as e:
        print(f"❌ Failed to check logs: {e}")


def main():
    print("=" * 80)
    print("COMPREHENSIVE HALLUCINATION DIAGNOSIS")
    print("=" * 80)
    print()

    # Step 1: Login
    print("[1/4] Logging in...")
    try:
        token = login()
        print("✅ Logged in successfully")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return

    # Step 2: Check prompt registry
    print("\n[2/4] Checking prompt registry...")
    prompt_ok = check_prompt_registry()

    # Step 3: Check document extraction
    print("\n[3/4] Checking document extraction...")
    doc_data = check_document_extraction(token, "Capital414_usoIA.pdf")

    # Step 4: Check RAG context in logs
    print("\n[4/4] Checking RAG context in logs...")
    check_rag_context_in_logs()

    # Final diagnosis
    print("\n" + "=" * 80)
    print("FINAL DIAGNOSIS")
    print("=" * 80)

    if not prompt_ok:
        print("\n🔴 CRITICAL: Prompts not updated correctly")
        print("   Action: Verify prompts/registry.yaml was saved and API restarted")

    if doc_data and doc_data['total_chars'] == 0:
        print("\n🔴 CRITICAL: Document has NO extracted text")
        print("   This is the ROOT CAUSE of hallucinations")
        print("   The LLM has no content to reference, so it invents everything")
        print("\n   Recommended actions:")
        print("   1. Re-upload the PDF to trigger re-processing")
        print("   2. Check OCR logs to see why extraction failed")
        print("   3. Verify the PDF is not just an image without text layer")

    if doc_data and doc_data['total_chars'] > 0 and doc_data['total_chars'] < 150:
        print("\n🟡 WARNING: Document has very little text")
        print("   OCR may have failed or returned poor results")

    print()


if __name__ == "__main__":
    main()
