"""
Format auditor for Copiloto 414.

Validates document formatting against style guidelines:
- Number formatting (decimal/thousands separators)
- Font whitelist and size ranges
- Color palette compliance (brand colors)

Configuration:
    apps/api/config/compliance.yaml (format section)
"""

from __future__ import annotations

import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from uuid import uuid4

import structlog

from ...schemas.models import PageFragment
from ...schemas.audit_message import Finding, Location, Evidence, Severity

logger = structlog.get_logger(__name__)


# ============================================================================
# Numeric Format Validation
# ============================================================================


NUMERIC_TOKEN_RE = re.compile(
    r"(?<![\w])[-+]?(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d+)?(?![\w])"
)


def _is_valid_number(
    token: str,
    thousand_sep: str,
    decimal_sep: str,
    min_decimals: int,
    max_decimals: int,
) -> bool:
    """
    Validate that a numeric token follows corporate formatting rules.
    """
    if not token:
        return True

    # Remove leading sign
    if token[0] in "+-":
        token = token[1:]

    if thousand_sep == decimal_sep:
        return False

    parts = token.split(decimal_sep)
    if len(parts) > 2:
        return False

    whole = parts[0]
    decimals = parts[1] if len(parts) == 2 else ""

    # Validate thousands grouping
    if thousand_sep in whole:
        chunks = whole.split(thousand_sep)
        if len(chunks[0]) > 3:
            return False
        if any(len(chunk) != 3 for chunk in chunks[1:]):
            return False

    # Ensure no wrong separators remain
    wrong_sep = "," if thousand_sep == "." else "."
    if wrong_sep in whole.replace(thousand_sep, ""):
        return False

    # Decimal length checks
    if decimals:
        if not (min_decimals <= len(decimals) <= max_decimals):
            return False
        if thousand_sep in decimals:
            return False
    else:
        if min_decimals > 0:
            return False

    return True


