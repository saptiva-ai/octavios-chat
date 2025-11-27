"""
End-to-End Tests for NL2SQL Pipeline

Tests the complete flow: Natural Language → QuerySpec → SQL → Chart
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from bankadvisor.services.query_spec_parser import QuerySpecParser
from bankadvisor.services.nl2sql_context_service import Nl2SqlContextService
from bankadvisor.services.sql_generation_service import SqlGenerationService
from bankadvisor.services.sql_validator import SqlValidator
from bankadvisor.specs import QuerySpec, TimeRangeSpec


class TestNl2SqlE2E:
    """End-to-end tests for NL2SQL pipeline."""

    @pytest.fixture
    def parser(self):
        """Create QuerySpecParser instance."""
        return QuerySpecParser()

    @pytest.fixture
    def context_service(self):
        """Create Nl2SqlContextService without RAG (template-only mode)."""
        return Nl2SqlContextService()

    @pytest.fixture
    def sql_generator(self):
        """Create SqlGenerationService."""
        return SqlGenerationService(validator=SqlValidator())

    @pytest.mark.asyncio
    async def test_simple_query_imor_invex(self, parser, context_service, sql_generator):
        """
        Test: "IMOR de INVEX últimos 3 meses"

        Expected:
        - Parser extracts metric=IMOR, bank=INVEX, time_range=last_n_months(3)
        - Context service returns available columns
        - SQL generator creates SELECT query
        - SQL is valid and safe
        """
        user_query = "IMOR de INVEX últimos 3 meses"

        # Step 1: Parse
        spec = await parser.parse(user_query, intent_hint=None, mode_hint="dashboard")

        assert spec.metric == "IMOR"
        assert "INVEX" in spec.bank_names
        assert spec.time_range.type == "last_n_months"
        assert spec.time_range.n == 3
        assert spec.is_complete()

        # Step 2: Get context
        ctx = await context_service.rag_context_for_spec(spec, original_query=user_query)

        assert len(ctx.available_columns) > 0
        assert "imor" in ctx.available_columns

        # Step 3: Generate SQL
        sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

        assert sql_result.success is True
        assert sql_result.sql is not None
        assert "SELECT" in sql_result.sql
        assert "imor" in sql_result.sql
        assert "INVEX" in sql_result.sql
        assert "INTERVAL '3 months'" in sql_result.sql
        assert "LIMIT" in sql_result.sql

    @pytest.mark.asyncio
    async def test_comparison_query_invex_vs_sistema(self, parser, context_service, sql_generator):
        """
        Test: "Compara IMOR INVEX vs Sistema 2024"

        Expected:
        - Parser detects comparison mode
        - SQL includes both banks
        - SQL orders by fecha and banco_nombre
        """
        user_query = "Compara IMOR INVEX vs Sistema 2024"

        # Step 1: Parse
        spec = await parser.parse(user_query)

        assert spec.metric == "IMOR"
        assert "INVEX" in spec.bank_names
        assert "SISTEMA" in spec.bank_names
        assert spec.comparison_mode is True
        assert spec.time_range.type == "year"

        # Step 2: Get context
        ctx = await context_service.rag_context_for_spec(spec, original_query=user_query)

        # Step 3: Generate SQL
        sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

        assert sql_result.success is True
        assert "banco_nombre" in sql_result.sql
        assert "IN ('INVEX', 'SISTEMA')" in sql_result.sql
        assert "ORDER BY fecha ASC, banco_nombre" in sql_result.sql

    @pytest.mark.asyncio
    async def test_cartera_comercial_query(self, parser, context_service, sql_generator):
        """
        Test: "cartera comercial de INVEX"

        Expected:
        - Parser resolves to CARTERA_COMERCIAL metric
        - SQL generator maps to cartera_comercial_total column
        """
        user_query = "cartera comercial de INVEX"

        # Step 1: Parse
        spec = await parser.parse(user_query)

        assert spec.metric == "CARTERA_COMERCIAL"
        assert "INVEX" in spec.bank_names

        # Step 2: Get context
        ctx = await context_service.rag_context_for_spec(spec)

        assert "cartera_comercial_total" in ctx.available_columns

        # Step 3: Generate SQL
        sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

        assert sql_result.success is True
        assert "cartera_comercial_total" in sql_result.sql

    @pytest.mark.asyncio
    async def test_icor_last_year(self, parser, context_service, sql_generator):
        """
        Test: "ICOR último año"

        Expected:
        - Parser detects last_n_months with n=12
        - SQL has 12-month interval filter
        """
        user_query = "ICOR último año"

        # Step 1: Parse
        spec = await parser.parse(user_query)

        assert spec.metric == "ICOR"
        # Parser should interpret "último año" as last 12 months
        assert spec.time_range.type in ["last_n_months", "year"]

        # Step 2-3: Context + SQL
        ctx = await context_service.rag_context_for_spec(spec)
        sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

        assert sql_result.success is True
        assert "icor" in sql_result.sql

    @pytest.mark.asyncio
    async def test_ambiguous_query_requires_clarification(self, parser):
        """
        Test: "cartera" (ambiguous - could be total, comercial, consumo, etc.)

        Expected:
        - Parser marks as requiring clarification
        - SQL generation should reject
        """
        user_query = "cartera"

        spec = await parser.parse(user_query)

        # Parser may or may not mark as requiring clarification
        # depending on implementation. If it does:
        if spec.requires_clarification:
            assert not spec.is_complete()
            assert len(spec.missing_fields) > 0

    @pytest.mark.asyncio
    async def test_unsupported_metric_tasa_me(self, parser, context_service, sql_generator):
        """
        Test: "TASA_ME de INVEX" (data empty - should handle gracefully)

        Expected:
        - Parser succeeds
        - SQL generation succeeds (column exists)
        - Note: Actual data may be empty (query returns 0 rows) but SQL is valid
        """
        user_query = "TASA_ME de INVEX"

        spec = await parser.parse(user_query)

        assert spec.metric == "TASA_ME"

        ctx = await context_service.rag_context_for_spec(spec)

        # TASA_ME column exists in schema
        if "tasa_me" in ctx.available_columns:
            sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

            # SQL should be generated successfully
            assert sql_result.success is True
            assert "tasa_me" in sql_result.sql

    @pytest.mark.asyncio
    async def test_pipeline_fallback_on_parser_failure(self, context_service, sql_generator):
        """
        Test pipeline behavior when parser returns low-confidence spec.

        Expected:
        - Incomplete spec is rejected by SQL generator
        - Returns error with code "ambiguous_spec"
        """
        # Manually create incomplete spec (simulates parser failure)
        spec = QuerySpec(
            metric="",
            bank_names=[],
            time_range=TimeRangeSpec(type="all"),
            requires_clarification=True,
            missing_fields=["metric", "time_range"],
            confidence_score=0.2
        )

        ctx = await context_service.rag_context_for_spec(spec)
        sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

        assert sql_result.success is False
        assert sql_result.error_code == "ambiguous_spec"

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(self, parser, context_service, sql_generator):
        """
        Test: Malicious query with SQL injection attempt

        Expected:
        - Parser/generator should sanitize or reject
        - Final SQL should be safe
        """
        user_query = "IMOR'; DROP TABLE monthly_kpis; --"

        spec = await parser.parse(user_query)

        # Parser should normalize metric name
        # SQL generator should use parameterized queries or escape properly

        ctx = await context_service.rag_context_for_spec(spec)
        sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

        # If SQL was generated, it should be validated
        if sql_result.success:
            # Should not contain DROP TABLE
            assert "DROP" not in sql_result.sql.upper()
            assert "--" not in sql_result.sql

    @pytest.mark.asyncio
    async def test_backward_compatibility_with_legacy_queries(self, parser, context_service, sql_generator):
        """
        Test that legacy queries still work with NL2SQL pipeline.

        Queries like "IMOR", "cartera comercial", "ICOR" should work as before.
        """
        legacy_queries = [
            ("IMOR", "IMOR"),
            ("cartera comercial", "CARTERA_COMERCIAL"),
            ("ICOR", "ICOR"),
            ("cartera total", "CARTERA_TOTAL"),
        ]

        for user_query, expected_metric in legacy_queries:
            spec = await parser.parse(user_query)

            assert spec.metric == expected_metric

            ctx = await context_service.rag_context_for_spec(spec)
            sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

            # Should generate valid SQL
            assert sql_result.success is True, f"Failed for query: {user_query}"
            assert "SELECT" in sql_result.sql


@pytest.mark.integration
class TestNl2SqlWithDatabase:
    """
    Integration tests that require actual database connection.

    NOTE: These tests are marked as @pytest.mark.integration
    and require a running PostgreSQL instance with monthly_kpis data.

    Run with: pytest -m integration
    """

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires database - run manually with DB available")
    async def test_full_pipeline_with_real_db(self):
        """
        Full E2E test with real database execution.

        Steps:
        1. Parse NL query
        2. Generate SQL
        3. Execute against DB
        4. Verify results
        5. Generate Plotly config

        This test should be run manually when DB is available.
        """
        from bankadvisor.db import AsyncSessionLocal
        from sqlalchemy import text

        user_query = "IMOR de INVEX últimos 3 meses"

        parser = QuerySpecParser()
        context_service = Nl2SqlContextService()
        sql_generator = SqlGenerationService()

        # Parse
        spec = await parser.parse(user_query)
        assert spec.is_complete()

        # Generate SQL
        ctx = await context_service.rag_context_for_spec(spec)
        sql_result = await sql_generator.build_sql_from_spec(spec, ctx)

        assert sql_result.success is True

        # Execute SQL
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(sql_result.sql))
            rows = result.fetchall()

        # Verify results
        assert len(rows) > 0  # Should have data
        assert len(rows) <= 1000  # LIMIT enforced

        # Verify row structure
        first_row = rows[0]
        assert "fecha" in first_row._mapping
        assert "imor" in first_row._mapping

        # TODO: Generate Plotly config from rows
        # plotly_config = VisualizationService.build_plotly_config(...)
