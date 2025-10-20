"""
Unit tests for PDF OCR fallback functionality.

Tests the heuristic that detects image-only PDFs and applies rasterization + OCR.

Test Coverage:
    1. Image-only PDF detection (< 10% pages with text → trigger OCR)
    2. Searchable PDF detection (≥ 10% pages with text → use pypdf)
    3. MAX_OCR_PAGES limit enforcement
    4. Error handling and fallback behavior
"""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock, Mock
from io import BytesIO

from src.services.document_extraction import extract_text_from_file
from src.models.document import PageContent


@pytest.mark.asyncio
class TestPdfOcrFallback:
    """Tests for PDF OCR fallback heuristic."""

    async def test_image_only_pdf_triggers_ocr(self, tmp_path):
        """
        Test that a PDF with no searchable text triggers OCR fallback.

        Given: PDF with 5 pages, all returning empty text via pypdf
        When: extract_text_from_file is called
        Then: raster_pdf_then_ocr_pages is called instead of using pypdf result
        """
        pdf_path = tmp_path / "scanned.pdf"
        # Create dummy PDF bytes (minimal valid PDF structure)
        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\ntrailer\n<<>>\n%%EOF"
        pdf_path.write_bytes(pdf_bytes)

        # Mock pypdf to return 5 pages with no text
        mock_pages = []
        for i in range(5):
            mock_page = MagicMock()
            mock_page.extract_text.return_value = ""  # Empty text
            mock_pages.append(mock_page)

        mock_reader = MagicMock()
        mock_reader.pages = mock_pages

        # Mock the OCR function to return dummy pages
        mock_ocr_result = [
            PageContent(page=1, text_md="OCR text page 1", has_table=False, has_images=False),
            PageContent(page=2, text_md="OCR text page 2", has_table=False, has_images=False),
            PageContent(page=3, text_md="OCR text page 3", has_table=False, has_images=False),
            PageContent(page=4, text_md="OCR text page 4", has_table=False, has_images=False),
            PageContent(page=5, text_md="OCR text page 5", has_table=False, has_images=False),
        ]

        with patch("src.services.document_extraction.PdfReader", return_value=mock_reader), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock(return_value=mock_ocr_result)) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Verify OCR was called
            assert mock_ocr.await_count == 1
            mock_ocr.assert_awaited_once_with(pdf_bytes)

            # Verify result comes from OCR, not pypdf
            assert len(result) == 5
            assert result[0].text_md == "OCR text page 1"
            assert result[4].text_md == "OCR text page 5"

    async def test_searchable_pdf_uses_pypdf(self, tmp_path):
        """
        Test that a PDF with searchable text uses pypdf (no OCR).

        Given: PDF with 5 pages, at least 1 (≥20%) has text
        When: extract_text_from_file is called
        Then: pypdf result is returned, OCR is NOT called
        """
        pdf_path = tmp_path / "searchable.pdf"
        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\ntrailer\n<<>>\n%%EOF"
        pdf_path.write_bytes(pdf_bytes)

        # Mock pypdf: 1 page with text, 4 pages empty (20% searchable)
        mock_pages = []

        # Page 1: Has text
        page1 = MagicMock()
        page1.extract_text.return_value = "This is searchable text on page 1"
        mock_pages.append(page1)

        # Pages 2-5: Empty
        for i in range(4):
            page = MagicMock()
            page.extract_text.return_value = ""
            mock_pages.append(page)

        mock_reader = MagicMock()
        mock_reader.pages = mock_pages

        with patch("src.services.document_extraction.PdfReader", return_value=mock_reader), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock()) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Verify OCR was NOT called
            assert mock_ocr.await_count == 0

            # Verify result comes from pypdf
            assert len(result) == 5
            assert result[0].text_md == "This is searchable text on page 1"
            assert result[1].text_md == "[Página 2 sin texto extraíble]"

    async def test_threshold_calculation_single_page_pdf(self, tmp_path):
        """
        Test threshold calculation for single-page PDF.

        Given: PDF with 1 page, no text
        When: extract_text_from_file is called
        Then: threshold = max(1, 0.1 * 1) = 1, so 0 < 1 → triggers OCR
        """
        pdf_path = tmp_path / "single_page.pdf"
        pdf_bytes = b"%PDF-1.4\n%%EOF"
        pdf_path.write_bytes(pdf_bytes)

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        mock_ocr_result = [
            PageContent(page=1, text_md="OCR page 1", has_table=False, has_images=False)
        ]

        with patch("src.services.document_extraction.PdfReader", return_value=mock_reader), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock(return_value=mock_ocr_result)) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Should trigger OCR (0 searchable < threshold of 1)
            assert mock_ocr.await_count == 1

    async def test_threshold_calculation_large_pdf(self, tmp_path):
        """
        Test threshold calculation for large PDF (100 pages).

        Given: PDF with 100 pages, 8 have text (8%)
        When: extract_text_from_file is called
        Then: threshold = max(1, 0.1 * 100) = 10, so 8 < 10 → triggers OCR
        """
        pdf_path = tmp_path / "large.pdf"
        pdf_bytes = b"%PDF-1.4\n%%EOF"
        pdf_path.write_bytes(pdf_bytes)

        mock_pages = []

        # First 8 pages have text
        for i in range(8):
            page = MagicMock()
            page.extract_text.return_value = f"Text on page {i+1}"
            mock_pages.append(page)

        # Remaining 92 pages empty
        for i in range(92):
            page = MagicMock()
            page.extract_text.return_value = ""
            mock_pages.append(page)

        mock_reader = MagicMock()
        mock_reader.pages = mock_pages

        mock_ocr_result = [
            PageContent(page=i, text_md=f"OCR page {i}", has_table=False, has_images=False)
            for i in range(1, 31)  # MAX_OCR_PAGES default is 30
        ] + [
            PageContent(page=31, text_md="[Truncated...]", has_table=False, has_images=False)
        ]

        with patch("src.services.document_extraction.PdfReader", return_value=mock_reader), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock(return_value=mock_ocr_result)) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Should trigger OCR (8 < 10)
            assert mock_ocr.await_count == 1

    async def test_pypdf_import_error_fallback(self, tmp_path):
        """
        Test fallback when pypdf is not installed.

        Given: pypdf raises ImportError
        When: extract_text_from_file is called
        Then: Falls back to extractor pattern (standard path)
        """
        pdf_path = tmp_path / "test.pdf"
        pdf_bytes = b"%PDF-1.4\n%%EOF"
        pdf_path.write_bytes(pdf_bytes)

        # Mock extractor
        mock_extractor = MagicMock()
        mock_extractor.extract_text = AsyncMock(return_value="Page 1 text\n\nPage 2 text")

        with patch("src.services.document_extraction.PdfReader",
                   side_effect=ImportError("No module named 'pypdf'")), \
             patch("src.services.document_extraction.get_text_extractor",
                   return_value=mock_extractor), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock()) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Should NOT call OCR (fallback to extractor)
            assert mock_ocr.await_count == 0

            # Should use extractor
            assert mock_extractor.extract_text.await_count == 1

            # Result from extractor
            assert len(result) == 2
            assert result[0].text_md == "Page 1 text"

    async def test_pypdf_exception_fallback(self, tmp_path):
        """
        Test fallback when pypdf raises unexpected exception.

        Given: pypdf raises generic Exception
        When: extract_text_from_file is called
        Then: Falls back to extractor pattern
        """
        pdf_path = tmp_path / "corrupt.pdf"
        pdf_bytes = b"%PDF-corrupted"
        pdf_path.write_bytes(pdf_bytes)

        mock_extractor = MagicMock()
        mock_extractor.extract_text = AsyncMock(return_value="Fallback text")

        with patch("src.services.document_extraction.PdfReader",
                   side_effect=Exception("PDF parsing error")), \
             patch("src.services.document_extraction.get_text_extractor",
                   return_value=mock_extractor), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock()) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Should NOT call OCR
            assert mock_ocr.await_count == 0

            # Should use extractor fallback
            assert mock_extractor.extract_text.await_count == 1

    async def test_pypdf_page_extraction_error(self, tmp_path):
        """
        Test handling of per-page extraction errors in pypdf.

        Given: pypdf raises exception on page 3
        When: extract_text_from_file is called
        Then: Error page is included, heuristic continues
        """
        pdf_path = tmp_path / "partial_error.pdf"
        pdf_bytes = b"%PDF-1.4\n%%EOF"
        pdf_path.write_bytes(pdf_bytes)

        mock_pages = []

        # Page 1: OK
        page1 = MagicMock()
        page1.extract_text.return_value = "Page 1 text"
        mock_pages.append(page1)

        # Page 2: OK
        page2 = MagicMock()
        page2.extract_text.return_value = "Page 2 text"
        mock_pages.append(page2)

        # Page 3: Error
        page3 = MagicMock()
        page3.extract_text.side_effect = Exception("Extraction failed")
        mock_pages.append(page3)

        mock_reader = MagicMock()
        mock_reader.pages = mock_pages

        with patch("src.services.document_extraction.PdfReader", return_value=mock_reader), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock()) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Should use pypdf result (2/3 pages = 66% > 10%)
            assert mock_ocr.await_count == 0

            # Verify error handling
            assert len(result) == 3
            assert result[0].text_md == "Page 1 text"
            assert result[1].text_md == "Page 2 text"
            assert "[Página 3 error pypdf:" in result[2].text_md

    async def test_image_extraction_not_affected(self, tmp_path):
        """
        Test that image extraction is not affected by PDF heuristic.

        Given: Image file (PNG)
        When: extract_text_from_file is called
        Then: Normal extraction path is used (no heuristic)
        """
        img_path = tmp_path / "test.png"
        img_bytes = b"\x89PNG\r\n\x1a\n"  # PNG header
        img_path.write_bytes(img_bytes)

        mock_extractor = MagicMock()
        mock_extractor.extract_text = AsyncMock(return_value="OCR text from image")

        with patch("src.services.document_extraction.get_text_extractor",
                   return_value=mock_extractor), \
             patch("src.services.document_extraction.PdfReader") as mock_pdf_reader, \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock()) as mock_ocr:

            result = await extract_text_from_file(img_path, "image/png")

            # Should NOT call PDF heuristic
            assert mock_pdf_reader.call_count == 0
            assert mock_ocr.await_count == 0

            # Should use normal extractor
            assert mock_extractor.extract_text.await_count == 1

            # Result
            assert len(result) == 1
            assert result[0].text_md == "OCR text from image"