async def audit_numeric_format(
    fragments: List[PageFragment],
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit numeric formatting across document fragments.
    """
    enabled = config.get("enabled", True)
    if not enabled:
        return [], {
            "enabled": False,
            "checked": 0,
            "invalid": 0,
            "compliance_rate": 1.0,
        }

    style = (config.get("style") or "EU").upper()

    style_defaults = {
        "EU": {"thousand": ".", "decimal": ",", "min_dec": 2, "max_dec": 2},
        "US": {"thousand": ",", "decimal": ".", "min_dec": 2, "max_dec": 2},
        "MX": {"thousand": ",", "decimal": ".", "min_dec": 2, "max_dec": 2},
    }
    defaults = style_defaults.get(style, style_defaults["EU"])

    thousand_sep = config.get("thousand_sep", defaults["thousand"])
    decimal_sep = config.get("decimal_sep", defaults["decimal"])
    min_decimals = config.get("min_decimals", 2)
    max_decimals = config.get("max_decimals", 2)
    severity = config.get("severity", "high")

    findings: List[Finding] = []
    checked = invalid = 0

    for frag in fragments:
        text = frag.text or ""
        for match in NUMERIC_TOKEN_RE.finditer(text):
            token = match.group(0)
            checked += 1

            if _is_valid_number(
                token,
                thousand_sep=thousand_sep,
                decimal_sep=decimal_sep,
                min_decimals=min_decimals,
                max_decimals=max_decimals,
            ):
                continue

            invalid += 1
            snippet_start = max(0, match.start() - 20)
            snippet_end = min(len(text), match.end() + 20)
            snippet = text[snippet_start:snippet_end].strip()

            findings.append(
                Finding(
                    id=f"numfmt-{frag.fragment_id}-{match.start()}",
                    category="format",
                    rule="numeric_format",
                    issue=f"Número con formato no permitido: «{token}»",
                    severity=severity,
                    location=Location(
                        page=frag.page,
                        bbox=frag.bbox,
                        fragment_id=frag.fragment_id,
                        text_snippet=snippet,
                    ),
                    suggestion=(
                        f"Usar separadores {thousand_sep} para miles y {decimal_sep} "
                        f"para decimales; {min_decimals}–{max_decimals} decimales."
                    ),
                    evidence=[
                        Evidence(
                            kind="rule",
                            data={
                                "found": token,
                                "style": style,
                                "thousand_sep": thousand_sep,
                                "decimal_sep": decimal_sep,
                                "min_decimals": min_decimals,
                                "max_decimals": max_decimals,
                            },
                        )
                    ],
                )
            )

    compliance_rate = 1.0 if checked == 0 else 1 - (invalid / checked)

    summary = {
        "enabled": True,
        "checked": checked,
        "invalid": invalid,
        "compliance_rate": round(compliance_rate, 4),
        "style": style,
        "thousand_sep": thousand_sep,
        "decimal_sep": decimal_sep,
        "min_decimals": min_decimals,
        "max_decimals": max_decimals,
    }

    return findings, summary


# ============================================================================
# Font and Style Extraction (PyMuPDF)
# ============================================================================


def extract_fonts_and_colors(pdf_path: Path) -> Dict[str, Any]:
    """
    Extract font names, sizes, and colors from PDF using PyMuPDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Dict with:
        - fonts: Set of (font_name, font_size) tuples
        - colors: Set of hex color strings
        - pages_analyzed: int

    Example:
        info = extract_fonts_and_colors(Path("/tmp/report.pdf"))
        print(f"Fonts used: {info['fonts']}")
        print(f"Colors used: {info['colors']}")
    """
    try:
        import fitz  # PyMuPDF

        fonts_used: Set[Tuple[str, float]] = set()
        font_usage_counter: Counter[str] = Counter()
        font_sizes_map: Dict[str, Set[float]] = defaultdict(set)
        colors_used: Set[str] = set()
        color_usage_counter: Counter[str] = Counter()
        pages_analyzed = 0

        with fitz.open(str(pdf_path)) as doc:
            for page in doc:
                pages_analyzed += 1

                # Extract text with font information
                blocks = page.get_text("dict")["blocks"]

                for block in blocks:
                    if block.get("type") != 0:  # 0 = text block
                        continue

                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            font_name = (span.get("font") or "Unknown").strip()
                            font_size = span.get("size", 0)
                            color = span.get("color", 0)

                            # Store font info
                            fonts_used.add((font_name, round(font_size, 1)))
                            font_usage_counter[font_name] += 1
                            font_sizes_map[font_name].add(round(font_size, 1))

                            # Convert color int to hex
                            # PyMuPDF color is int: 0xRRGGBB
                            if color:
                                hex_color = f"#{color:06X}"
                                colors_used.add(hex_color)
                                color_usage_counter[hex_color] += 1

        logger.info(
            "Font and color extraction completed",
            pdf_path=str(pdf_path),
            unique_fonts=len(fonts_used),
            unique_colors=len(colors_used),
            pages_analyzed=pages_analyzed,
        )

        return {
            "fonts": fonts_used,
            "font_usage": [
                {
                    "font": font_name,
                    "count": font_usage_counter[font_name],
                    "sizes": sorted(font_sizes_map.get(font_name, [])),
                }
                for font_name in font_usage_counter
            ],
            "colors": colors_used,
            "color_usage": [
                {"color": color, "count": count}
                for color, count in color_usage_counter.most_common()
            ],
            "pages_analyzed": pages_analyzed,
        }

    except ImportError:
        logger.error("PyMuPDF not installed, cannot extract fonts/colors")
        return {"fonts": set(), "colors": set(), "pages_analyzed": 0}

    except Exception as exc:
        logger.error("Font/color extraction failed", error=str(exc), exc_info=True)
        return {"fonts": set(), "colors": set(), "pages_analyzed": 0}


# ============================================================================
# Font Validation
# ============================================================================


def validate_fonts(
    fonts_used: Set[Tuple[str, float]],
    allowed_fonts: List[str],
    min_size: float = 8.0,
    max_size: float = 72.0,
) -> List[Dict[str, Any]]:
    """
    Validate fonts against whitelist and size constraints.

    Args:
        fonts_used: Set of (font_name, size) tuples
        allowed_fonts: List of allowed font names
        min_size: Minimum font size (points)
        max_size: Maximum font size (points)

    Returns:
        List of violations
    """
    violations = []

    for font_name, font_size in fonts_used:
        # Check whitelist
        if not any(allowed in font_name for allowed in allowed_fonts):
            violations.append({
                "font_name": font_name,
                "font_size": font_size,
                "issue": f"Fuente no autorizada: {font_name}",
                "rule": "font_whitelist",
            })

        # Check size range
        if font_size < min_size:
            violations.append({
                "font_name": font_name,
                "font_size": font_size,
                "issue": f"Tamaño de fuente muy pequeño: {font_size}pt < {min_size}pt",
                "rule": "font_size_min",
            })

        if font_size > max_size:
            violations.append({
                "font_name": font_name,
                "font_size": font_size,
                "issue": f"Tamaño de fuente muy grande: {font_size}pt > {max_size}pt",
                "rule": "font_size_max",
            })

    return violations


# ============================================================================
# Color Validation
# ============================================================================


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def color_distance(color1: str, color2: str) -> float:
    """
    Calculate Euclidean distance between two hex colors.

    Returns:
        Distance 0.0 - 441.67 (0 = identical, 441.67 = max distance)
    """
    r1, g1, b1 = hex_to_rgb(color1)
    r2, g2, b2 = hex_to_rgb(color2)

    distance = ((r2 - r1)**2 + (g2 - g1)**2 + (b2 - b1)**2) ** 0.5
    return distance


def is_color_in_palette(
    color: str,
    palette: List[str],
    tolerance: float = 0.1,
) -> bool:
    """
    Check if color is within tolerance of palette colors.

    Args:
        color: Hex color to check
        palette: List of allowed hex colors
        tolerance: Tolerance fraction (0.1 = 10% variance)

    Returns:
        True if color matches any palette color within tolerance
    """
    max_distance = 441.67  # Maximum RGB distance (sqrt(255^2 + 255^2 + 255^2))
    threshold = max_distance * tolerance

    for palette_color in palette:
        if color_distance(color, palette_color) <= threshold:
            return True

    return False


def validate_colors(
    colors_used: Set[str],
    palette: List[str],
    tolerance: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    Validate colors against brand palette.

    Args:
        colors_used: Set of hex colors found in document
        palette: List of allowed hex colors
        tolerance: Tolerance for color matching (0.1 = 10%)

    Returns:
        List of violations
    """
    violations = []

    for color in colors_used:
        if not is_color_in_palette(color, palette, tolerance):
            # Find closest palette color for suggestion
            closest_color = min(
                palette,
                key=lambda p: color_distance(color, p)
            )

            violations.append({
                "color": color,
                "issue": f"Color fuera de paleta corporativa: {color}",
                "rule": "color_palette",
                "closest_match": closest_color,
                "distance": color_distance(color, closest_color),
            })

    return violations


def extract_image_metrics(pdf_path: Path) -> Dict[str, Any]:
    """
    Extract image bounding boxes and compute relative size metrics.

    Args:
        pdf_path: Path to PDF

    Returns:
        Dict with image metrics
    """
    try:
        import fitz

        images: List[Dict[str, Any]] = []
        pages_with_images: Set[int] = set()
        max_ratio = 0.0
        total_ratio = 0.0

        with fitz.open(str(pdf_path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                page_area = page.rect.width * page.rect.height or 1.0
                image_list = page.get_images(full=True)

                if not image_list:
                    continue

                pages_with_images.add(page_index)

                for image in image_list:
                    xref = image[0]
                    rects = page.get_image_rects(xref)

                    for rect in rects:
                        width = rect.width
                        height = rect.height
                        area = width * height
                        ratio = area / page_area
                        max_ratio = max(max_ratio, ratio)
                        total_ratio += ratio

                        images.append(
                            {
                                "page": page_index,
                                "width": round(width, 2),
                                "height": round(height, 2),
                                "area": round(area, 2),
                                "area_ratio": round(ratio, 4),
                            }
                        )

        average_ratio = round(total_ratio / len(images), 4) if images else 0.0

        return {
            "total_images": len(images),
            "pages_with_images": sorted(pages_with_images),
            "largest_image_ratio": round(max_ratio, 4),
            "average_image_ratio": average_ratio,
            "images": images,
        }

    except ImportError:
        logger.error("PyMuPDF not installed, cannot analyze image proportions")
        return {
            "total_images": 0,
            "pages_with_images": [],
            "largest_image_ratio": 0.0,
            "average_image_ratio": 0.0,
            "images": [],
        }
    except Exception as exc:
        logger.error(
            "Image extraction failed",
            error=str(exc),
            pdf_path=str(pdf_path),
            exc_info=True,
        )
        return {
            "total_images": 0,
            "pages_with_images": [],
            "largest_image_ratio": 0.0,
            "average_image_ratio": 0.0,
            "images": [],
            "error": str(exc),
        }


# ============================================================================
# Main Audit Function
# ============================================================================


async def audit_format(
    fragments: List[PageFragment],
    pdf_path: Path,
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit document formatting (numbers, fonts, colors).

    Args:
        fragments: List of PageFragment objects
        pdf_path: Path to PDF file (for font/color extraction)
        config: Compliance configuration

    Returns:
        (findings, summary) tuple

    Example:
        findings, summary = await audit_format(fragments, pdf_path, config)
        print(f"Format violations: {len(findings)}")
    """
    findings: List[Finding] = []
    format_config = config.get("format", {})

    logger.info(
        "Starting format audit",
        fragments_count=len(fragments),
        pdf_path=str(pdf_path),
    )

    # ========================================================================
    # 1. Number Format Validation
    # ========================================================================

    numeric_cfg = format_config.get("numeric_format")
    # Backward compatibility with legacy "numbers" config
    if not numeric_cfg and format_config.get("numbers"):
        legacy = format_config.get("numbers", {})
        numeric_cfg = {
            "enabled": True,
            "style": "EU",
            "thousand_sep": legacy.get("thousands_separator", "."),
            "decimal_sep": legacy.get("decimal_separator", ","),
            "min_decimals": legacy.get("min_decimals", 2),
            "max_decimals": legacy.get("max_decimals", 2),
            "severity": legacy.get("severity", "medium"),
        }

    numeric_findings: List[Finding] = []
    numeric_summary = {
        "enabled": False,
        "checked": 0,
        "invalid": 0,
        "compliance_rate": 1.0,
    }

    if numeric_cfg:
        numeric_findings, numeric_summary = await audit_numeric_format(
            fragments,
            numeric_cfg,
        )
        findings.extend(numeric_findings)

    number_violations_count = numeric_summary.get("invalid", 0)

    # ========================================================================
    # 2. Font Validation
    # ========================================================================

    fonts_config = format_config.get("fonts", {})
    allowed_fonts = fonts_config.get("allowed", ["Arial", "Helvetica", "Calibri"])
    font_severity = fonts_config.get("severity", "medium")

    font_sizes_config = format_config.get("font_sizes", {})
    min_font_size = font_sizes_config.get("min", 8)
    max_font_size = font_sizes_config.get("max", 72)
    font_size_severity = font_sizes_config.get("severity", "low")

    # Extract fonts from PDF
    font_color_info = extract_fonts_and_colors(pdf_path)
    fonts_used = font_color_info["fonts"]
    font_usage_detail = font_color_info.get("font_usage", [])

    font_violations = validate_fonts(
        fonts_used,
        allowed_fonts,
        min_font_size,
        max_font_size,
    )

    for violation in font_violations:
        finding_id = f"font-{uuid4().hex[:8]}"
        severity = font_severity if violation["rule"] == "font_whitelist" else font_size_severity

        findings.append(
            Finding(
                id=finding_id,
                category="format",
                rule=violation["rule"],
                issue=violation["issue"],
                severity=severity,
                location=Location(
                    page=1,  # Font violations apply to entire document
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None,
                ),
                suggestion=(
                    f"Usar fuentes permitidas: {', '.join(allowed_fonts)}"
                    if violation["rule"] == "font_whitelist"
                    else f"Ajustar tamaño entre {min_font_size}pt y {max_font_size}pt"
                ),
                evidence=[
                    Evidence(
                        kind="metric",
                        data={
                            "font_name": violation["font_name"],
                            "font_size": violation["font_size"],
                        },
                    )
                ],
            )
        )

    # ========================================================================
    # 3. Color Validation
    # ========================================================================

    colors_config = format_config.get("colors", {})
    palette = colors_config.get("palette", ["#002B5C", "#FFFFFF", "#000000"])
    color_tolerance = colors_config.get("tolerance", 0.1)
    color_severity = colors_config.get("severity", "low")

    colors_used = font_color_info["colors"]
    color_usage_detail = font_color_info.get("color_usage", [])

    # Extract image metrics
    image_metrics = extract_image_metrics(pdf_path)

    color_violations = validate_colors(colors_used, palette, color_tolerance)

    for violation in color_violations:
        finding_id = f"color-{uuid4().hex[:8]}"

        findings.append(
            Finding(
                id=finding_id,
                category="format",
                rule="color_palette",
                issue=violation["issue"],
                severity=color_severity,
                location=Location(
                    page=1,  # Color violations apply to entire document
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None,
                ),
                suggestion=f"Usar color de paleta más cercano: {violation['closest_match']}",
                evidence=[
                    Evidence(
                        kind="metric",
                        data={
                            "color_found": violation["color"],
                            "closest_palette_color": violation["closest_match"],
                            "distance": violation["distance"],
                        },
                    )
                ],
            )
        )

    # ========================================================================
    # Summary
    # ========================================================================

    # ========================================================================
    # 4. Image proportion checks
    # ========================================================================

    image_config = format_config.get("images", {})
    image_violation_count = 0
    image_findings_limit = image_config.get("max_findings", 10)
    image_severity = image_config.get("severity", "low")
    max_ratio_allowed = image_config.get("max_ratio")
    min_ratio_allowed = image_config.get("min_ratio")

    for image_info in image_metrics.get("images", []):
        ratio = image_info.get("area_ratio", 0.0)
        page = image_info.get("page")
        trigger = None

        if max_ratio_allowed is not None and ratio > max_ratio_allowed:
            trigger = (
                f"Imagen ocupa {ratio:.1%} de la página (límite {max_ratio_allowed:.0%})"
            )
        elif min_ratio_allowed is not None and ratio < min_ratio_allowed:
            trigger = (
                f"Imagen muy pequeña ({ratio:.1%} de la página, mínimo {min_ratio_allowed:.0%})"
            )

        if trigger and image_violation_count < image_findings_limit:
            finding_id = f"image-ratio-{page}-{uuid4().hex[:8]}"
            findings.append(
                Finding(
                    id=finding_id,
                    category="format",
                    rule="image_proportion",
                    issue=trigger,
                    severity=image_severity,
                    location=Location(
                        page=page,
                        bbox=None,
                        fragment_id=None,
                        text_snippet=None,
                    ),
                    suggestion="Ajustar tamaño de la imagen para mantener proporciones equilibradas.",
                    evidence=[
                        Evidence(
                            kind="metric",
                            data={
                                "page": page,
                                "area_ratio": ratio,
                                "max_allowed": max_ratio_allowed,
                                "min_allowed": min_ratio_allowed,
                                "width": image_info.get("width"),
                                "height": image_info.get("height"),
                            },
                        )
                    ],
                )
            )
            image_violation_count += 1

    # ========================================================================
    # Summary
    # ========================================================================

    summary = {
        "number_violations": number_violations_count,
        "font_violations": len(font_violations),
        "color_violations": len(color_violations),
        "image_violations": image_violation_count,
        "total_violations": len(findings),
        "fonts_analyzed": len(fonts_used),
        "colors_analyzed": len(colors_used),
        "fonts_detail": font_usage_detail,
        "colors_detail": color_usage_detail,
        "dominant_colors": [item["color"] for item in color_usage_detail[:5]],
        "images": image_metrics,
        "numeric_format": numeric_summary,
    }

    logger.info(
        "Format audit completed",
        findings_count=len(findings),
        number_violations=number_violations_count,
        font_violations=len(font_violations),
        color_violations=len(color_violations),
    )

    return findings, summary
