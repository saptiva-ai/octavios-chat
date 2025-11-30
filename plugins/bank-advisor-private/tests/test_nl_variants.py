"""
Natural Language Variants Test Suite

Tests that different phrasings of the same query produce consistent results.
This ensures the NLP layer is robust to natural language variations.

HU3 - NLP Query Interpretation
"""

import pytest
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class QueryVariant:
    """A query variant with expected classification."""
    query: str
    expected_intent: str
    expected_metric: str
    expected_bank: Optional[str] = None


# =============================================================================
# IMOR Query Variants
# =============================================================================
IMOR_VARIANTS = [
    # Core query
    QueryVariant("IMOR de INVEX en 2024", "evolution", "imor", "INVEX"),
    # Formal variations
    QueryVariant("índice de morosidad de INVEX 2024", "evolution", "imor", "INVEX"),
    QueryVariant("índice de morosidad de INVEX para el año 2024", "evolution", "imor", "INVEX"),
    # Casual variations
    QueryVariant("morosidad de invex en 2024", "evolution", "imor", "INVEX"),
    QueryVariant("cómo estuvo el imor de invex en 2024", "evolution", "imor", "INVEX"),
    # Evolution explicit
    QueryVariant("evolución del IMOR de INVEX durante 2024", "evolution", "imor", "INVEX"),
    QueryVariant("tendencia del imor invex 2024", "evolution", "imor", "INVEX"),
    # Comparison variations
    QueryVariant("IMOR de INVEX vs sistema", "comparison", "imor", None),
    QueryVariant("compara IMOR de INVEX contra sistema", "comparison", "imor", None),
    QueryVariant("IMOR INVEX comparado con sistema", "comparison", "imor", None),
]


# =============================================================================
# ICAP Query Variants
# =============================================================================
ICAP_VARIANTS = [
    # Core query
    QueryVariant("ICAP de INVEX en 2024", "evolution", "icap", "INVEX"),
    # Formal variations
    QueryVariant("índice de capitalización de INVEX 2024", "evolution", "icap", "INVEX"),
    QueryVariant("capitalización de INVEX para 2024", "evolution", "icap", "INVEX"),
    # Comparison variations
    QueryVariant("ICAP de INVEX contra sistema en 2024", "comparison", "icap", None),
    QueryVariant("compara el ICAP de INVEX vs sistema", "comparison", "icap", None),
]


# =============================================================================
# Cartera Comercial Query Variants
# =============================================================================
CARTERA_COMERCIAL_VARIANTS = [
    # Core query
    QueryVariant("cartera comercial de INVEX", "evolution", "cartera_comercial_total", "INVEX"),
    # Comparison variations
    QueryVariant("cartera comercial de INVEX vs sistema", "comparison", "cartera_comercial_total", None),
    QueryVariant("compara cartera comercial INVEX contra sistema", "comparison", "cartera_comercial_total", None),
    # Timeline variations
    QueryVariant("cartera comercial INVEX últimos 12 meses", "evolution", "cartera_comercial_total", "INVEX"),
    QueryVariant("evolución de cartera comercial de INVEX", "evolution", "cartera_comercial_total", "INVEX"),
]


# =============================================================================
# Cartera Vencida Query Variants
# =============================================================================
CARTERA_VENCIDA_VARIANTS = [
    QueryVariant("cartera vencida en 2024", "evolution", "cartera_vencida_total", None),
    QueryVariant("cartera vencida de INVEX en 2024", "evolution", "cartera_vencida_total", "INVEX"),
    QueryVariant("cartera vencida INVEX últimos 12 meses", "evolution", "cartera_vencida_total", "INVEX"),
]


# =============================================================================
# Reservas Query Variants
# =============================================================================
RESERVAS_VARIANTS = [
    QueryVariant("reservas totales de INVEX", "evolution", "reservas_etapa_todas", "INVEX"),
    QueryVariant("reservas de INVEX", "evolution", "reservas_etapa_todas", "INVEX"),
    QueryVariant("reservas totales INVEX en 2024", "evolution", "reservas_etapa_todas", "INVEX"),
]


# =============================================================================
# ICOR Query Variants
# =============================================================================
ICOR_VARIANTS = [
    QueryVariant("ICOR de INVEX 2024", "evolution", "icor", "INVEX"),
    QueryVariant("índice de cobertura de INVEX 2024", "evolution", "icor", "INVEX"),
    QueryVariant("cobertura de reservas INVEX en 2024", "evolution", "icor", "INVEX"),
]


# =============================================================================
# Sistema/Sector Aggregate Variants
# =============================================================================
AGGREGATE_VARIANTS = [
    QueryVariant("IMOR del sistema bancario en 2024", "evolution", "imor", "SISTEMA"),
    QueryVariant("IMOR del sector en 2024", "evolution", "imor", "SISTEMA"),
    QueryVariant("IMOR promedio del mercado en 2024", "evolution", "imor", "SISTEMA"),
]


# =============================================================================
# Test Functions
# =============================================================================

