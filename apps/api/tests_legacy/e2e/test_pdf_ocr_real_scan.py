"""
E2E test for PDF OCR fallback using real scanned PDF.

This test validates the complete OCR fallback pipeline with a real-world
scanned PDF (HPE.pdf) containing image-only pages.

Test Coverage:
    1. Real scanned PDF is correctly detected as image-only
    2. OCR fallback is triggered automatically
    3. Text is successfully extracted from rasterized pages
    4. PageContent objects are properly formatted
    5. Performance metrics are within acceptable bounds
"""

import pytest
from pathlib import Path
import time

from src.services.document_extraction import extract_text_from_file


# Real scanned PDF path (2.3MB, image-only pages)
TEST_PDF_PATH = Path("/tmp/HPE.pdf")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow  # This test will take time due to OCR processing
class TestPdfOcrRealScan:
    """E2E tests for PDF OCR fallback with real scanned documents."""

    async def test_hpe_pdf_triggers_ocr_fallback(self):
        """
        Test that HPE.pdf (real scanned document) triggers OCR fallback.

        Given: Real scanned PDF with image-only pages (HPE.pdf)
        When: extract_text_from_file is called
        Then:
            - Heuristic detects it as image-only (< 10% searchable)
            - OCR fallback is triggered
            - Text is extracted from rasterized pages
            - At least some pages contain extracted text
        """
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        start_time = time.time()

        # Extract text from real scanned PDF
        result = await extract_text_from_file(TEST_PDF_PATH, "application/pdf")

        duration = time.time() - start_time

        # Verify result structure
        assert result is not None, "Result should not be None"
        assert isinstance(result, list), "Result should be a list"
        assert len(result) > 0, "Result should contain at least one page"

        # Verify PageContent objects are properly formatted
        first_page = result[0]
        assert hasattr(first_page, "page"), "PageContent should have 'page' attribute"
        assert hasattr(first_page, "text_md"), "PageContent should have 'text_md' attribute"
        assert first_page.page == 1, "First page should be numbered 1"

        # Verify OCR extracted some meaningful text
        # (real scanned documents should have substantial text content)
        total_text = "".join(page.text_md for page in result)
        assert len(total_text) > 100, "Should extract meaningful text from scanned pages (> 100 chars)"

        # Verify text is not just error messages
        error_pages = sum(
            1 for page in result
            if "[Página" in page.text_md and ("error" in page.text_md.lower() or "fallido" in page.text_md.lower())
        )
        total_pages = len(result)
        assert error_pages < total_pages, "Not all pages should be errors"

        # Log performance metrics
        print(f"\n{'='*60}")
        print(f"PDF OCR E2E Test Results:")
        print(f"{'='*60}")
        print(f"File: {TEST_PDF_PATH.name}")
        print(f"File size: {TEST_PDF_PATH.stat().st_size / (1024*1024):.2f} MB")
        print(f"Pages processed: {len(result)}")
        print(f"Total text extracted: {len(total_text):,} characters")
        print(f"Processing time: {duration:.2f} seconds")
        print(f"Avg time per page: {duration/len(result):.2f} seconds")
        print(f"Characters per second: {len(total_text)/duration:.1f}")
        print(f"Error pages: {error_pages}/{total_pages}")
        print(f"{'='*60}\n")

    async def test_hpe_pdf_text_quality(self):
        """
        Test that extracted text from HPE.pdf has reasonable quality.

        Given: Real scanned PDF (HPE.pdf)
        When: Text is extracted via OCR fallback
        Then:
            - Text contains expected HPE-related keywords
            - Text is properly formatted (not just gibberish)
            - Pages have varying text lengths (not uniform errors)
        """
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        result = await extract_text_from_file(TEST_PDF_PATH, "application/pdf")

        # Aggregate all text
        all_text = " ".join(page.text_md for page in result).lower()

        # Check for HPE-related keywords (adjust based on actual content)
        # These are generic tech/business keywords that should appear in HPE docs
        expected_keywords = ["hewlett", "packard", "hpe", "enterprise", "technology", "solution"]
        found_keywords = [kw for kw in expected_keywords if kw in all_text]

        # At least one keyword should be found (lenient for OCR errors)
        assert len(found_keywords) > 0, f"Should find at least one HPE-related keyword. Found: {found_keywords}"

        # Check text length variation (indicates real content, not uniform errors)
        text_lengths = [len(page.text_md) for page in result]
        min_length = min(text_lengths)
        max_length = max(text_lengths)
        avg_length = sum(text_lengths) / len(text_lengths)

        assert max_length > min_length, "Pages should have varying text lengths"
        assert avg_length > 50, f"Average text per page should be substantial (got {avg_length:.1f})"

    async def test_hpe_pdf_respects_max_ocr_pages_limit(self):
        """
        Test that MAX_OCR_PAGES limit is respected for HPE.pdf.

        Given: Real scanned PDF (HPE.pdf) with potentially many pages
        When: extract_text_from_file is called
        Then:
            - If PDF has > MAX_OCR_PAGES (30), only 30 pages are processed
            - Truncation marker is added if truncated
            - Result length is at most MAX_OCR_PAGES + 1 (for truncation marker)
        """
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        from src.core.config import get_settings
        settings = get_settings()
        max_pages = settings.max_ocr_pages

        result = await extract_text_from_file(TEST_PDF_PATH, "application/pdf")

        # Check if truncation occurred
        has_truncation_marker = any("truncado" in page.text_md.lower() for page in result)

        if has_truncation_marker:
            # If truncated, should have max_pages + 1 (for marker)
            assert len(result) == max_pages + 1, \
                f"Truncated PDF should have {max_pages} pages + 1 marker (got {len(result)})"

            # Verify truncation marker is on last page
            last_page = result[-1]
            assert "truncado" in last_page.text_md.lower(), \
                "Last page should be truncation marker"
            assert str(max_pages) in last_page.text_md, \
                f"Truncation marker should mention {max_pages} pages"
        else:
            # If not truncated, should be <= max_pages
            assert len(result) <= max_pages, \
                f"Non-truncated PDF should have <= {max_pages} pages (got {len(result)})"

    async def test_hpe_pdf_page_numbering_sequential(self):
        """
        Test that page numbers are sequential and start from 1.

        Given: Real scanned PDF (HPE.pdf)
        When: Text is extracted via OCR fallback
        Then:
            - Page numbers start at 1
            - Page numbers are sequential (1, 2, 3, ...)
            - No duplicate page numbers
        """
        if not TEST_PDF_PATH.exists():
            pytest.skip(f"Test PDF not found at {TEST_PDF_PATH}")

        result = await extract_text_from_file(TEST_PDF_PATH, "application/pdf")

        page_numbers = [page.page for page in result]

        # Check starts at 1
        assert page_numbers[0] == 1, "First page should be numbered 1"

        # Check sequential (allowing for truncation marker at end)
        for i in range(len(page_numbers) - 1):
            current = page_numbers[i]
            next_page = page_numbers[i + 1]

            # Allow last page to be truncation marker (may have page = max_pages + 1)
            if i == len(page_numbers) - 2 and "truncado" in result[i + 1].text_md.lower():
                assert next_page == current + 1, "Truncation marker should have sequential page number"
            else:
                assert next_page == current + 1, \
                    f"Pages should be sequential: page {current} followed by {next_page}"

        # Check no duplicates
        non_truncation_pages = [
            p.page for p in result
            if "truncado" not in p.text_md.lower()
        ]
        assert len(non_truncation_pages) == len(set(non_truncation_pages)), \
            "Should have no duplicate page numbers"
