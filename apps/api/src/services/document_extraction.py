"""
Utilities for extracting text/tables from uploaded documents.

This module provides a high-level interface for document text extraction.
Uses pluggable extractors (pypdf+pytesseract or Saptiva) via factory pattern.

Configuration:
    EXTRACTOR_PROVIDER: "third_party" (default) | "saptiva"
    MAX_OCR_PAGES: Maximum pages to OCR for image-only PDFs (default: 30)
    OCR_RASTER_DPI: Rasterization DPI for OCR fallback (default: 180)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List

import structlog

from ..models.document import PageContent
from .extractors import get_text_extractor, ExtractionError, UnsupportedFormatError
from .extractors.pdf_raster_ocr import raster_pdf_then_ocr_pages, raster_single_page_and_ocr
from ..core.config import get_settings

logger = structlog.get_logger(__name__)


async def extract_text_from_file(file_path: Path, content_type: str) -> List[PageContent]:
    """
    Extract text from PDF or image files using pluggable extractor.

    This function routes to the appropriate extraction backend based on
    EXTRACTOR_PROVIDER environment variable:
        - third_party: pypdf + pytesseract (current default)
        - saptiva: Saptiva Native Tools API (future)

    Args:
        file_path: Path to document file on disk
        content_type: MIME type (e.g., "application/pdf", "image/png")

    Returns:
        List of PageContent objects with extracted text

        For PDFs: One PageContent per page
        For Images: Single PageContent with OCR text
        For Unsupported: Single PageContent with error message

    Example:
        pages = await extract_text_from_file(
            Path("/tmp/document.pdf"),
            "application/pdf"
        )
        for page in pages:
            print(f"Page {page.page}: {page.text_md[:100]}...")
    """
    pages: List[PageContent] = []

    try:
        # Determine media type from content_type
        if content_type == "application/pdf":
            media_type = "pdf"
        elif content_type in [
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/heic",
            "image/heif",
            "image/gif",
        ]:
            media_type = "image"
        else:
            # Unsupported format
            logger.warning(
                "Unsupported content type for extraction",
                content_type=content_type,
                file_path=str(file_path),
            )
            pages.append(
                PageContent(
                    page=1,
                    text_md=f"[Formato no soportado: {content_type}]",
                    has_table=False,
                )
            )
            return pages

        # Read file bytes
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Special handling for PDFs: Hybrid extraction (pypdf + selective OCR)
        if media_type == "pdf":
            # Hybrid approach: Try pypdf first, apply OCR to pages with insufficient text
            try:
                import fitz  # PyMuPDF for OCR fallback
                from pypdf import PdfReader

                settings = get_settings()
                MIN_CHARS_THRESHOLD = 50  # Páginas con < 50 caracteres se procesan con OCR

                reader = PdfReader(io.BytesIO(file_bytes))
                total_pages = len(reader.pages)
                temp_pages: List[PageContent] = []

                # Counters for telemetry
                pypdf_count = 0
                ocr_count = 0
                error_count = 0

                logger.info(
                    "Starting hybrid PDF extraction (pypdf + selective OCR)",
                    total_pages=total_pages,
                    min_chars_threshold=MIN_CHARS_THRESHOLD,
                    file_path=str(file_path),
                )

                # Open PDF with PyMuPDF for OCR fallback (if needed)
                fitz_doc = None
                try:
                    fitz_doc = fitz.open(stream=file_bytes, filetype="pdf")
                except Exception as fitz_exc:
                    logger.warning(
                        "PyMuPDF failed to open PDF, OCR fallback unavailable",
                        error=str(fitz_exc),
                        file_path=str(file_path),
                    )

                # Process each page with hybrid approach
                for page_idx, page in enumerate(reader.pages):
                    page_num = page_idx + 1

                    try:
                        # Step 1: Try pypdf extraction
                        text = page.extract_text() or ""
                        text_stripped = text.strip()

                        # Step 2: Determine if OCR is needed
                        needs_ocr = (
                            len(text_stripped) < MIN_CHARS_THRESHOLD
                            and fitz_doc is not None
                        )

                        if needs_ocr:
                            # Step 3: Apply OCR to this page
                            logger.debug(
                                "Applying OCR to page with insufficient text",
                                page=page_num,
                                pypdf_chars=len(text_stripped),
                                threshold=MIN_CHARS_THRESHOLD,
                            )

                            ocr_text = await raster_single_page_and_ocr(
                                doc=fitz_doc,
                                page_idx=page_idx,
                                dpi=settings.ocr_raster_dpi,
                            )

                            # Use OCR text if it's better than pypdf
                            if len(ocr_text.strip()) > len(text_stripped):
                                text_stripped = ocr_text.strip()
                                ocr_count += 1
                                logger.debug(
                                    "OCR text used for page",
                                    page=page_num,
                                    ocr_chars=len(text_stripped),
                                )
                            else:
                                pypdf_count += 1
                                logger.debug(
                                    "pypdf text retained (OCR did not improve)",
                                    page=page_num,
                                )
                        else:
                            pypdf_count += 1

                        # Store page content
                        temp_pages.append(
                            PageContent(
                                page=page_num,
                                text_md=text_stripped or f"[Página {page_num} sin texto extraíble]",
                                has_table=False,
                                has_images=False,
                            )
                        )

                    except Exception as page_exc:
                        error_count += 1
                        logger.warning(
                            "Page extraction failed",
                            page=page_num,
                            error=str(page_exc),
                        )
                        temp_pages.append(
                            PageContent(
                                page=page_num,
                                text_md=f"[Página {page_num} error: {page_exc}]",
                                has_table=False,
                                has_images=False,
                            )
                        )

                # Close PyMuPDF document
                if fitz_doc is not None:
                    fitz_doc.close()

                pages = temp_pages

                logger.info(
                    "Hybrid PDF extraction completed",
                    total_pages=total_pages,
                    pypdf_pages=pypdf_count,
                    ocr_pages=ocr_count,
                    error_pages=error_count,
                    total_chars=sum(len(p.text_md) for p in pages),
                    file_path=str(file_path),
                )

                return pages

            except ImportError:
                # pypdf or PyMuPDF not installed, fall back to extractor pattern
                logger.warning(
                    "pypdf or PyMuPDF not installed, falling back to extractor pattern",
                    file_path=str(file_path),
                )

            except Exception as exc:
                # Hybrid extraction failed, fall back to extractor pattern
                logger.warning(
                    "Hybrid extraction failed, falling back to extractor pattern",
                    error=str(exc),
                    file_path=str(file_path),
                )

        # Standard extraction path (for images and PDF fallback)
        extractor = get_text_extractor()

        logger.info(
            "Starting text extraction",
            media_type=media_type,
            content_type=content_type,
            file_path=str(file_path),
            file_size=len(file_bytes),
            extractor_type=type(extractor).__name__,
        )

        # Extract text using abstraction layer
        extracted_text = await extractor.extract_text(
            media_type=media_type,
            data=file_bytes,
            mime=content_type,
            filename=file_path.name,
        )

        # Convert extracted text to PageContent format
        if media_type == "pdf":
            # PDF: Split by double newlines (page separators from ThirdPartyExtractor)
            page_texts = extracted_text.split("\n\n")
            for page_num, page_text in enumerate(page_texts, start=1):
                text = page_text.strip()
                if not text:
                    text = f"[Página {page_num} sin texto extraíble]"

                pages.append(
                    PageContent(
                        page=page_num,
                        text_md=text,
                        has_table=False,
                    )
                )
        else:  # media_type == "image"
            # Image: Single page with OCR text
            pages.append(
                PageContent(
                    page=1,
                    text_md=extracted_text,
                    has_table=False,
                )
            )

        logger.info(
            "Text extraction successful",
            media_type=media_type,
            pages_extracted=len(pages),
            total_chars=sum(len(p.text_md) for p in pages),
            file_path=str(file_path),
        )

    except UnsupportedFormatError as exc:
        logger.warning(
            "Unsupported format for extraction",
            content_type=content_type,
            error=str(exc),
            file_path=str(file_path),
        )
        pages = [
            PageContent(
                page=1,
                text_md=f"[Formato no soportado: {content_type}]",
                has_table=False,
            )
        ]

    except ExtractionError as exc:
        logger.error(
            "Text extraction failed",
            error=str(exc),
            media_type=getattr(exc, "media_type", None),
            file_path=str(file_path),
            exc_info=True,
        )
        pages = _fallback_mock_pages()

    except Exception as exc:  # pragma: no cover - unexpected errors
        logger.error(
            "Unexpected extraction error",
            error=str(exc),
            file_path=str(file_path),
            exc_info=True,
        )
        pages = _fallback_mock_pages()

    return pages


def _fallback_mock_pages() -> List[PageContent]:
    return [
        PageContent(
            page=1,
            text_md="# Documento de Prueba\n\nEste es un documento de ejemplo (modo fallback).",
            has_table=False,
        )
    ]
