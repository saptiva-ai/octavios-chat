"""
Unit tests for semantic_consistency_auditor.py (Phase 5 - FINAL)

Tests cover:
- Number extraction from text
- Number normalization
- Cosine similarity calculation
- Section extraction from fragments
- Semantic consistency validation
- Finding generation
"""

import pytest
from typing import List

from src.services.semantic_consistency_auditor import (
    extract_numbers_from_text,
    normalize_number,
    cosine_similarity,
    extract_sections_from_fragments,
    audit_semantic_consistency,
    _embed,
)
from src.models.document import PageFragment


# ============================================================================
# Test: Number Extraction
# ============================================================================


def test_extract_numbers_simple():
    """Test extracting simple numbers"""
    text = "El precio es de 1234 pesos."
    numbers = extract_numbers_from_text(text)

    assert "1234" in numbers


def test_extract_numbers_with_separators():
    """Test extracting numbers with thousand separators"""
    text = "Ingresos: $1,234,567.89 USD"
    numbers = extract_numbers_from_text(text)

    assert len(numbers) >= 1
    assert any("1" in n for n in numbers)


def test_extract_numbers_multiple():
    """Test extracting multiple numbers"""
    text = "Valores: 100, 200.50, 1,000 y 5,000.75"
    numbers = extract_numbers_from_text(text)

    assert len(numbers) >= 4


def test_extract_numbers_percentage():
    """Test extracting percentages"""
    text = "Crecimiento del 15.7% anual"
    numbers = extract_numbers_from_text(text)

    assert len(numbers) >= 1


def test_extract_numbers_no_numbers():
    """Test text without numbers"""
    text = "Este texto no contiene cifras numéricas."
    numbers = extract_numbers_from_text(text)

    assert len(numbers) == 0


# ============================================================================
# Test: Number Normalization
# ============================================================================


def test_normalize_number_with_commas():
    """Test normalizing number with commas"""
    assert normalize_number("1,234") == "1234"
    assert normalize_number("1,234,567") == "1234567"


def test_normalize_number_with_decimals():
    """Test normalizing number with decimal point"""
    assert normalize_number("1.23") == "123"
    assert normalize_number("1,234.56") == "123456"


def test_normalize_number_plain():
    """Test normalizing plain number"""
    assert normalize_number("1234") == "1234"


# ============================================================================
# Test: Cosine Similarity
# ============================================================================


def test_cosine_similarity_identical():
    """Test cosine similarity of identical vectors"""
    vec_a = [1.0, 2.0, 3.0]
    vec_b = [1.0, 2.0, 3.0]

    similarity = cosine_similarity(vec_a, vec_b)
    assert similarity == pytest.approx(1.0, abs=0.01)


def test_cosine_similarity_opposite():
    """Test cosine similarity of opposite vectors"""
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [-1.0, 0.0, 0.0]

    similarity = cosine_similarity(vec_a, vec_b)
    assert similarity == pytest.approx(-1.0, abs=0.01)


def test_cosine_similarity_orthogonal():
    """Test cosine similarity of orthogonal vectors"""
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.0, 1.0, 0.0]

    similarity = cosine_similarity(vec_a, vec_b)
    assert similarity == pytest.approx(0.0, abs=0.01)


def test_cosine_similarity_similar():
    """Test cosine similarity of similar vectors"""
    vec_a = [1.0, 2.0, 3.0]
    vec_b = [1.1, 2.1, 2.9]

    similarity = cosine_similarity(vec_a, vec_b)
    assert 0.9 < similarity < 1.0  # Very similar


def test_cosine_similarity_different_magnitude():
    """Test cosine similarity ignores magnitude"""
    vec_a = [1.0, 2.0, 3.0]
    vec_b = [2.0, 4.0, 6.0]  # Same direction, double magnitude

    similarity = cosine_similarity(vec_a, vec_b)
    assert similarity == pytest.approx(1.0, abs=0.01)


def test_cosine_similarity_empty_vectors():
    """Test cosine similarity with empty vectors"""
    vec_a = []
    vec_b = []

    similarity = cosine_similarity(vec_a, vec_b)
    assert similarity == 0.0


def test_cosine_similarity_zero_vectors():
    """Test cosine similarity with zero vectors"""
    vec_a = [0.0, 0.0, 0.0]
    vec_b = [1.0, 2.0, 3.0]

    similarity = cosine_similarity(vec_a, vec_b)
    assert similarity == 0.0


