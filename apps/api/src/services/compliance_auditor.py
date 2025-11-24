"""
Compliance auditor for Document Audit.

Validates documents against compliance rules:
- Disclaimer presence and coverage (per-page)
- Client name verification
- Template matching with fuzzy logic

Configuration:
    apps/api/config/compliance.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from uuid import uuid4

import structlog
import yaml
from rapidfuzz import fuzz

from ..models.document import PageFragment
from ..schemas.audit_message import Finding, Location, Evidence, Category, Severity

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuration Loading
# ============================================================================


def load_compliance_config() -> Dict[str, Any]:
    """
    Load compliance configuration from YAML file.

    Returns:
        Configuration dictionary with disclaimers, logo, format rules

    Example:
        config = load_compliance_config()
        templates = config["disclaimers"]["templates"]
        tolerance = config["disclaimers"]["default_tolerance"]
    """
    # Try multiple paths (local dev, Docker container, tests)
    config_paths = [
        Path(__file__).parent.parent.parent / "config" / "compliance.yaml",
        Path("/app/config/compliance.yaml"),
        Path("apps/api/config/compliance.yaml"),
    ]

    for config_path in config_paths:
        if config_path.exists():
            logger.info("Loading compliance config", path=str(config_path))
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

    # Fallback: Return default config
    logger.warning(
        "Compliance config not found, using defaults",
        searched_paths=[str(p) for p in config_paths],
    )
    return _default_compliance_config()


def _default_compliance_config() -> Dict[str, Any]:
    """Fallback configuration if YAML file is not found"""
    return {
        "disclaimers": {
            "default_tolerance": 0.90,
            "min_coverage": 1.0,
            "missing_severity": "high",
            "templates": [
                {
                    "id": "std-es",
                    "text": "Este documento es confidencial y dirigido exclusivamente a {CLIENTE} por 414 Capital.",
                    "active": True,
                }
            ],
        },
        "logo": {
            "min_similarity": 0.75,
            "min_area": 5000,
            "required_pages": ["first", "last"],
            "missing_severity": "high",
        },
        "format": {
            "numeric_format": {
                "enabled": True,
                "style": "MX",
                "thousand_sep": ",",
                "decimal_sep": ".",
                "min_decimals": 2,
                "max_decimals": 2,
                "severity": "high",
            },
            "fonts": {"allowed": ["Arial", "Helvetica", "Calibri"]},
            "colors": {"palette": ["#002B5C", "#FFFFFF", "#000000"]},
        },
        "typography": {
            "enabled": True,
            "heading_font_threshold": 18,
            "max_heading_levels": 5,
            "min_line_spacing": 0.5,
            "max_line_spacing": 2.5,
            "severity_heading": "low",
            "severity_spacing": "low",
        },
    }


# ============================================================================
# Disclaimer Matching
# ============================================================================


def match_disclaimer(fragment_text: str, template_text: str, client_name: Optional[str] = None) -> float:
    """
    Calculate similarity score between fragment text and template.

    Uses fuzzy token set ratio (insensitive to word order, extra words).

    Args:
        fragment_text: Text extracted from PDF fragment
        template_text: Template string (may contain {CLIENTE} placeholder)
        client_name: Client name to substitute into template (optional)

    Returns:
        Similarity score 0.0 - 1.0 (1.0 = perfect match)

    Example:
        score = match_disclaimer(
            "Este documento es confidencial para Banamex por 414 Capital.",
            "Este documento es confidencial y dirigido exclusivamente a {CLIENTE} por 414 Capital.",
            "Banamex"
        )
        # score ~= 0.92 (high similarity despite differences)
    """
    # Substitute client name if provided
    if client_name and "{CLIENTE}" in template_text:
        template_text = template_text.replace("{CLIENTE}", client_name)

    # Normalize text (lowercase, strip whitespace)
    fragment_normalized = fragment_text.lower().strip()
    template_normalized = template_text.lower().strip()

    # Fuzzy matching (token_set_ratio: ignores word order, extra words)
    score = fuzz.token_set_ratio(fragment_normalized, template_normalized) / 100.0

    return score


def find_best_template_match(
    fragment_text: str,
    templates: List[Dict[str, Any]],
    client_name: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    Find the best matching template for a fragment.

    Args:
        fragment_text: Text from PDF fragment
        templates: List of template dicts with 'id', 'text', 'active'
        client_name: Client name for placeholder substitution

    Returns:
        (best_template, best_score) or (None, 0.0) if no active templates
    """
    best_template = None
    best_score = 0.0

    for template in templates:
        # Skip inactive templates
        if not template.get("active", True):
            continue

        score = match_disclaimer(fragment_text, template["text"], client_name)

        if score > best_score:
            best_score = score
            best_template = template

    return best_template, best_score


