"""
Typography Auditor for Document Audit.

Validates basic typography guidelines:
- Reasonable number of heading levels (based on font size)
- Detects overlapping text fragments (line spacing issues)

Configuration is read from compliance/policy configuration under the
"typography" key.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from uuid import uuid4

import structlog

from ..models.document import PageFragment
from ..schemas.audit_message import Evidence, Finding, Location

logger = structlog.get_logger(__name__)


def _collect_heading_sizes(
    fragments: List[PageFragment], font_threshold: float
) -> List[float]:
    sizes = [
        round(fragment.font_size, 1)
        for fragment in fragments
        if fragment.font_size and fragment.font_size >= font_threshold
    ]
    return sorted(set(sizes))


def _detect_heading_issues(
    fragments: List[PageFragment],
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []

    font_threshold = config.get("heading_font_threshold", 18.0)
    max_levels = config.get("max_heading_levels", 5)
    severity = config.get("severity_heading", "low")

    heading_sizes = _collect_heading_sizes(fragments, font_threshold)

    if heading_sizes and len(heading_sizes) > max_levels:
        largest = max(heading_sizes)
        smallest = min(heading_sizes)

        # Use first heading fragment as reference for location/snippet
        reference = next(
            (
                fragment
                for fragment in fragments
                if fragment.font_size and fragment.font_size >= font_threshold
            ),
            None,
        )

        finding_id = f"typo-heading-{uuid4().hex[:8]}"
        snippet = reference.text[:120] if reference else None

        findings.append(
            Finding(
                id=finding_id,
                category="typography",
                rule="heading_hierarchy",
                issue=(
                    f"Jerarquía de encabezados inconsistente: {len(heading_sizes)} tamaños detectados"
                ),
                severity=severity,
                location=Location(
                    page=reference.page if reference else 1,
                    bbox=reference.bbox if reference else None,
                    fragment_id=reference.fragment_id if reference else None,
                    text_snippet=snippet,
                ),
                suggestion=
                "Mantener entre 3 y 5 niveles de encabezado para facilitar la lectura.",
                evidence=[
                    Evidence(
                        kind="metric",
                        data={
                            "unique_heading_sizes": heading_sizes,
                            "largest": largest,
                            "smallest": smallest,
                        },
                    )
                ],
            )
        )

    summary = {
        "heading_sizes_detected": heading_sizes,
        "heading_levels": len(heading_sizes),
        "font_threshold": font_threshold,
        "max_allowed_levels": max_levels,
    }

    return findings, summary


def _detect_line_spacing_issues(
    fragments: List[PageFragment],
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    findings: List[Finding] = []

    min_spacing = config.get("min_line_spacing", 0.5)
    max_spacing = config.get("max_line_spacing", 3.0)
    severity = config.get("severity_spacing", "low")

    overlaps = 0
    pages_processed = set()

    # Group by page
    fragments_by_page: Dict[int, List[PageFragment]] = {}
    for fragment in fragments:
        if fragment.bbox is None:
            continue
        fragments_by_page.setdefault(fragment.page, []).append(fragment)

    for page, page_fragments in fragments_by_page.items():
        if len(page_fragments) < 2:
            continue

        pages_processed.add(page)
        # Sort by vertical position (y coordinate)
        sorted_frags = sorted(page_fragments, key=lambda f: f.bbox[1])

        for current, nxt in zip(sorted_frags, sorted_frags[1:]):
            current_bottom = current.bbox[3]
            next_top = nxt.bbox[1]
            line_height = current.bbox[3] - current.bbox[1]

            if next_top < current_bottom:
                overlaps += 1
                findings.append(
                    Finding(
                        id=f"typo-spacing-{uuid4().hex[:8]}",
                        category="typography",
                        rule="line_spacing",
                        issue="Fragmentos de texto superpuestos detectados",
                        severity=severity,
                        location=Location(
                            page=page,
                            bbox=current.bbox,
                            fragment_id=current.fragment_id,
                            text_snippet=(current.text[:120] if current.text else None),
                        ),
                        suggestion="Ajustar interlineado para evitar superposición de texto.",
                        evidence=[
                            Evidence(
                                kind="metric",
                                data={
                                    "current_bottom": current_bottom,
                                    "next_top": next_top,
                                    "line_height": line_height,
                                },
                            )
                        ],
                    )
                )
            else:
                # Optional spacing check if we have meaningful metrics
                if line_height > 0:
                    spacing_ratio = (next_top - current_bottom) / line_height
                    if spacing_ratio < min_spacing or spacing_ratio > max_spacing:
                        findings.append(
                            Finding(
                                id=f"typo-spacing-{uuid4().hex[:8]}",
                                category="typography",
                                rule="line_spacing",
                                issue=(
                                    f"Espaciado irregular entre líneas (ratio {spacing_ratio:.2f})"
                                ),
                                severity=severity,
                                location=Location(
                                    page=page,
                                    bbox=current.bbox,
                                    fragment_id=current.fragment_id,
                                    text_snippet=(current.text[:120] if current.text else None),
                                ),
                                suggestion="Revisar interlineado para mantener consistencia visual.",
                                evidence=[
                                    Evidence(
                                        kind="metric",
                                        data={
                                            "spacing_ratio": round(spacing_ratio, 3),
                                            "min_allowed": min_spacing,
                                            "max_allowed": max_spacing,
                                        },
                                    )
                                ],
                            )
                        )

    summary = {
        "pages_analyzed": sorted(pages_processed),
        "overlaps_detected": overlaps,
        "min_line_spacing": min_spacing,
        "max_line_spacing": max_spacing,
    }

    return findings, summary


async def audit_typography(
    fragments: List[PageFragment],
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit typography best practices.
    """
    if not config.get("enabled", True):
        return [], {
            "enabled": False,
            "heading_levels": 0,
            "overlaps_detected": 0,
        }

    logger.info(
        "Starting typography audit",
        fragments_count=len(fragments),
        config=config,
    )

    heading_findings, heading_summary = _detect_heading_issues(fragments, config)
    spacing_findings, spacing_summary = _detect_line_spacing_issues(fragments, config)

    findings = heading_findings + spacing_findings
    summary = {
        "enabled": True,
        "heading": heading_summary,
        "spacing": spacing_summary,
        "total_findings": len(findings),
    }

    logger.info(
        "Typography audit completed",
        findings=len(findings),
        heading_levels=heading_summary.get("heading_levels", 0),
        overlaps=spacing_summary.get("overlaps_detected", 0),
    )

    return findings, summary
