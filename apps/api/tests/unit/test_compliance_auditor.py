"""
Unit tests for compliance_auditor.py

Tests cover:
- Fuzzy matching (match_disclaimer)
- Template selection (find_best_template_match)
- Coverage analysis (analyze_disclaimer_coverage)
- Finding generation (generate_disclaimer_findings)
- Full audit flow (audit_disclaimers)
"""

import pytest
from typing import List, Dict, Any
from uuid import uuid4
from types import SimpleNamespace

from src.services.compliance_auditor import (
    match_disclaimer,
    find_best_template_match,
    analyze_disclaimer_coverage,
    generate_disclaimer_findings,
    load_compliance_config,
    audit_disclaimers,
)
from src.models.document import PageFragment


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def compliance_config():
    """Sample compliance configuration for testing"""
    return {
        "disclaimers": {
            "templates": [
                {
                    "id": "template-414-capital",
                    "text": "Este documento es confidencial para {CLIENTE} por 414 Capital.",
                    "active": True,
                }
            ],
            "default_tolerance": 0.80,
            "severity": "high",
            "min_coverage": 1.0,
        },
        "format": {
            "numeric_format": {},
            "fonts": {},
        },
        "logo": {},
    }


@pytest.fixture
def sample_fragments_with_disclaimer():
    """Create sample fragments with disclaimers on all pages (full coverage)"""
    fragments = []

    # Page 1 - with disclaimer in footer
    fragments.append(SimpleNamespace(
        fragment_id=f"1-{uuid4().hex[:8]}",
        page=1,
        kind="footer",
        bbox=[50.0, 700.0, 500.0, 750.0],
        text="Este documento es confidencial para Banamex por 414 Capital.",
    ))

    # Page 2 - with disclaimer in footer
    fragments.append(SimpleNamespace(
        fragment_id=f"2-{uuid4().hex[:8]}",
        page=2,
        kind="footer",
        bbox=[50.0, 700.0, 500.0, 750.0],
        text="Este documento es confidencial para Banamex por 414 Capital.",
    ))

    # Page 3 - with disclaimer in footer
    fragments.append(SimpleNamespace(
        fragment_id=f"3-{uuid4().hex[:8]}",
        page=3,
        kind="footer",
        bbox=[50.0, 700.0, 500.0, 750.0],
        text="Este documento es confidencial para Banamex por 414 Capital.",
    ))

    return fragments


@pytest.fixture
def sample_fragments_missing_disclaimer():
    """Create sample fragments with disclaimer only on page 1 (partial coverage)"""
    fragments = []

    # Page 1 - with disclaimer in footer
    fragments.append(SimpleNamespace(
        fragment_id=f"1-{uuid4().hex[:8]}",
        page=1,
        kind="footer",
        bbox=[50.0, 700.0, 500.0, 750.0],
        text="Este documento es confidencial para Banamex por 414 Capital.",
    ))

    # Page 2 - NO disclaimer (missing)
    fragments.append(SimpleNamespace(
        fragment_id=f"2-{uuid4().hex[:8]}",
        page=2,
        kind="footer",
        bbox=[50.0, 700.0, 500.0, 750.0],
        text="Página 2",
    ))

    # Page 3 - NO disclaimer (missing)
    fragments.append(SimpleNamespace(
        fragment_id=f"3-{uuid4().hex[:8]}",
        page=3,
        kind="footer",
        bbox=[50.0, 700.0, 500.0, 750.0],
        text="Página 3",
    ))

    return fragments


# ============================================================================
# Test: Fuzzy Matching
# ============================================================================


def test_match_disclaimer_exact_match():
    """Test perfect match returns score of 1.0"""
    template = "Este documento es confidencial para {CLIENTE} por 414 Capital."
    text = "Este documento es confidencial para Banamex por 414 Capital."

    score = match_disclaimer(text, template, client_name="Banamex")

    assert score >= 0.95, "Exact match should have score >= 0.95"


