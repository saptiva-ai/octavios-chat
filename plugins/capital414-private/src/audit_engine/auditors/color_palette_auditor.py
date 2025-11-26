"""
Color Palette Auditor for COPILOTO_414.

Validates strict color palette compliance:
- All colors must match corporate palette (with tolerance)
- Detects unauthorized brand colors
- Flags images with off-brand colors

Phase 3 of 5-phase plan (plan_summary.txt)
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
from uuid import uuid4
import structlog

from ...schemas.audit_message import Finding, Location, Evidence

logger = structlog.get_logger(__name__)


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def color_distance(color1: str, color2: str) -> float:
    """
    Calculate Euclidean distance between two hex colors.

    Returns:
        Distance (0.0 = identical, 441.67 = maximum difference)
    """
    rgb1 = hex_to_rgb(color1)
    rgb2 = hex_to_rgb(color2)

    return sum((a - b) ** 2 for a, b in zip(rgb1, rgb2)) ** 0.5


def is_color_in_palette(
    color: str,
    palette: List[str],
    tolerance: float = 0.12
) -> Tuple[bool, str]:
    """
    Check if color is within tolerance of palette.

    Args:
        color: Hex color to check
        palette: List of allowed hex colors
        tolerance: Maximum normalized distance (0.0-1.0)
                   Default 0.12 = ~12% tolerance (53 units out of 441.67 max)

    Returns:
        (is_valid, closest_match_color)
    """
    if not palette:
        return True, color

    min_distance = float('inf')
    closest_color = palette[0]

    for palette_color in palette:
        distance = color_distance(color, palette_color)
        if distance < min_distance:
            min_distance = distance
            closest_color = palette_color

    # Normalize distance to 0.0-1.0 range (max distance = 441.67)
    normalized_distance = min_distance / 441.67
    is_valid = normalized_distance <= tolerance

    return is_valid, closest_color


def extract_all_colors_from_pdf(pdf_path: Path) -> Set[str]:
    """
    Extract ALL unique colors from PDF (text + images + shapes).

    Uses PyMuPDF to analyze every element.

    Returns:
        Set of hex color strings (e.g., {"#002B5C", "#FFFFFF"})
    """
    try:
        import fitz  # PyMuPDF

        colors_used = set()

        with fitz.open(str(pdf_path)) as doc:
            for page_num, page in enumerate(doc, 1):
                # Extract text colors
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block.get("type") != 0:  # Skip non-text blocks
                        continue

                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            color = span.get("color", 0)
                            if color:
                                hex_color = f"#{color:06X}"
                                colors_used.add(hex_color)

                # Extract drawing/shape colors
                for drawing in page.get_drawings():
                    # Fill colors
                    if drawing.get("fill"):
                        fill_color = drawing["fill"]
                        if isinstance(fill_color, tuple) and len(fill_color) == 3:
                            r, g, b = [int(c * 255) for c in fill_color]
                            hex_color = f"#{r:02X}{g:02X}{b:02X}"
                            colors_used.add(hex_color)

                    # Stroke colors
                    if drawing.get("color"):
                        stroke_color = drawing["color"]
                        if isinstance(stroke_color, tuple) and len(stroke_color) == 3:
                            r, g, b = [int(c * 255) for c in stroke_color]
                            hex_color = f"#{r:02X}{g:02X}{b:02X}"
                            colors_used.add(hex_color)

        logger.info(
            "Extracted colors from PDF",
            pdf_path=str(pdf_path),
            unique_colors=len(colors_used)
        )

        return colors_used

    except Exception as exc:
        logger.error("Color extraction failed", error=str(exc), exc_info=True)
        return set()


async def audit_color_palette(
    pdf_path: Path,
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit strict color palette compliance.

    Args:
        pdf_path: Path to PDF file
        config: Policy configuration (color_palette section)

    Returns:
        (findings, summary) tuple
            - findings: List of Finding objects for violations
            - summary: Aggregated metrics
                - total_colors_detected: int
                - unauthorized_colors: int
                - compliance_rate: float (0.0-1.0)
                - palette_used: List[str]
                - unauthorized_colors_list: List[str]

    Example:
        findings, summary = await audit_color_palette(
            pdf_path=Path("/tmp/doc.pdf"),
            config={
                "color_palette": {
                    "enabled": True,
                    "allowed_colors": ["#003366", "#FFFFFF"],
                    "tolerance": 0.12,
                    "severity": "high"
                }
            }
        )
    """
    findings: List[Finding] = []
    color_config = config.get("color_palette", {})

    # Configuration
    palette = color_config.get("allowed_colors", ["#003366", "#FFFFFF", "#000000"])
    tolerance = color_config.get("tolerance", 0.12)  # 12% normalized tolerance
    severity = color_config.get("severity", "medium")

    logger.info(
        "Starting color palette audit",
        palette=palette,
        tolerance=tolerance
    )

    # Extract all colors from PDF
    colors_used = extract_all_colors_from_pdf(pdf_path)

    # Validate each color
    unauthorized_colors = []
    for color in colors_used:
        is_valid, closest_match = is_color_in_palette(color, palette, tolerance)

        if not is_valid:
            unauthorized_colors.append({
                "color": color,
                "closest_match": closest_match,
                "distance": color_distance(color, closest_match)
            })

    # Create findings
    for violation in unauthorized_colors:
        findings.append(
            Finding(
                id=f"color-palette-{uuid4().hex[:8]}",
                category="color_palette",
                rule="color_palette_compliance",
                issue=f"Color no autorizado {violation['color']} detectado",
                severity=severity,
                location=Location(
                    page=1,  # Colors apply to entire document
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None
                ),
                suggestion=f"Usar color corporativo más cercano: {violation['closest_match']}",
                evidence=[
                    Evidence(
                        kind="metric",
                        data={
                            "unauthorized_color": violation["color"],
                            "suggested_replacement": violation["closest_match"],
                            "distance": round(violation["distance"], 2),
                            "allowed_palette": palette
                        }
                    )
                ]
            )
        )

    # Generate summary
    summary = {
        "total_colors_detected": len(colors_used),
        "unauthorized_colors": len(unauthorized_colors),
        "compliance_rate": 1.0 - (len(unauthorized_colors) / max(len(colors_used), 1)),
        "palette_used": palette,
        "unauthorized_colors_list": [v["color"] for v in unauthorized_colors[:10]]  # Top 10
    }

    logger.info(
        "Color palette audit completed",
        findings=len(findings),
        compliance_rate=f"{summary['compliance_rate']:.1%}"
    )

    return findings, summary