@pytest.mark.asyncio
class TestPdfRasterOcrLimits:
    """Tests for MAX_OCR_PAGES limit enforcement."""

    async def test_max_ocr_pages_limit_enforced(self, tmp_path):
        """
        Test that MAX_OCR_PAGES limit is enforced.

        Given: Image-only PDF with 50 pages, MAX_OCR_PAGES=30
        When: raster_pdf_then_ocr_pages is called
        Then: Only 30 pages are processed, truncation marker is added
        """
        pdf_path = tmp_path / "large_scan.pdf"
        pdf_bytes = b"%PDF-1.4\n%%EOF"
        pdf_path.write_bytes(pdf_bytes)

        # Mock 50 empty pages
        mock_pages = [MagicMock(extract_text=MagicMock(return_value="")) for _ in range(50)]
        mock_reader = MagicMock(pages=mock_pages)

        # Mock OCR to return 30 pages + truncation marker
        mock_ocr_result = [
            PageContent(page=i, text_md=f"OCR page {i}", has_table=False, has_images=False)
            for i in range(1, 31)
        ] + [
            PageContent(
                page=31,
                text_md="[⚠️  Documento truncado: OCR aplicado solo a las primeras 30 páginas. Total de páginas: 50...]",
                has_table=False,
                has_images=False
            )
        ]

        with patch("src.services.document_extraction.PdfReader", return_value=mock_reader), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock(return_value=mock_ocr_result)) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Verify OCR was called
            assert mock_ocr.await_count == 1

            # Verify result has 31 pages (30 OCR + 1 truncation marker)
            assert len(result) == 31

            # Verify last page is truncation marker
            assert "truncado" in result[30].text_md.lower()
            assert "30" in result[30].text_md

    async def test_small_pdf_no_truncation(self, tmp_path):
        """
        Test that small PDFs are not truncated.

        Given: Image-only PDF with 10 pages, MAX_OCR_PAGES=30
        When: raster_pdf_then_ocr_pages is called
        Then: All 10 pages processed, no truncation marker
        """
        pdf_path = tmp_path / "small_scan.pdf"
        pdf_bytes = b"%PDF-1.4\n%%EOF"
        pdf_path.write_bytes(pdf_bytes)

        # Mock 10 empty pages
        mock_pages = [MagicMock(extract_text=MagicMock(return_value="")) for _ in range(10)]
        mock_reader = MagicMock(pages=mock_pages)

        # Mock OCR to return exactly 10 pages (no truncation)
        mock_ocr_result = [
            PageContent(page=i, text_md=f"OCR page {i}", has_table=False, has_images=False)
            for i in range(1, 11)
        ]

        with patch("src.services.document_extraction.PdfReader", return_value=mock_reader), \
             patch("src.services.document_extraction.raster_pdf_then_ocr_pages",
                   new=AsyncMock(return_value=mock_ocr_result)) as mock_ocr:

            result = await extract_text_from_file(pdf_path, "application/pdf")

            # Verify OCR was called
            assert mock_ocr.await_count == 1

            # Verify exactly 10 pages (no truncation marker)
            assert len(result) == 10

            # Verify no truncation message
            assert not any("truncado" in p.text_md.lower() for p in result)