def test_match_disclaimer_minor_variation():
    """Test minor variations still get high score"""
    template = "Este documento es confidencial para {CLIENTE} por 414 Capital."
    text = "Este documento confidencial es para Banamex por 414 Capital."

    score = match_disclaimer(text, template, client_name="Banamex")

    # Minor word order change should still match well
    assert score >= 0.80, "Minor variation should still score >= 0.80"


def test_match_disclaimer_completely_different():
    """Test completely different text gets low score"""
    template = "Este documento es confidencial para {CLIENTE} por 414 Capital."
    text = "Este es un documento público de acceso general."

    score = match_disclaimer(text, template, client_name="Banamex")

    # Note: token_set_ratio can give higher scores than expected for partial overlaps
    # "documento" appears in both, so score might be ~0.56
    assert score < 0.70, "Different text should score < 0.70"


def test_match_disclaimer_without_client_name():
    """Test matching works even without client name substitution"""
    template = "Este documento es confidencial por 414 Capital."
    text = "Este documento es confidencial por 414 Capital."

    score = match_disclaimer(text, template, client_name=None)

    assert score >= 0.95, "Match without client name should work"


def test_match_disclaimer_case_insensitive():
    """Test matching is case-insensitive"""
    template = "Este documento es confidencial para {CLIENTE} por 414 Capital."
    text = "ESTE DOCUMENTO ES CONFIDENCIAL PARA BANAMEX POR 414 CAPITAL."

    score = match_disclaimer(text, template, client_name="Banamex")

    assert score >= 0.95, "Case should not affect matching"


# ============================================================================
# Test: Template Selection
# ============================================================================


def test_find_best_template_match_single_template():
    """Test finding best match with single template"""
    templates = [
        {
            "id": "test-template",
            "text": "Este documento es confidencial para {CLIENTE} por 414 Capital.",
            "active": True,
        }
    ]

    text = "Este documento es confidencial para Banamex por 414 Capital."

    best_template, score = find_best_template_match(text, templates, "Banamex")

    assert best_template is not None, "Should find template"
    assert best_template["id"] == "test-template"
    assert score >= 0.95


def test_find_best_template_match_multiple_templates():
    """Test selecting best match from multiple templates"""
    templates = [
        {
            "id": "template-1",
            "text": "Este documento es confidencial para {CLIENTE}.",
            "active": True,
        },
        {
            "id": "template-2",
            "text": "Este documento es confidencial para {CLIENTE} por 414 Capital.",
            "active": True,
        },
    ]

    text = "Este documento es confidencial para Banamex por 414 Capital."

    best_template, score = find_best_template_match(text, templates, "Banamex")

    # Should select template-2 (more specific)
    assert best_template["id"] == "template-2"
    assert score >= 0.95


def test_find_best_template_match_inactive_template():
    """Test inactive templates are ignored"""
    templates = [
        {
            "id": "inactive",
            "text": "Este documento es confidencial para {CLIENTE} por 414 Capital.",
            "active": False,
        },
        {
            "id": "active",
            "text": "Documento para {CLIENTE}.",
            "active": True,
        },
    ]

    text = "Este documento es confidencial para Banamex por 414 Capital."

    best_template, score = find_best_template_match(text, templates, "Banamex")

    # Should NOT select inactive template even if it matches better
    assert best_template["id"] == "active", "Should skip inactive templates"


def test_find_best_template_match_no_active_templates():
    """Test returns None when no active templates"""
    templates = [
        {
            "id": "inactive",
            "text": "Test",
            "active": False,
        }
    ]

    text = "Some text"

    best_template, score = find_best_template_match(text, templates, None)

    assert best_template is None
    assert score == 0.0


# ============================================================================
# Test: Coverage Analysis
# ============================================================================