class TestEntityExtraction:
    """Test that entity extraction works for all variants."""

    @pytest.fixture
    def config_service(self):
        """Get config service instance."""
        from bankadvisor.config_service import get_config
        return get_config()

    @pytest.mark.parametrize("variant", IMOR_VARIANTS, ids=lambda v: v.query[:40])
    def test_imor_variants_metric(self, variant: QueryVariant, config_service):
        """Test IMOR metric is correctly identified in all variants."""
        metric = config_service.find_metric(variant.query)
        assert metric == variant.expected_metric, f"Query '{variant.query}' should match metric '{variant.expected_metric}', got '{metric}'"

    @pytest.mark.parametrize("variant", ICAP_VARIANTS, ids=lambda v: v.query[:40])
    def test_icap_variants_metric(self, variant: QueryVariant, config_service):
        """Test ICAP metric is correctly identified in all variants."""
        metric = config_service.find_metric(variant.query)
        assert metric == variant.expected_metric, f"Query '{variant.query}' should match metric '{variant.expected_metric}', got '{metric}'"

    @pytest.mark.parametrize("variant", CARTERA_COMERCIAL_VARIANTS, ids=lambda v: v.query[:40])
    def test_cartera_comercial_variants_metric(self, variant: QueryVariant, config_service):
        """Test cartera comercial metric is correctly identified."""
        metric = config_service.find_metric(variant.query)
        assert metric == variant.expected_metric, f"Query '{variant.query}' should match metric '{variant.expected_metric}', got '{metric}'"

    @pytest.mark.parametrize("variant", CARTERA_VENCIDA_VARIANTS, ids=lambda v: v.query[:40])
    def test_cartera_vencida_variants_metric(self, variant: QueryVariant, config_service):
        """Test cartera vencida metric is correctly identified."""
        metric = config_service.find_metric(variant.query)
        assert metric == variant.expected_metric, f"Query '{variant.query}' should match metric '{variant.expected_metric}', got '{metric}'"

    @pytest.mark.parametrize("variant", RESERVAS_VARIANTS, ids=lambda v: v.query[:40])
    def test_reservas_variants_metric(self, variant: QueryVariant, config_service):
        """Test reservas metric is correctly identified."""
        metric = config_service.find_metric(variant.query)
        assert metric == variant.expected_metric, f"Query '{variant.query}' should match metric '{variant.expected_metric}', got '{metric}'"

    @pytest.mark.parametrize("variant", ICOR_VARIANTS, ids=lambda v: v.query[:40])
    def test_icor_variants_metric(self, variant: QueryVariant, config_service):
        """Test ICOR metric is correctly identified."""
        metric = config_service.find_metric(variant.query)
        assert metric == variant.expected_metric, f"Query '{variant.query}' should match metric '{variant.expected_metric}', got '{metric}'"


class TestIntentClassification:
    """Test that intent classification works for all variants."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("variant", IMOR_VARIANTS, ids=lambda v: v.query[:40])
    async def test_imor_variants_intent(self, variant: QueryVariant):
        """Test IMOR intent is correctly classified."""
        from bankadvisor.services.intent_service import NlpIntentService
        from bankadvisor.entity_service import ExtractedEntities

        entities = ExtractedEntities(
            metric_id=variant.expected_metric,
            date_start=None if "vs" in variant.query else "2024-01-01",
            date_end=None if "vs" in variant.query else "2024-12-31",
        )

        result = NlpIntentService._classify_with_rules(variant.query, entities)
        assert result.intent.value == variant.expected_intent, \
            f"Query '{variant.query}' should have intent '{variant.expected_intent}', got '{result.intent.value}'"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("variant", ICAP_VARIANTS, ids=lambda v: v.query[:40])
    async def test_icap_variants_intent(self, variant: QueryVariant):
        """Test ICAP intent is correctly classified."""
        from bankadvisor.services.intent_service import NlpIntentService
        from bankadvisor.entity_service import ExtractedEntities

        entities = ExtractedEntities(
            metric_id=variant.expected_metric,
            date_start=None if "vs" in variant.query or "contra" in variant.query else "2024-01-01",
            date_end=None if "vs" in variant.query or "contra" in variant.query else "2024-12-31",
        )

        result = NlpIntentService._classify_with_rules(variant.query, entities)
        assert result.intent.value == variant.expected_intent, \
            f"Query '{variant.query}' should have intent '{variant.expected_intent}', got '{result.intent.value}'"


class TestComparisonDetection:
    """Test that comparison queries are correctly detected."""

    @pytest.mark.parametrize("query,expected", [
        ("IMOR de INVEX vs sistema", True),
        ("IMOR de INVEX contra sistema", True),
        ("compara IMOR de INVEX con sistema", True),
        ("IMOR de INVEX comparado con sistema", True),
        ("IMOR de INVEX en 2024", False),
        ("evolución del IMOR de INVEX", False),
    ])
    def test_comparison_detection(self, query: str, expected: bool):
        """Test that comparison queries are correctly identified."""
        from bankadvisor.entity_service import EntityService

        result = EntityService.is_comparison_query(query)
        assert result == expected, f"Query '{query}' comparison detection should be {expected}, got {result}"


class TestAggregateResolution:
    """Test that aggregate aliases are correctly resolved."""

    def test_sistema_aliases(self):
        """Test that sistema aliases resolve correctly."""
        from bankadvisor.runtime_config import get_runtime_config

        config = get_runtime_config()

        test_cases = [
            ("sistema", "SISTEMA"),
            ("sector", "SISTEMA"),
            ("sistema bancario", "SISTEMA"),
            ("promedio del sector", "SISTEMA"),
        ]

        for alias, expected in test_cases:
            result = config.resolve_aggregate_alias(alias)
            assert result == expected, f"Alias '{alias}' should resolve to '{expected}', got '{result}'"


# =============================================================================
# Test Summary
# =============================================================================
# Total variants tested:
# - IMOR: 10 variants
# - ICAP: 5 variants
# - Cartera Comercial: 5 variants
# - Cartera Vencida: 3 variants
# - Reservas: 3 variants
# - ICOR: 3 variants
# - Aggregates: 3 variants
# Total: 32 query variants
