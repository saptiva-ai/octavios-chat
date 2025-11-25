#!/usr/bin/env python3
"""
Script to inspect what text is actually being extracted from a PDF.
This helps diagnose hallucination issues.
"""

import sys
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

async def inspect_pdf(pdf_path: str):
    """Inspect text extraction from a PDF."""
    from src.services.document_extraction import extract_text_from_file, _is_text_quality_sufficient

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"❌ File not found: {pdf_path}")
        return

    print("=" * 80)
    print(f"INSPECTING: {pdf_file.name}")
    print("=" * 80)
    print()

    # Extract text
    print("Extracting text...")
    pages = await extract_text_from_file(pdf_file, "application/pdf")

    print(f"\n📄 Total pages extracted: {len(pages)}")
    print()

    # Analyze each page
    for i, page in enumerate(pages, 1):
        text = page.text_md or ""
        text_clean = text.strip()

        print(f"--- PAGE {i} ---")
        print(f"Length: {len(text_clean)} characters")

        # Quality check
        if text_clean:
            valid_chars = sum(1 for c in text_clean if c.isalnum() or c.isspace())
            total_chars = len(text_clean)
            quality_ratio = valid_chars / total_chars if total_chars > 0 else 0
            is_quality_ok = _is_text_quality_sufficient(text_clean)

            print(f"Quality: {quality_ratio:.1%} valid chars ({'✅ PASS' if is_quality_ok else '❌ FAIL'})")

            # Show character breakdown
            alpha = sum(1 for c in text_clean if c.isalpha())
            numeric = sum(1 for c in text_clean if c.isdigit())
            spaces = sum(1 for c in text_clean if c.isspace())
            special = total_chars - alpha - numeric - spaces

            print(f"  - Alphabetic: {alpha} ({alpha/total_chars:.1%})")
            print(f"  - Numeric: {numeric} ({numeric/total_chars:.1%})")
            print(f"  - Spaces: {spaces} ({spaces/total_chars:.1%})")
            print(f"  - Special chars: {special} ({special/total_chars:.1%})")
        else:
            print("Quality: N/A (empty)")

        # Show preview
        print("\nText preview (first 500 chars):")
        print("-" * 40)
        preview = text_clean[:500] if text_clean else "(EMPTY)"
        print(preview)
        print("-" * 40)

        # Show raw bytes (first 200 chars) to detect encoding issues
        if text_clean:
            print("\nRaw representation (first 200 chars):")
            print(repr(text_clean[:200]))

        print()

    # Overall assessment
    print("=" * 80)
    print("ASSESSMENT:")
    print("=" * 80)

    total_text = " ".join(p.text_md or "" for p in pages).strip()

    if not total_text:
        print("❌ NO TEXT EXTRACTED - Document is image-only or OCR failed")
    elif len(total_text) < 150:
        print(f"⚠️  INSUFFICIENT TEXT - Only {len(total_text)} chars (< 150 threshold)")
    elif not _is_text_quality_sufficient(total_text):
        valid_ratio = sum(1 for c in total_text if c.isalnum() or c.isspace()) / len(total_text)
        print(f"⚠️  POOR QUALITY TEXT - {valid_ratio:.1%} valid chars (< 40% threshold)")
        print("   This text would trigger OCR in production")
    else:
        print(f"✅ TEXT LOOKS GOOD - {len(total_text)} chars with acceptable quality")
        print("   This text should be usable for RAG")


if __name__ == "__main__":
    import asyncio

    if len(sys.argv) < 2:
        print("Usage: python inspect_pdf_extraction.py <path_to_pdf>")
        print("\nExample:")
        print("  python inspect_pdf_extraction.py /tmp/ClientProject_presentacion.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    asyncio.run(inspect_pdf(pdf_path))