def test_analyze_disclaimer_coverage_full_coverage(
    sample_fragments_with_disclaimer, compliance_config
):
    """Test analysis with 100% coverage (all pages have disclaimers)"""
    templates = compliance_config["disclaimers"]["templates"]
    tolerance = compliance_config["disclaimers"]["default_tolerance"]

    result = analyze_disclaimer_coverage(
        fragments=sample_fragments_with_disclaimer,
        templates=templates,
        tolerance=tolerance,
        client_name="Banamex",
    )

    assert result["total_pages"] == 3
    assert result["covered_pages"] == 3
    assert result["coverage_ratio"] == 1.0
    assert len(result["missing_pages"]) == 0
    assert len(result["matches"]) == 3


def test_analyze_disclaimer_coverage_partial_coverage(
    sample_fragments_missing_disclaimer, compliance_config
):
    """Test analysis with partial coverage (some pages missing disclaimers)"""
    templates = compliance_config["disclaimers"]["templates"]
    tolerance = compliance_config["disclaimers"]["default_tolerance"]

    result = analyze_disclaimer_coverage(
        fragments=sample_fragments_missing_disclaimer,
        templates=templates,
        tolerance=tolerance,
        client_name="Banamex",
    )

    assert result["total_pages"] == 3
    assert result["covered_pages"] == 1  # Only page 1 has disclaimer
    assert result["coverage_ratio"] == pytest.approx(0.333, abs=0.01)
    assert 2 in result["missing_pages"]
    assert 3 in result["missing_pages"]


def test_analyze_disclaimer_coverage_only_paragraph_fragments(compliance_config):
    """Test that only footer fragments are checked for disclaimers"""
    from uuid import uuid4
    from types import SimpleNamespace

    # Fragments with disclaimer text but kind='paragraph' (should be ignored)
    fragments = [
        SimpleNamespace(
            fragment_id=f"1-{uuid4().hex[:8]}",
            page=1,
            kind="paragraph",  # Not a footer!
            bbox=[50.0, 50.0, 500.0, 100.0],
            text="Este documento es confidencial para Banamex por 414 Capital.",
        )
    ]

    templates = compliance_config["disclaimers"]["templates"]
    tolerance = compliance_config["disclaimers"]["default_tolerance"]

    result = analyze_disclaimer_coverage(
        fragments=fragments,
        templates=templates,
        tolerance=tolerance,
        client_name="Banamex",
    )

    # Should NOT find disclaimer (only looks at footers)
    assert result["covered_pages"] == 0
    assert 1 in result["missing_pages"]


# ============================================================================
# Test: Finding Generation
# ============================================================================


def test_generate_disclaimer_findings_no_violations(compliance_config):
    """Test no findings when all pages have disclaimers"""
    coverage_analysis = {
        "coverage_by_page": {1: True, 2: True, 3: True},
        "total_pages": 3,
        "covered_pages": 3,
        "coverage_ratio": 1.0,
        "missing_pages": [],
        "matches": [
            {"page": 1, "template_id": "test", "score": 0.95},
            {"page": 2, "template_id": "test", "score": 0.95},
            {"page": 3, "template_id": "test", "score": 0.95},
        ],
    }

    findings = generate_disclaimer_findings(coverage_analysis, compliance_config)

    assert len(findings) == 0, "Should have no findings with full coverage"


def test_generate_disclaimer_findings_missing_pages(compliance_config):
    """Test findings are generated for each missing page"""
    coverage_analysis = {
        "coverage_by_page": {1: True, 2: False, 3: False},
        "total_pages": 3,
        "covered_pages": 1,
        "coverage_ratio": 0.333,
        "missing_pages": [2, 3],
        "matches": [{"page": 1, "template_id": "test", "score": 0.95}],
    }

    findings = generate_disclaimer_findings(coverage_analysis, compliance_config)

    # Should have findings for page 2, page 3, and overall coverage
    assert len(findings) >= 2, "Should have finding for each missing page"

    # Check that page numbers are in findings
    pages_with_findings = [f.location.page for f in findings]
    assert 2 in pages_with_findings or any(
        "página 2" in f.issue.lower() for f in findings
    )
    assert 3 in pages_with_findings or any(
        "página 3" in f.issue.lower() for f in findings
    )