# ============================================================================
# Coverage Analysis
# ============================================================================


def analyze_disclaimer_coverage(
    fragments: List[PageFragment],
    templates: List[Dict[str, Any]],
    tolerance: float = 0.90,
    client_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyze disclaimer coverage across all pages.

    Args:
        fragments: List of PageFragment objects
        templates: Template configurations
        tolerance: Minimum similarity score (0-1)
        client_name: Client name for validation

    Returns:
        Coverage analysis dict with:
        - coverage_by_page: {page: bool}
        - total_pages: int
        - covered_pages: int
        - coverage_ratio: float
        - missing_pages: List[int]
        - matches: List[dict] (page, template_id, score, fragment_id)

    Example:
        result = analyze_disclaimer_coverage(fragments, templates, 0.90, "Banamex")
        if result["coverage_ratio"] < 1.0:
            print(f"Missing disclaimers on pages: {result['missing_pages']}")
    """
    # Group fragments by page
    fragments_by_page: Dict[int, List[PageFragment]] = {}
    for frag in fragments:
        if frag.page not in fragments_by_page:
            fragments_by_page[frag.page] = []
        fragments_by_page[frag.page].append(frag)

    # Determine total pages
    all_pages = sorted(fragments_by_page.keys())
    total_pages = max(all_pages) if all_pages else 0

    # Check each page for disclaimer
    coverage_by_page: Dict[int, bool] = {}
    matches: List[Dict[str, Any]] = []

    for page in range(1, total_pages + 1):
        page_fragments = fragments_by_page.get(page, [])

        # Only check footer fragments
        footer_fragments = [f for f in page_fragments if f.kind == "footer"]

        page_has_disclaimer = False

        for frag in footer_fragments:
            template, score = find_best_template_match(frag.text, templates, client_name)

            if template and score >= tolerance:
                page_has_disclaimer = True
                matches.append({
                    "page": page,
                    "template_id": template["id"],
                    "score": score,
                    "fragment_id": frag.fragment_id,
                    "text_snippet": frag.text[:100],
                })
                break  # Found valid disclaimer on this page

        coverage_by_page[page] = page_has_disclaimer

    # Calculate metrics
    covered_pages = sum(1 for has_disc in coverage_by_page.values() if has_disc)
    coverage_ratio = covered_pages / total_pages if total_pages > 0 else 0.0
    missing_pages = [page for page, has_disc in coverage_by_page.items() if not has_disc]

    logger.info(
        "Disclaimer coverage analysis completed",
        total_pages=total_pages,
        covered_pages=covered_pages,
        coverage_ratio=coverage_ratio,
        missing_pages=missing_pages,
        matches_found=len(matches),
    )

    return {
        "coverage_by_page": coverage_by_page,
        "total_pages": total_pages,
        "covered_pages": covered_pages,
        "coverage_ratio": coverage_ratio,
        "missing_pages": missing_pages,
        "matches": matches,
    }


# ============================================================================
# Findings Generation
# ============================================================================


def generate_disclaimer_findings(
    coverage_analysis: Dict[str, Any],
    config: Dict[str, Any],
) -> List[Finding]:
    """
    Generate Finding objects for missing disclaimers.

    Args:
        coverage_analysis: Result from analyze_disclaimer_coverage()
        config: Compliance configuration

    Returns:
        List of Finding objects (one per missing page)

    Example:
        analysis = analyze_disclaimer_coverage(fragments, templates, 0.90)
        findings = generate_disclaimer_findings(analysis, config)
        for finding in findings:
            print(f"{finding.severity}: {finding.issue}")
    """
    findings: List[Finding] = []

    missing_pages = coverage_analysis["missing_pages"]
    severity = config["disclaimers"].get("missing_severity", "high")

    for page in missing_pages:
        finding_id = f"disclaimer-missing-{page}-{uuid4().hex[:8]}"

        findings.append(
            Finding(
                id=finding_id,
                category="compliance",
                rule="disclaimer_coverage",
                issue=f"Disclaimer ausente o inválido en página {page}",
                severity=severity,
                location=Location(
                    page=page,
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None,
                ),
                suggestion=(
                    f"Agregar disclaimer válido en el footer de la página {page}. "
                    "Consultar config/compliance.yaml para plantillas aprobadas."
                ),
                evidence=[
                    Evidence(
                        kind="metric",
                        data={
                            "coverage_ratio": coverage_analysis["coverage_ratio"],
                            "total_pages": coverage_analysis["total_pages"],
                            "covered_pages": coverage_analysis["covered_pages"],
                        },
                    )
                ],
            )
        )

    # Add summary finding if coverage is below threshold
    min_coverage = config["disclaimers"].get("min_coverage", 1.0)
    if coverage_analysis["coverage_ratio"] < min_coverage:
        findings.append(
            Finding(
                id=f"disclaimer-coverage-low-{uuid4().hex[:8]}",
                category="compliance",
                rule="disclaimer_min_coverage",
                issue=(
                    f"Cobertura de disclaimers insuficiente: "
                    f"{coverage_analysis['coverage_ratio']:.1%} < {min_coverage:.1%}"
                ),
                severity="critical" if coverage_analysis["coverage_ratio"] < 0.5 else "high",
                location=Location(
                    page=1,  # Summary applies to entire document
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None,
                ),
                suggestion=(
                    f"Aumentar cobertura de disclaimers. Páginas faltantes: {missing_pages}"
                ),
                evidence=[
                    Evidence(
                        kind="metric",
                        data={
                            "coverage_ratio": coverage_analysis["coverage_ratio"],
                            "min_coverage": min_coverage,
                            "missing_pages": missing_pages,
                        },
                    )
                ],
            )
        )

    logger.info(
        "Disclaimer findings generated",
        total_findings=len(findings),
        missing_pages=len(missing_pages),
    )

    return findings


# ============================================================================
# Main Audit Function
# ============================================================================


async def audit_disclaimers(
    fragments: List[PageFragment],
    client_name: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit document for disclaimer compliance.

    Main entry point for disclaimer validation.

    Args:
        fragments: List of PageFragment objects from document
        client_name: Expected client name (for validation)
        config: Compliance configuration (loads from YAML if not provided)

    Returns:
        (findings, summary) tuple:
        - findings: List of Finding objects
        - summary: Dict with coverage metrics

    Example:
        from services.document_extraction import extract_fragments_with_bbox
        from services.compliance_auditor import audit_disclaimers

        fragments = await extract_fragments_with_bbox(Path("/tmp/report.pdf"))
        findings, summary = await audit_disclaimers(fragments, "Banamex")

        print(f"Coverage: {summary['coverage_ratio']:.1%}")
        for finding in findings:
            print(f"  {finding.severity.upper()}: {finding.issue}")
    """
    # Load configuration
    if config is None:
        config = load_compliance_config()

    # Extract disclaimer configuration
    disclaimer_config = config.get("disclaimers", {})
    templates = disclaimer_config.get("templates", [])
    tolerance = disclaimer_config.get("default_tolerance", 0.90)

    logger.info(
        "Starting disclaimer audit",
        fragments_count=len(fragments),
        client_name=client_name,
        templates_count=len(templates),
        tolerance=tolerance,
    )

    # Analyze coverage
    coverage_analysis = analyze_disclaimer_coverage(
        fragments=fragments,
        templates=templates,
        tolerance=tolerance,
        client_name=client_name,
    )

    # Generate findings
    findings = generate_disclaimer_findings(coverage_analysis, config)

    # Build summary
    summary = {
        "disclaimer_coverage": coverage_analysis["coverage_ratio"],
        "pages_with_disclaimer": coverage_analysis["covered_pages"],
        "pages_missing_disclaimer": len(coverage_analysis["missing_pages"]),
        "total_pages": coverage_analysis["total_pages"],
        "matches": coverage_analysis["matches"],
    }

    logger.info(
        "Disclaimer audit completed",
        findings_count=len(findings),
        coverage=coverage_analysis["coverage_ratio"],
    )

    return findings, summary
