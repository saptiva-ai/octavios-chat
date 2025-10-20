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
from .extractors.pdf_raster_ocr import raster_pdf_then_ocr_pages

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

        # Special handling for PDFs: Detect image-only PDFs and apply OCR fallback
        if media_type == "pdf":
            # Heuristic: Try pypdf first to detect if PDF is searchable
            try:
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(file_bytes))
                total_pages = len(reader.pages)
                searchable_hits = 0
                temp_pages: List[PageContent] = []

                # Attempt to extract text from all pages
                for page_idx, page in enumerate(reader.pages, start=1):
                    try:
                        text = page.extract_text() or ""
                        text_stripped = text.strip()

                        if text_stripped:
                            searchable_hits += 1

                        # Store temporary pages (we'll use them if PDF is searchable)
                        temp_pages.append(
                            PageContent(
                                page=page_idx,
                                text_md=text_stripped or f"[Página {page_idx} sin texto extraíble]",
                                has_table=False,
                                has_images=False,
                            )
                        )

                    except Exception as page_exc:
                        logger.warning(
                            "pypdf extraction failed for page",
                            page=page_idx,
                            error=str(page_exc),
                        )
                        temp_pages.append(
                            PageContent(
                                page=page_idx,
                                text_md=f"[Página {page_idx} error pypdf: {page_exc}]",
                                has_table=False,
                                has_images=False,
                            )
                        )

                # Apply heuristic: < 10% of pages have text = image-only PDF
                threshold = max(1, int(0.1 * total_pages))

                if searchable_hits < threshold:
                    logger.info(
                        "Image-only PDF detected, activating raster + OCR fallback",
                        total_pages=total_pages,
                        searchable_hits=searchable_hits,
                        threshold=threshold,
                        file_path=str(file_path),
                    )

                    # Call OCR fallback
                    pages = await raster_pdf_then_ocr_pages(file_bytes)

                    logger.info(
                        "OCR fallback completed",
                        pages_extracted=len(pages),
                        total_chars=sum(len(p.text_md) for p in pages),
                        file_path=str(file_path),
                    )

                    return pages

                else:
                    # PDF is searchable, use pypdf results
                    logger.info(
                        "Searchable PDF detected, using pypdf extraction",
                        total_pages=total_pages,
                        searchable_hits=searchable_hits,
                        threshold=threshold,
                        file_path=str(file_path),
                    )
                    pages = temp_pages

                    logger.info(
                        "Text extraction successful (searchable PDF)",
                        media_type=media_type,
                        pages_extracted=len(pages),
                        total_chars=sum(len(p.text_md) for p in pages),
                        file_path=str(file_path),
                    )

                    return pages

            except ImportError:
                # pypdf not installed, fall back to extractor pattern
                logger.warning(
                    "pypdf not installed, falling back to extractor pattern",
                    file_path=str(file_path),
                )

            except Exception as exc:
                # pypdf heuristic failed, fall back to extractor pattern
                logger.warning(
                    "pypdf heuristic failed, falling back to extractor pattern",
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