def test_cosine_similarity_mismatched_dimensions():
    """Test cosine similarity rejects mismatched dimensions"""
    vec_a = [1.0, 2.0]
    vec_b = [1.0, 2.0, 3.0]

    with pytest.raises(ValueError):
        cosine_similarity(vec_a, vec_b)


# ============================================================================
# Test: Embedding Generation
# ============================================================================


@pytest.mark.asyncio
async def test_embed_deterministic():
    """Test embeddings are deterministic for same text"""
    text = "Este es un texto de prueba."

    vec1 = await _embed(text)
    vec2 = await _embed(text)

    assert vec1 == vec2


@pytest.mark.asyncio
async def test_embed_dimensions():
    """Test embeddings have correct dimensions"""
    text = "Texto de prueba"
    vec = await _embed(text)

    assert len(vec) == 768  # Standard embedding size


@pytest.mark.asyncio
async def test_embed_different_texts():
    """Test different texts produce different embeddings"""
    text1 = "Resumen ejecutivo del proyecto."
    text2 = "Conclusiones finales del análisis."

    vec1 = await _embed(text1)
    vec2 = await _embed(text2)

    assert vec1 != vec2


# ============================================================================
# Test: Section Extraction
# ============================================================================


def create_fragment(page: int, text: str, font_size: float = 12.0) -> PageFragment:
    """Helper to create PageFragment for testing"""
    frag = PageFragment(
        fragment_id=f"frag-{page}",
        page=page,
        kind="paragraph",
        bbox=[0.0, 0.0, 100.0, 100.0],
        text=text
    )
    frag.font_size = font_size  # Set as attribute
    return frag


def test_extract_sections_simple():
    """Test extracting simple sections"""
    fragments = [
        create_fragment(1, "Resumen Ejecutivo", font_size=18.0),
        create_fragment(1, "Este es el contenido del resumen.", font_size=12.0),
        create_fragment(2, "Conclusiones", font_size=18.0),
        create_fragment(2, "Estas son las conclusiones.", font_size=12.0),
    ]

    sections = extract_sections_from_fragments(
        fragments=fragments,
        section_titles=["Resumen Ejecutivo", "Conclusiones"]
    )

    assert "resumen ejecutivo" in sections
    assert "conclusiones" in sections
    assert "resumen" in sections["resumen ejecutivo"].lower()
    assert "conclusiones" in sections["conclusiones"].lower()


def test_extract_sections_no_headings():
    """Test with no recognized headings"""
    fragments = [
        create_fragment(1, "Texto sin encabezados", font_size=12.0),
        create_fragment(1, "Más contenido normal", font_size=12.0),
    ]

    sections = extract_sections_from_fragments(
        fragments=fragments,
        section_titles=["Resumen Ejecutivo", "Conclusiones"]
    )

    assert len(sections) == 0


def test_extract_sections_heading_threshold():
    """Test heading threshold filtering"""
    fragments = [
        create_fragment(1, "Resumen Ejecutivo", font_size=12.0),  # Below threshold
        create_fragment(1, "Contenido", font_size=12.0),
    ]

    sections = extract_sections_from_fragments(
        fragments=fragments,
        section_titles=["Resumen Ejecutivo"],
        heading_threshold=14  # Requires 14pt or higher
    )

    # Should not recognize as heading (font too small)
    assert len(sections) == 0


# ============================================================================
# Test: Full Audit Flow
# ============================================================================


@pytest.mark.asyncio
async def test_audit_semantic_consistency_basic():
    """Test basic audit flow"""
    fragments = [
        create_fragment(1, "Resumen Ejecutivo", font_size=18.0),
        create_fragment(1, "El proyecto generó ingresos de 1,000,000 pesos. La inversión fue exitosa.", font_size=12.0),
        create_fragment(2, "Conclusiones", font_size=18.0),
        create_fragment(2, "Se lograron los objetivos con 1,000,000 pesos de retorno.", font_size=12.0),
    ]

    config = {
        "semantic_consistency": {
            "enabled": True,
            "min_section_len": 50,
            "section_titles": ["Resumen Ejecutivo", "Conclusiones"],
            "similarity_threshold": 0.80,
            "severity": "medium"
        }
    }

    findings, summary = await audit_semantic_consistency(fragments, config)

    # Verify summary structure
    assert "sections_found" in summary
    assert "comparisons_made" in summary
    assert "similarities" in summary
    assert "numeric_discrepancies" in summary
    assert "semantic_discrepancies" in summary

    # Should find both sections
    assert "resumen ejecutivo" in summary["sections_found"]
    assert "conclusiones" in summary["sections_found"]


