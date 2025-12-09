"""
Document text extraction service.

Supports PDF and image files with OCR fallback.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import structlog
from pypdf import PdfReader

from ..config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def _is_text_quality_sufficient(text: str, min_quality_ratio: float = 0.4) -> bool:
    """
    Validate if extracted text has sufficient quality.

    Prevents using corrupted text from scanned PDFs with hidden text layers.

    Args:
        text: Extracted text to validate
        min_quality_ratio: Minimum ratio of valid characters

    Returns:
        True if text quality is sufficient
    """
    if not text or len(text.strip()) == 0:
        return False

    text_clean = text.strip()

    # Check 1: Character quality ratio
    valid_chars = sum(1 for c in text_clean if c.isalnum() or c.isspace())
    total_chars = len(text_clean)
    quality_ratio = valid_chars / total_chars if total_chars > 0 else 0

    if quality_ratio < min_quality_ratio:
        return False

    # Check 2: Must have actual words (2+ consecutive letters)
    words = re.findall(r'[a-zA-ZáéíóúÁÉÍÓÚñÑ]{2,}', text_clean)
    if len(words) < 5:
        return False

    # Check 3: Cannot be mostly special characters
    special_chars = total_chars - valid_chars
    special_ratio = special_chars / total_chars if total_chars > 0 else 0
    if special_ratio > 0.8:
        return False

    return True


def extract_text_from_pdf(file_path: Path) -> tuple[str, int]:
    """
    Extract text from a PDF file.

    Uses pypdf for text extraction with OCR fallback for scanned PDFs.

    Args:
        file_path: Path to PDF file

    Returns:
        Tuple of (extracted_text, page_count)
    """
    try:
        reader = PdfReader(str(file_path))
        pages_text = []
        total_pages = len(reader.pages)

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""

                # Validate text quality
                if _is_text_quality_sufficient(text):
                    pages_text.append(text)
                else:
                    # Try OCR fallback for this page
                    ocr_text = _ocr_pdf_page(file_path, i)
                    if ocr_text:
                        pages_text.append(ocr_text)
                    else:
                        pages_text.append(f"[Page {i+1}: No text extracted]")

            except Exception as e:
                logger.warning(f"Failed to extract page {i+1}", error=str(e))
                pages_text.append(f"[Page {i+1}: Extraction failed]")

        full_text = "\n\n".join(pages_text)

        logger.info(
            "PDF text extracted",
            file=str(file_path),
            pages=total_pages,
            text_length=len(full_text),
        )

        return full_text, total_pages

    except Exception as e:
        logger.error("Failed to extract PDF text", file=str(file_path), error=str(e))
        raise


def _ocr_pdf_page(file_path: Path, page_num: int) -> Optional[str]:
    """
    OCR a single PDF page using tesseract.

    Args:
        file_path: Path to PDF file
        page_num: Zero-indexed page number

    Returns:
        Extracted text or None if OCR fails
    """
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
        import io

        doc = fitz.open(str(file_path))
        page = doc[page_num]

        # Render page to image
        dpi = settings.ocr_raster_dpi
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL Image
        img = Image.open(io.BytesIO(pix.tobytes("png")))

        # OCR
        text = pytesseract.image_to_string(img, lang="spa+eng")

        doc.close()

        if _is_text_quality_sufficient(text):
            return text

        return None

    except ImportError:
        logger.warning("PyMuPDF or pytesseract not available for OCR")
        return None
    except Exception as e:
        logger.warning(f"OCR failed for page {page_num}", error=str(e))
        return None


def extract_text_from_image(file_path: Path) -> str:
    """
    Extract text from an image using OCR.

    Args:
        file_path: Path to image file

    Returns:
        Extracted text
    """
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang="spa+eng")

        logger.info(
            "Image text extracted",
            file=str(file_path),
            text_length=len(text),
        )

        return text

    except ImportError:
        logger.error("pytesseract not available")
        return "[OCR not available]"
    except Exception as e:
        logger.error("Failed to extract image text", file=str(file_path), error=str(e))
        raise


async def extract_text_from_file(
    file_path: Path,
    content_type: str,
) -> tuple[str, Optional[int]]:
    """
    Extract text from a file based on its content type.

    Args:
        file_path: Path to the file
        content_type: MIME type of the file

    Returns:
        Tuple of (extracted_text, page_count or None for images)
    """
    if content_type == "application/pdf":
        text, pages = extract_text_from_pdf(file_path)
        return text, pages

    elif content_type.startswith("image/"):
        text = extract_text_from_image(file_path)
        return text, None

    else:
        logger.warning(f"Unsupported content type for extraction: {content_type}")
        return f"[Unsupported format: {content_type}]", None
