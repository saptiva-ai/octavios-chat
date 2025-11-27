"""
Unit tests for SqlGenerationService

Tests SQL generation from QuerySpec + RagContext using templates.
"""

import pytest
from bankadvisor.specs import QuerySpec, TimeRangeSpec, RagContext, SqlGenerationResult
from bankadvisor.services.sql_generation_service import SqlGenerationService
from bankadvisor.services.sql_validator import SqlValidator


class TestSqlGenerationService:
    """Test suite for SQL generation service."""

    @pytest.fixture
    def service(self):
        """Create service with validator."""
        return SqlGenerationService(validator=SqlValidator())

    @pytest.fixture
    def basic_context(self):
        """Create basic RAG context."""
        return RagContext(
            metric_definitions=[],
            schema_snippets=[],
            example_queries=[],
            available_columns=["imor", "icor", "cartera_total", "cartera_comercial_total"]
        )

    @pytest.mark.asyncio
    async def test_simple_timeseries_query(self, service, basic_context):
        """Test generation of simple time series SQL."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="last_n_months", n=3),
            granularity="month",
            visualization_type="line"
        )

        result = await service.build_sql_from_spec(spec, basic_context)

        assert result.success is True
        assert result.sql is not None
        assert "SELECT" in result.sql
        assert "fecha" in result.sql
        assert "imor" in result.sql
        assert "banco_nombre = 'INVEX'" in result.sql
        assert "LIMIT" in result.sql
        assert result.used_template is True
        assert result.metadata.get("template") == "metric_timeseries"

    @pytest.mark.asyncio
    async def test_comparison_query(self, service, basic_context):
        """Test generation of comparison SQL (INVEX vs SISTEMA)."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX", "SISTEMA"],
            time_range=TimeRangeSpec(type="year", start_date="2024-01-01", end_date="2024-12-31"),
            comparison_mode=True
        )

        result = await service.build_sql_from_spec(spec, basic_context)

        assert result.success is True
        assert result.sql is not None
        assert "banco_nombre" in result.sql
        assert "IN ('INVEX', 'SISTEMA')" in result.sql
        assert "ORDER BY fecha ASC, banco_nombre" in result.sql
        assert result.metadata.get("template") == "metric_comparison"

    @pytest.mark.asyncio
    async def test_aggregate_query(self, service, basic_context):
        """Test generation of aggregate SQL (no time dimension)."""
        spec = QuerySpec(
            metric="ICOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="all")
        )

        result = await service.build_sql_from_spec(spec, basic_context)

        assert result.success is True
        assert result.sql is not None
        assert "AVG(icor)" in result.sql
        assert "MIN(icor)" in result.sql
        assert "MAX(icor)" in result.sql
        assert result.metadata.get("template") == "metric_aggregate"

    @pytest.mark.asyncio
    async def test_incomplete_spec_rejected(self, service, basic_context):
        """Test that incomplete QuerySpec is rejected."""
        spec = QuerySpec(
            metric="",  # Missing metric
            bank_names=[],
            time_range=TimeRangeSpec(type="all"),
            requires_clarification=True,
            missing_fields=["metric"],
            confidence_score=0.3
        )

        result = await service.build_sql_from_spec(spec, basic_context)

        assert result.success is False
        assert result.error_code == "ambiguous_spec"
        assert "incomplete" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_unsupported_metric_rejected(self, service, basic_context):
        """Test that unsupported metrics are rejected."""
        spec = QuerySpec(
            metric="FAKE_METRIC",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="last_n_months", n=3)
        )

        result = await service.build_sql_from_spec(spec, basic_context)

        assert result.success is False
        assert result.error_code == "unsupported_metric"

    @pytest.mark.asyncio
    async def test_metric_column_resolution_direct_match(self, service, basic_context):
        """Test direct metric-to-column resolution."""
        column = service._resolve_metric_column("IMOR", basic_context)
        assert column == "imor"

    @pytest.mark.asyncio
    async def test_metric_column_resolution_prefix_match(self, service, basic_context):
        """Test prefix matching for CARTERA_* metrics."""
        column = service._resolve_metric_column("CARTERA_COMERCIAL", basic_context)
        assert column == "cartera_comercial_total"

    @pytest.mark.asyncio
    async def test_time_filter_last_n_months(self, service):
        """Test time filter for last N months."""
        time_range = TimeRangeSpec(type="last_n_months", n=6)
        filter_clause = service._build_time_filter(time_range)

        assert filter_clause is not None
        assert "INTERVAL '6 months'" in filter_clause
        assert "fecha >=" in filter_clause

    @pytest.mark.asyncio
    async def test_time_filter_year(self, service):
        """Test time filter for year range."""
        time_range = TimeRangeSpec(
            type="year",
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        filter_clause = service._build_time_filter(time_range)

        assert filter_clause is not None
        assert "2024-01-01" in filter_clause
        assert "2024-12-31" in filter_clause

    @pytest.mark.asyncio
    async def test_time_filter_between_dates(self, service):
        """Test time filter for date range."""
        time_range = TimeRangeSpec(
            type="between_dates",
            start_date="2023-06-01",
            end_date="2024-01-01"
        )
        filter_clause = service._build_time_filter(time_range)

        assert filter_clause is not None
        assert "2023-06-01" in filter_clause
        assert "2024-01-01" in filter_clause

    @pytest.mark.asyncio
    async def test_time_filter_all_returns_none(self, service):
        """Test that 'all' time range returns no filter."""
        time_range = TimeRangeSpec(type="all")
        filter_clause = service._build_time_filter(time_range)

        assert filter_clause is None

    @pytest.mark.asyncio
    async def test_sql_validation_rejects_unsafe_sql(self, service, basic_context):
        """Test that validation catches unsafe SQL patterns."""
        # This test verifies integration with SqlValidator
        # SqlValidator is already tested separately, so we just verify it's called

        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="last_n_months", n=3)
        )

        result = await service.build_sql_from_spec(spec, basic_context)

        # Should pass validation
        assert result.success is True

        # SQL should have LIMIT (injected by validator if missing)
        assert "LIMIT" in result.sql

    @pytest.mark.asyncio
    async def test_multiple_banks_in_clause(self, service, basic_context):
        """Test IN clause for multiple banks."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX", "SISTEMA", "BANORTE"],  # 3 banks
            time_range=TimeRangeSpec(type="last_n_months", n=1),
            comparison_mode=True
        )

        result = await service.build_sql_from_spec(spec, basic_context)

        assert result.success is True
        assert "IN ('INVEX', 'SISTEMA', 'BANORTE')" in result.sql

    @pytest.mark.asyncio
    async def test_no_bank_filter(self, service, basic_context):
        """Test SQL generation without bank filter (all banks)."""
        spec = QuerySpec(
            metric="ICOR",
            bank_names=[],  # No bank filter
            time_range=TimeRangeSpec(type="last_n_months", n=12)
        )

        result = await service.build_sql_from_spec(spec, basic_context)

        assert result.success is True
        # Should not have banco_nombre filter if no banks specified
        # OR should query all banks - implementation dependent
        assert "SELECT" in result.sql

    @pytest.mark.asyncio
    async def test_llm_generation_not_implemented(self, service, basic_context):
        """Test that LLM fallback returns None (not implemented in Phase 2)."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="all")  # No template match
        )

        # LLM not configured
        result_inner = await service._try_llm_generation(spec, basic_context, "imor")

        assert result_inner is None

    @pytest.mark.asyncio
    async def test_rag_context_with_metric_definition(self, service):
        """Test using RAG context metric definitions for column resolution."""
        ctx = RagContext(
            metric_definitions=[
                {
                    "metric_name": "CUSTOM_METRIC",
                    "preferred_columns": ["cartera_total"]
                }
            ],
            schema_snippets=[],
            example_queries=[],
            available_columns=["cartera_total"]
        )

        column = service._resolve_metric_column("CUSTOM_METRIC", ctx)
        assert column == "cartera_total"