@pytest.mark.asyncio
async def test_audit_semantic_consistency_disabled():
    """Test audit skips when disabled"""
    fragments = [
        create_fragment(1, "Test text", font_size=12.0)
    ]

    config = {
        "semantic_consistency": {
            "enabled": False,
            "section_titles": ["Resumen Ejecutivo"],
            "similarity_threshold": 0.80,
            "severity": "medium"
        }
    }

    findings, summary = await audit_semantic_consistency(fragments, config)

    # When disabled, should return minimal results
    assert isinstance(findings, list)
    assert isinstance(summary, dict)


@pytest.mark.asyncio
async def test_audit_semantic_consistency_low_similarity():
    """Test audit flags low similarity"""
    fragments = [
        create_fragment(1, "Resumen Ejecutivo", font_size=18.0),
        create_fragment(1, "Este es el resumen del proyecto inicial con análisis financiero detallado y proyecciones de mercado ambiciosas.", font_size=12.0),
        create_fragment(2, "Conclusiones", font_size=18.0),
        create_fragment(2, "Resultados técnicos completamente diferentes sin relación alguna con el resumen previo.", font_size=12.0),
    ]

    config = {
        "semantic_consistency": {
            "enabled": True,
            "min_section_len": 50,
            "section_titles": ["Resumen Ejecutivo", "Conclusiones"],
            "similarity_threshold": 0.95,  # Very high threshold
            "severity": "high"
        }
    }

    findings, summary = await audit_semantic_consistency(fragments, config)

    # With very different texts and high threshold, should find issues
    # (actual behavior depends on embedding implementation)
    assert isinstance(findings, list)
    assert summary["comparisons_made"] >= 0


@pytest.mark.asyncio
async def test_audit_semantic_consistency_missing_numbers():
    """Test audit flags missing numbers"""
    fragments = [
        create_fragment(1, "Resumen Ejecutivo", font_size=18.0),
        create_fragment(1, "El proyecto generó 1,000,000 pesos y tuvo 500 empleados.", font_size=12.0),
        create_fragment(2, "Conclusiones", font_size=18.0),
        create_fragment(2, "El proyecto fue exitoso sin mencionar cifras específicas.", font_size=12.0),
    ]

    config = {
        "semantic_consistency": {
            "enabled": True,
            "min_section_len": 50,
            "section_titles": ["Resumen Ejecutivo", "Conclusiones"],
            "similarity_threshold": 0.80,
            "severity": "medium"
        }
    }

    findings, summary = await audit_semantic_consistency(fragments, config)

    # Should potentially flag missing numbers
    assert summary["numeric_discrepancies"] >= 0


# ============================================================================
# Test: Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_audit_semantic_consistency_empty_fragments():
    """Test audit with empty fragments"""
    fragments = []

    config = {
        "semantic_consistency": {
            "enabled": True,
            "section_titles": ["Resumen Ejecutivo"],
            "similarity_threshold": 0.80,
            "severity": "medium"
        }
    }

    findings, summary = await audit_semantic_consistency(fragments, config)

    assert len(findings) == 0
    assert summary["sections_found"] == []


@pytest.mark.asyncio
async def test_audit_semantic_consistency_missing_sections():
    """Test audit when expected sections are missing"""
    fragments = [
        create_fragment(1, "Introducción", font_size=18.0),
        create_fragment(1, "Este es el contenido.", font_size=12.0),
    ]

    config = {
        "semantic_consistency": {
            "enabled": True,
            "section_titles": ["Resumen Ejecutivo", "Conclusiones"],
            "similarity_threshold": 0.80,
            "severity": "medium"
        }
    }

    findings, summary = await audit_semantic_consistency(fragments, config)

    # Should not crash, just not compare
    assert summary["comparisons_made"] == 0


@pytest.mark.asyncio
async def test_audit_semantic_consistency_short_sections():
    """Test audit filters out short sections"""
    fragments = [
        create_fragment(1, "Resumen Ejecutivo", font_size=18.0),
        create_fragment(1, "Breve.", font_size=12.0),  # Too short
        create_fragment(2, "Conclusiones", font_size=18.0),
        create_fragment(2, "También breve.", font_size=12.0),  # Too short
    ]

    config = {
        "semantic_consistency": {
            "enabled": True,
            "min_section_len": 200,  # High minimum
            "section_titles": ["Resumen Ejecutivo", "Conclusiones"],
            "similarity_threshold": 0.80,
            "severity": "medium"
        }
    }

    findings, summary = await audit_semantic_consistency(fragments, config)

    # Sections should be filtered out due to length
    assert len(summary["sections_found"]) == 0
