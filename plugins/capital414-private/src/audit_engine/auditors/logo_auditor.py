"""
Logo auditor for Copiloto 414.

Validates logo presence, position, and size in documents:
- Template matching using OpenCV
- Required pages validation (cover, back cover)
- Size and similarity thresholds

Configuration:
    apps/api/config/compliance.yaml (logo section)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from uuid import uuid4

import structlog
import numpy as np

from ...schemas.audit_message import Finding, Location, Evidence, Severity

logger = structlog.get_logger(__name__)


# ============================================================================
# PDF to Image Conversion
# ============================================================================


def render_pdf_page_to_image(pdf_path: Path, page_num: int, dpi: int = 150) -> Optional[np.ndarray]:
    """
    Render a single PDF page to numpy array (grayscale image).

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (1-indexed)
        dpi: Resolution for rendering (default: 150)

    Returns:
        Grayscale image as numpy array, or None on failure

    Example:
        img = render_pdf_page_to_image(Path("/tmp/report.pdf"), page_num=1)
        if img is not None:
            print(f"Image shape: {img.shape}")
    """
    try:
        import fitz  # PyMuPDF
        import cv2

        with fitz.open(str(pdf_path)) as doc:
            if page_num < 1 or page_num > len(doc):
                logger.warning(
                    "Page number out of range",
                    page_num=page_num,
                    total_pages=len(doc),
                )
                return None

            page = doc[page_num - 1]  # Convert to 0-indexed

            # Render page to pixmap (image)
            zoom = dpi / 72.0  # 72 DPI is default
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Convert to numpy array (RGB)
            img_rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )

            # Convert to grayscale (OpenCV format)
            if pix.n == 4:  # RGBA
                img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGBA2GRAY)
            elif pix.n == 3:  # RGB
                img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
            else:
                img_gray = img_rgb[:, :, 0]  # Already grayscale

            return img_gray

    except ImportError:
        logger.error("PyMuPDF or OpenCV not installed")
        return None

    except Exception as exc:
        logger.error(
            "Page rendering failed",
            page_num=page_num,
            error=str(exc),
            exc_info=True,
        )
        return None


# ============================================================================
# Logo Template Matching
# ============================================================================


def match_logo_on_page(
    page_image: np.ndarray,
    template_image: np.ndarray,
    min_similarity: float = 0.75,
) -> Tuple[bool, float, Optional[Tuple[int, int, int, int]]]:
    """
    Detect logo on page using OpenCV template matching.

    Args:
        page_image: Grayscale page image (numpy array)
        template_image: Grayscale template image (logo)
        min_similarity: Minimum similarity threshold (0-1)

    Returns:
        (found, similarity, bbox) tuple:
        - found: True if logo detected above threshold
        - similarity: Match score (0-1)
        - bbox: (x, y, w, h) of best match, or None

    Example:
        found, score, bbox = match_logo_on_page(page_img, template_img, 0.75)
        if found:
            print(f"Logo found at {bbox} with score {score:.2f}")
    """
    try:
        import cv2

        # Template matching (normalized cross-correlation)
        result = cv2.matchTemplate(page_image, template_image, cv2.TM_CCOEFF_NORMED)

        # Find best match
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # max_val is similarity score (0-1)
        similarity = float(max_val)

        # Check if above threshold
        if similarity >= min_similarity:
            # Extract bounding box
            template_h, template_w = template_image.shape
            x, y = max_loc
            bbox = (x, y, template_w, template_h)

            logger.debug(
                "Logo match found",
                similarity=similarity,
                bbox=bbox,
            )

            return True, similarity, bbox
        else:
            logger.debug(
                "Logo not found (below threshold)",
                similarity=similarity,
                threshold=min_similarity,
            )
            return False, similarity, None

    except Exception as exc:
        logger.error("Logo matching failed", error=str(exc), exc_info=True)
        return False, 0.0, None


# ============================================================================
# Logo Area Validation
# ============================================================================


def is_logo_size_valid(bbox: Tuple[int, int, int, int], min_area: int) -> bool:
    """
    Check if logo bounding box meets minimum area requirement.

    Args:
        bbox: (x, y, width, height) tuple
        min_area: Minimum area in pixels²

    Returns:
        True if logo is large enough
    """
    _, _, width, height = bbox
    area = width * height
    return area >= min_area


# ============================================================================
# Main Audit Function
# ============================================================================


async def audit_logo(
    pdf_path: Path,
    config: Dict[str, Any],
    total_pages: int,
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit logo presence and compliance in document.

    Args:
        pdf_path: Path to PDF file
        config: Compliance configuration
        total_pages: Total number of pages in document

    Returns:
        (findings, summary) tuple

    Example:
        findings, summary = await audit_logo(pdf_path, config, total_pages=15)
        print(f"Logo violations: {len(findings)}")
    """
    findings: List[Finding] = []
    logo_config = config.get("logo", {})

    # Configuration
    template_path = logo_config.get("template_path", "assets/logo_template.png")
    min_similarity = logo_config.get("min_similarity", 0.75)
    min_area = logo_config.get("min_area", 5000)
    required_pages_config = logo_config.get("required_pages", ["first", "last"])
    missing_severity = logo_config.get("missing_severity", "high")

    logger.info(
        "Starting logo audit",
        pdf_path=str(pdf_path),
        template_path=template_path,
        min_similarity=min_similarity,
        min_area=min_area,
        required_pages=required_pages_config,
    )

    # ========================================================================
    # 1. Load template image
    # ========================================================================

    try:
        import cv2

        # Try multiple paths for template
        template_paths = [
            Path(__file__).parent.parent.parent / template_path,
            Path(template_path),
            Path(f"apps/api/{template_path}"),
        ]

        template_img = None
        for tpl_path in template_paths:
            if tpl_path.exists():
                template_img = cv2.imread(str(tpl_path), cv2.IMREAD_GRAYSCALE)
                if template_img is not None:
                    logger.info("Logo template loaded", path=str(tpl_path))
                    break

        if template_img is None:
            logger.warning(
                "Logo template not found, skipping logo audit",
                searched_paths=[str(p) for p in template_paths],
            )
            return [], {"logo_template_missing": True, "checks_performed": 0}

    except ImportError:
        logger.error("OpenCV not installed, cannot perform logo audit")
        return [], {"opencv_missing": True}

    # ========================================================================
    # 2. Determine required pages
    # ========================================================================

    required_pages: List[int] = []
    for page_spec in required_pages_config:
        if page_spec == "first":
            required_pages.append(1)
        elif page_spec == "last":
            required_pages.append(total_pages)
        elif isinstance(page_spec, int):
            required_pages.append(page_spec)
        else:
            logger.warning("Invalid page spec in logo config", page_spec=page_spec)

    # ========================================================================
    # 3. Check each required page
    # ========================================================================

    checks_performed = 0
    logos_found = 0

    for page_num in required_pages:
        # Render page to image
        page_img = render_pdf_page_to_image(pdf_path, page_num, dpi=150)

        if page_img is None:
            logger.warning("Failed to render page", page_num=page_num)
            continue

        checks_performed += 1

        # Match logo
        found, similarity, bbox = match_logo_on_page(
            page_img,
            template_img,
            min_similarity,
        )

        if not found:
            # Logo missing or below similarity threshold
            finding_id = f"logo-missing-{page_num}-{uuid4().hex[:8]}"

            findings.append(
                Finding(
                    id=finding_id,
                    category="logo",
                    rule="logo_presence",
                    issue=f"Logo ausente o no detectado en página {page_num} (requerida)",
                    severity=missing_severity,
                    location=Location(
                        page=page_num,
                        bbox=None,
                        fragment_id=None,
                        text_snippet=None,
                    ),
                    suggestion=(
                        f"Agregar logo de 414 Capital en página {page_num}. "
                        f"Debe tener similitud >= {min_similarity:.0%}"
                    ),
                    evidence=[
                        Evidence(
                            kind="metric",
                            data={
                                "similarity_found": similarity,
                                "threshold": min_similarity,
                            },
                        )
                    ],
                )
            )

        elif bbox is not None:
            # Logo found, check size
            if not is_logo_size_valid(bbox, min_area):
                finding_id = f"logo-size-{page_num}-{uuid4().hex[:8]}"

                x, y, w, h = bbox
                area = w * h

                findings.append(
                    Finding(
                        id=finding_id,
                        category="logo",
                        rule="logo_size",
                        issue=f"Logo muy pequeño en página {page_num} ({area} px² < {min_area} px²)",
                        severity="medium",
                        location=Location(
                            page=page_num,
                            bbox=[float(x), float(y), float(x + w), float(y + h)],
                            fragment_id=None,
                            text_snippet=None,
                        ),
                        suggestion=f"Aumentar tamaño del logo a mínimo {min_area} px²",
                        evidence=[
                            Evidence(
                                kind="metric",
                                data={
                                    "area_found": area,
                                    "min_area": min_area,
                                    "bbox": bbox,
                                },
                            )
                        ],
                    )
                )
            else:
                # Logo OK
                logos_found += 1

    # ========================================================================
    # Summary
    # ========================================================================

    summary = {
        "checks_performed": checks_performed,
        "logos_found": logos_found,
        "required_pages": required_pages,
        "violations": len(findings),
    }

    logger.info(
        "Logo audit completed",
        checks_performed=checks_performed,
        logos_found=logos_found,
        violations=len(findings),
    )

    return findings, summary