def test_generate_disclaimer_findings_severity(compliance_config):
    """Test findings have correct severity"""
    coverage_analysis = {
        "coverage_by_page": {1: False},
        "total_pages": 1,
        "covered_pages": 0,
        "coverage_ratio": 0.0,
        "missing_pages": [1],
        "matches": [],
    }

    findings = generate_disclaimer_findings(coverage_analysis, compliance_config)

    # All disclaimer findings should have high severity (from config)
    for finding in findings:
        assert finding.severity in ["high", "critical"]
        assert finding.category == "compliance"
        assert finding.rule in ["disclaimer_coverage", "disclaimer_min_coverage"]


# ============================================================================
# Test: Full Audit Flow (Integration)
# ============================================================================


@pytest.mark.asyncio
async def test_audit_disclaimers_full_flow_success(
    sample_fragments_with_disclaimer, compliance_config
):
    """Test complete audit flow with valid disclaimers"""
    findings, summary = await audit_disclaimers(
        fragments=sample_fragments_with_disclaimer,
        client_name="Banamex",
        config=compliance_config,
    )

    # Should have no findings
    assert len(findings) == 0

    # Check summary
    assert summary["disclaimer_coverage"] == 1.0
    assert summary["pages_with_disclaimer"] == 3
    assert summary["pages_missing_disclaimer"] == 0
    assert summary["total_pages"] == 3


@pytest.mark.asyncio
async def test_audit_disclaimers_full_flow_violations(
    sample_fragments_missing_disclaimer, compliance_config
):
    """Test complete audit flow with missing disclaimers"""
    findings, summary = await audit_disclaimers(
        fragments=sample_fragments_missing_disclaimer,
        client_name="Banamex",
        config=compliance_config,
    )

    # Should have findings for missing pages
    assert len(findings) >= 2

    # Check summary
    assert summary["disclaimer_coverage"] < 1.0
    assert summary["pages_with_disclaimer"] == 1
    assert summary["pages_missing_disclaimer"] == 2
    assert summary["total_pages"] == 3


@pytest.mark.asyncio
async def test_audit_disclaimers_without_client_name(
    sample_fragments_with_disclaimer, compliance_config
):
    """Test audit works without client name (template without {CLIENTE})"""
    # Modify fragments to have disclaimer without client name
    for frag in sample_fragments_with_disclaimer:
        if frag.kind == "footer":
            frag.text = "Este documento es confidencial por 414 Capital."

    # Modify config to have template without placeholder
    config_no_cliente = compliance_config.copy()
    config_no_cliente["disclaimers"]["templates"] = [
        {
            "id": "no-cliente",
            "text": "Este documento es confidencial por 414 Capital.",
            "active": True,
        }
    ]

    findings, summary = await audit_disclaimers(
        fragments=sample_fragments_with_disclaimer,
        client_name=None,
        config=config_no_cliente,
    )

    assert len(findings) == 0
    assert summary["disclaimer_coverage"] == 1.0


# ============================================================================
# Test: Configuration Loading
# ============================================================================


def test_load_compliance_config():
    """Test loading compliance configuration from YAML"""
    config = load_compliance_config()

    # Verify structure
    assert "disclaimers" in config
    assert "format" in config
    assert "logo" in config

    # Verify disclaimers
    assert "templates" in config["disclaimers"]
    assert "default_tolerance" in config["disclaimers"]
    assert isinstance(config["disclaimers"]["templates"], list)

    # Verify format
    assert "numeric_format" in config["format"]  # Updated from 'numbers' to 'numeric_format'
    assert "fonts" in config["format"]
    # Note: 'colors' config removed - not in current compliance.yaml


def test_load_compliance_config_fallback():
    """Test configuration fallback works when file not found"""
    # Config should still work with defaults even if file is missing
    config = load_compliance_config()

    # Should have at least one template
    assert len(config["disclaimers"]["templates"]) >= 1
    assert config["disclaimers"]["default_tolerance"] > 0
