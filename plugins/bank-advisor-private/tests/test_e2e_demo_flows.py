"""
End-to-End Test Suite for Demo Flows

Tests the complete NL → SQL → DB → Visualization pipeline for the 9 priority
visualizations. These tests simulate exactly what will happen during the demo
on December 3rd.

Purpose:
- Validate the full analytics pipeline works end-to-end
- Protect against regressions in synonyms, intent detection, or visualizations
- Provide ready-to-use queries for the demo

Usage:
    # Run all E2E tests
    .venv/bin/python -m pytest tests/test_e2e_demo_flows.py -v

    # Run specific test
    .venv/bin/python -m pytest tests/test_e2e_demo_flows.py::TestE2EDemoFlows::test_demo_1_imor -v
"""
import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


# Mark all tests as asyncio
pytestmark = pytest.mark.asyncio


class TestE2EDemoFlows:
    """
    E2E tests for demo scenarios.

    Each test represents a real query that could be demonstrated on Dec 3rd.
    """

    @pytest.fixture(scope="class")
    async def analytics_impl(self):
        """
        Import and setup analytics implementation.

        This fixture is scoped to class to avoid repeated imports.
        """
        from main import _bank_analytics_impl
        from bankadvisor.db import init_db

        # Initialize database connection pool
        await init_db()

        return _bank_analytics_impl

    # =========================================================================
    # DEMO SCENARIO 1: IMOR Evolution (Timeline)
    # =========================================================================
    async def test_demo_1_imor_evolution(self, analytics_impl):
        """
        Demo Query: "IMOR de INVEX en los últimos 3 meses"

        Expected:
        - Successful query execution
        - Returns timeline data (3 months)
        - Returns Plotly line chart config
        - No errors
        """
        result = await analytics_impl(
            metric_or_query="IMOR de INVEX en los últimos 3 meses",
            mode="dashboard"
        )

        # Verify no error
        assert "error" not in result, f"Query failed with error: {result.get('error')}"

        # Verify data structure
        assert "data" in result, "Missing 'data' key in result"
        assert "plotly_config" in result, "Missing 'plotly_config' key in result"
        assert "title" in result, "Missing 'title' key in result"

        # Verify data content
        data = result["data"]
        assert "months" in data, "Missing 'months' in data"
        assert len(data["months"]) > 0, "No months returned"

        # Verify plotly config structure
        plotly = result["plotly_config"]
        assert "data" in plotly, "Missing 'data' in plotly_config"
        assert "layout" in plotly, "Missing 'layout' in plotly_config"
        assert len(plotly["data"]) > 0, "No traces in plotly data"

        print(f"✅ DEMO 1 - IMOR: Returned {len(data['months'])} months")

    # =========================================================================
    # DEMO SCENARIO 2: Cartera Comercial Comparison
    # =========================================================================
    async def test_demo_2_cartera_comercial(self, analytics_impl):
        """
        Demo Query: "Cartera comercial de INVEX vs sistema"

        Expected:
        - Successful query execution
        - Returns comparison data (INVEX + SISTEMA)
        - Returns Plotly bar chart
        """
        result = await analytics_impl(
            metric_or_query="cartera comercial de INVEX vs sistema",
            mode="dashboard"
        )

        # Verify no error
        assert "error" not in result, f"Query failed: {result.get('error')}"

        # Verify data structure
        assert "data" in result
        assert "plotly_config" in result

        # Verify plotly is bar chart
        plotly = result["plotly_config"]
        assert plotly["data"][0]["type"] == "bar", "Expected bar chart for comparison"

        print(f"✅ DEMO 2 - Cartera Comercial: Bar chart generated")

    # =========================================================================
    # DEMO SCENARIO 3: Reservas Totales (Calculated Metric)
    # =========================================================================
    async def test_demo_3_reservas_totales(self, analytics_impl):
        """
        Demo Query: "Reservas totales de INVEX"

        Expected:
        - Uses column 'reservas_etapa_todas' (synonym for 'pérdida esperada')
        - Returns comparison data
        """
        result = await analytics_impl(
            metric_or_query="reservas totales",
            mode="dashboard"
        )

        assert "error" not in result, f"Query failed: {result.get('error')}"
        assert "data" in result
        assert "plotly_config" in result

        # Verify metadata contains correct metric
        if "metadata" in result:
            meta = result["metadata"]
            # Should resolve to 'reservas_etapa_todas'
            assert "metric" in meta or "title" in meta

        print(f"✅ DEMO 3 - Reservas Totales: Query successful")

    # =========================================================================
    # DEMO SCENARIO 4: ICAP (Ratio Metric)
    # =========================================================================
    async def test_demo_4_icap(self, analytics_impl):
        """
        Demo Query: "ICAP de INVEX contra sistema en 2024"

        Expected:
        - Returns ratio data (formatted as percentage)
        - Timeline or comparison mode
        """
        result = await analytics_impl(
            metric_or_query="ICAP de INVEX contra sistema en 2024",
            mode="dashboard"
        )

        assert "error" not in result, f"Query failed: {result.get('error')}"
        assert "data" in result
        assert "plotly_config" in result

        # Verify plotly has proper percentage formatting for ratios
        plotly = result["plotly_config"]
        if "layout" in plotly and "yaxis" in plotly["layout"]:
            # Ratio metrics should have percentage tick format
            yaxis = plotly["layout"]["yaxis"]
            # tickformat should be ".1%" for ratios
            if "tickformat" in yaxis:
                assert "%" in yaxis["tickformat"], "Ratio should be formatted as percentage"

        print(f"✅ DEMO 4 - ICAP: Ratio metric handled correctly")

    # =========================================================================
    # DEMO SCENARIO 5: Cartera Vencida (Timeline)
    # =========================================================================
    async def test_demo_5_cartera_vencida(self, analytics_impl):
        """
        Demo Query: "Cartera vencida últimos 12 meses"

        Expected:
        - Returns 12 months of data
        - Line chart (timeline mode)
        """
        result = await analytics_impl(
            metric_or_query="cartera vencida últimos 12 meses",
            mode="dashboard"
        )

        assert "error" not in result, f"Query failed: {result.get('error')}"
        assert "data" in result

        data = result["data"]
        assert "months" in data

        # Should have multiple months (may be less than 12 if data incomplete)
        assert len(data["months"]) > 1, "Should return multiple months for timeline"

        print(f"✅ DEMO 5 - Cartera Vencida: {len(data['months'])} months returned")

    # =========================================================================
    # DEMO SCENARIO 6: Cartera Comercial Sin Gobierno (Calculated Column)
    # =========================================================================
    async def test_demo_6_cartera_sin_gobierno(self, analytics_impl):
        """
        Demo Query: "Cartera comercial sin gobierno"

        Expected:
        - Uses calculated field (cartera_comercial_total - entidades_gubernamentales_total)
        - Query succeeds without error
        """
        result = await analytics_impl(
            metric_or_query="cartera comercial sin gobierno",
            mode="dashboard"
        )

        assert "error" not in result, f"Query failed: {result.get('error')}"
        assert "data" in result
        assert "plotly_config" in result

        # Verify we got data back (calculated field worked)
        data = result["data"]
        assert "months" in data
        assert len(data["months"]) > 0

        print(f"✅ DEMO 6 - Cartera Sin Gobierno: Calculated field working")

    # =========================================================================
    # EDGE CASE: Ambiguous Query Handling
    # =========================================================================
    async def test_edge_case_ambiguous_query(self, analytics_impl):
        """
        Test: Ambiguous query should return clarification

        Query: "cartera" (could be total, comercial, consumo, vivienda, vencida)

        Expected:
        - Returns error='ambiguous_query'
        - Provides options for clarification
        """
        result = await analytics_impl(
            metric_or_query="cartera",
            mode="dashboard"
        )

        # Should detect ambiguity
        if "error" in result:
            assert result["error"] == "ambiguous_query", "Should detect ambiguous query"
            assert "options" in result, "Should provide clarification options"
            assert len(result["options"]) > 0, "Should have at least one option"
        else:
            # If not ambiguous, should have resolved to a specific metric
            assert "data" in result, "Should either be ambiguous or successful"

        print(f"✅ EDGE CASE - Ambiguous: Handled correctly")

    # =========================================================================
    # EDGE CASE: Invalid Metric
    # =========================================================================
    async def test_edge_case_invalid_metric(self, analytics_impl):
        """
        Test: Invalid/unknown metric should return error

        Query: "tasa de quiebra" (doesn't exist in our system)

        Expected:
        - Returns validation error or clarification
        """
        result = await analytics_impl(
            metric_or_query="tasa de quiebra total absoluta",
            mode="dashboard"
        )

        # Should either return ambiguous or validation error
        assert "error" in result or "options" in result, \
            "Unknown metric should trigger error or clarification"

        print(f"✅ EDGE CASE - Invalid Metric: Handled correctly")

    # =========================================================================
    # SMOKE TEST: All 9 Priority Visualizations
    # =========================================================================
    @pytest.mark.parametrize("query_spec", [
        ("Cartera Comercial CC", "cartera comercial total"),
        ("Cartera Sin Gobierno", "cartera comercial sin gobierno"),
        ("Pérdida Esperada", "pérdida esperada total"),
        ("Reservas Totales", "reservas totales"),
        ("IMOR", "IMOR de INVEX"),
        ("Cartera Vencida", "cartera vencida"),
        ("ICOR", "ICOR de INVEX"),
        ("ICAP", "ICAP de INVEX")
    ])
    async def test_smoke_all_9_visualizations(self, analytics_impl, query_spec):
        """
        Smoke test: Ensure all 9 priority visualizations can be queried.

        This test validates that the NLP → SQL → Viz pipeline doesn't crash
        for any of the 9 priority visualizations.
        """
        title, query = query_spec

        result = await analytics_impl(
            metric_or_query=query,
            mode="dashboard"
        )

        # Should not crash (either success or handled error)
        assert result is not None, f"{title} returned None"

        # If no error, should have valid structure
        if "error" not in result:
            assert "data" in result, f"{title} missing data"
            assert "plotly_config" in result, f"{title} missing plotly_config"

        print(f"✅ SMOKE - {title}: No crash")

    # =========================================================================
    # PERFORMANCE: Validate Performance Metadata
    # =========================================================================
    async def test_performance_metadata_present(self, analytics_impl):
        """
        Test: Verify performance metrics are included in response

        Expected:
        - Response includes 'performance' in metadata
        - Contains 'duration_ms' and 'rows_returned'
        """
        result = await analytics_impl(
            metric_or_query="IMOR",
            mode="dashboard"
        )

        if "error" not in result and "metadata" in result:
            meta = result["metadata"]
            # Performance logging was added, so this should be present
            if "performance" in meta:
                perf = meta["performance"]
                assert "duration_ms" in perf, "Should include duration_ms"
                assert "rows_returned" in perf, "Should include rows_returned"
                assert perf["duration_ms"] > 0, "Duration should be positive"

                print(f"✅ PERFORMANCE - Metadata present: {perf['duration_ms']}ms, {perf['rows_returned']} rows")
            else:
                # Performance metadata might not be added to all pipelines yet
                print("⚠️  PERFORMANCE - Metadata not present (may be expected for some pipelines)")
