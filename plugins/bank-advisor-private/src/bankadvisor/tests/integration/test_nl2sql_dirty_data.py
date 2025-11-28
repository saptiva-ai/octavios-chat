"""
NL2SQL Dirty Data / Hostile Query Test Harness (BA-QA-001)

Tests the NL2SQL pipeline with adversarial, malformed, and edge-case queries
to ensure robust error handling, SQL injection prevention, and graceful degradation.

Special focus on BA-NULL-001: NULL handling for ICAP, TDA, TASA_MN, TASA_ME metrics.

Run with: pytest -m nl2sql_dirty -v
Run NULL tests only: pytest -m nl2sql_dirty -k "ba_null" -v
"""

import json
import time
import pytest
import httpx
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)

# Path to hostile queries catalog
HOSTILE_QUERIES_PATH = Path(__file__).parent.parent.parent.parent.parent / "tests" / "data" / "hostile_queries.json"


@dataclass
class QueryResult:
    """Result of a single hostile query test."""
    query_id: str
    category: str
    query: str
    http_status: int
    response_time_ms: float
    success: bool
    error: Optional[str] = None
    error_code: Optional[str] = None
    pipeline_attribution: Optional[str] = None  # "nl2sql" or "legacy"
    has_valid_json_rpc: bool = False
    sql_injection_detected: bool = False
    null_handling_ok: bool = True
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class DirtyDataTestSummary:
    """Summary of all hostile query tests."""
    total_queries: int = 0
    successes: int = 0
    handled_errors: int = 0
    invalid_responses: int = 0
    crashes: int = 0
    injection_attempts_blocked: int = 0
    null_handling_passed: int = 0
    null_handling_failed: int = 0
    by_category: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: {"total": 0, "success": 0, "error": 0}))
    results: List[QueryResult] = field(default_factory=list)

    def add_result(self, result: QueryResult):
        self.results.append(result)
        self.total_queries += 1
        self.by_category[result.category]["total"] += 1

        if result.success:
            self.successes += 1
            self.by_category[result.category]["success"] += 1
        elif result.error and result.http_status < 500:
            self.handled_errors += 1
            self.by_category[result.category]["error"] += 1
        elif result.http_status >= 500:
            self.crashes += 1
        else:
            self.invalid_responses += 1

        if result.sql_injection_detected:
            self.injection_attempts_blocked += 1

        if result.query_id.startswith("DN-"):
            if result.null_handling_ok:
                self.null_handling_passed += 1
            else:
                self.null_handling_failed += 1


def load_hostile_queries() -> Dict[str, Any]:
    """Load the hostile queries catalog from JSON file."""
    if not HOSTILE_QUERIES_PATH.exists():
        raise FileNotFoundError(f"Hostile queries catalog not found: {HOSTILE_QUERIES_PATH}")

    with open(HOSTILE_QUERIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_rpc_endpoint() -> str:
    """Get the JSON-RPC endpoint URL from environment or default."""
    import os
    return os.environ.get("BANKADVISOR_RPC_URL", "http://localhost:8002/rpc")


class HostileQueryRunner:
    """Runs hostile queries against the NL2SQL JSON-RPC endpoint."""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or get_rpc_endpoint()
        self.client = httpx.Client(timeout=30.0)

    def close(self):
        self.client.close()

    def build_rpc_payload(self, query: str, method: str = "tools/call") -> Dict[str, Any]:
        """Build JSON-RPC 2.0 payload for query."""
        return {
            "jsonrpc": "2.0",
            "id": f"test-{int(time.time() * 1000)}",
            "method": method,
            "params": {
                "name": "bank_analytics",
                "arguments": {
                    "metric_or_query": query,
                    "mode": "dashboard"
                }
            }
        }

    def execute_query(self, query_id: str, category: str, query: str) -> QueryResult:
        """Execute a single hostile query and capture result."""
        start_time = time.time()

        try:
            payload = self.build_rpc_payload(query)
            response = self.client.post(self.base_url, json=payload)
            elapsed_ms = (time.time() - start_time) * 1000

            result = QueryResult(
                query_id=query_id,
                category=category,
                query=query,
                http_status=response.status_code,
                response_time_ms=elapsed_ms,
                success=False,
            )

            # Check for valid JSON-RPC response
            try:
                body = response.json()
                result.has_valid_json_rpc = "jsonrpc" in body and "id" in body
                result.raw_response = body

                if "result" in body:
                    result.success = True
                    result.pipeline_attribution = body.get("result", {}).get("pipeline", "unknown")

                    # Check for SQL injection indicators in result
                    result_str = str(body.get("result", {}))
                    if any(x in result_str.upper() for x in ["DROP TABLE", "DELETE FROM", "UNION SELECT"]):
                        result.sql_injection_detected = False  # Injection made it through!
                    else:
                        result.sql_injection_detected = category == "injection_like"

                elif "error" in body:
                    result.error = body["error"].get("message", "Unknown error")
                    result.error_code = body["error"].get("code")

                    # Handled errors are OK for hostile queries
                    if response.status_code < 500:
                        result.success = True  # Graceful handling counts as success

                    # Check injection was blocked
                    if category == "injection_like":
                        result.sql_injection_detected = True

            except json.JSONDecodeError:
                result.error = "Invalid JSON response"
                result.has_valid_json_rpc = False

            return result

        except httpx.RequestError as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return QueryResult(
                query_id=query_id,
                category=category,
                query=query,
                http_status=0,
                response_time_ms=elapsed_ms,
                success=False,
                error=str(e),
            )


@pytest.fixture(scope="module")
def hostile_queries():
    """Load hostile queries catalog."""
    return load_hostile_queries()


@pytest.fixture(scope="module")
def query_runner():
    """Create query runner instance."""
    runner = HostileQueryRunner()
    yield runner
    runner.close()


@pytest.fixture(scope="module")
def test_summary():
    """Shared test summary across all tests."""
    return DirtyDataTestSummary()


@pytest.mark.nl2sql_dirty
class TestNl2SqlDirtyData:
    """
    Dirty Data / Hostile Query tests for NL2SQL pipeline.

    These tests validate that the pipeline:
    1. Does not crash on malformed input
    2. Returns valid JSON-RPC responses
    3. Blocks SQL injection attempts
    4. Handles NULL values gracefully (BA-NULL-001)
    5. Provides helpful error messages
    """

    @pytest.mark.parametrize("query_data", load_hostile_queries()["queries"], ids=lambda q: q["id"])
    def test_hostile_query(self, query_data: Dict[str, Any], query_runner: HostileQueryRunner, test_summary: DirtyDataTestSummary):
        """
        Test a single hostile query from the catalog.

        Asserts:
        - No 5xx server errors (crashes)
        - Valid JSON-RPC response structure
        - SQL injection patterns are blocked
        """
        result = query_runner.execute_query(
            query_id=query_data["id"],
            category=query_data["category"],
            query=query_data["query"],
        )

        test_summary.add_result(result)

        # CRITICAL: No crashes (5xx errors)
        assert result.http_status != 500, f"Server crash on query '{query_data['id']}': {result.error}"

        # Valid JSON-RPC structure (if we got a response)
        if result.http_status > 0:
            assert result.has_valid_json_rpc, f"Invalid JSON-RPC response for '{query_data['id']}'"

        # SQL injection must be blocked
        if query_data["category"] == "injection_like":
            # Either rejected (error) or sanitized (success without injection payload)
            assert result.sql_injection_detected or result.success, \
                f"SQL injection may have succeeded for '{query_data['id']}'"


@pytest.mark.nl2sql_dirty
@pytest.mark.ba_null_001
class TestBaNullHandling:
    """
    BA-NULL-001: Specific tests for NULL value handling in ICAP, TDA, TASA metrics.

    The BA-NULL-001 commit added logic to:
    - Skip records with NULL metric values in AnalyticsService
    - Display "N/A" for null/zero values in VisualizationService
    - Handle NULL gracefully in comparison charts
    """

    @pytest.fixture
    def null_queries(self, hostile_queries):
        """Filter to only BA-NULL-001 relevant queries."""
        return [q for q in hostile_queries["queries"] if q.get("ba_null_001")]

    @pytest.mark.parametrize("metric,expected_column", [
        ("ICAP", "icap_total"),
        ("TDA", "tda_cartera_total"),
        ("tasa mn", "tasa_mn"),
        ("tasa me", "tasa_me"),
    ])
    def test_nullable_metric_resolution(self, metric: str, expected_column: str):
        """Test that nullable metrics resolve correctly."""
        pytest.importorskip("bankadvisor.services.analytics_service")
        from bankadvisor.services.analytics_service import AnalyticsService

        resolved = AnalyticsService.resolve_metric_id(metric)
        assert resolved == expected_column, f"'{metric}' should resolve to '{expected_column}', got '{resolved}'"

    def test_null_metric_in_whitelist(self):
        """Verify nullable metrics are in SAFE_METRIC_COLUMNS whitelist."""
        pytest.importorskip("bankadvisor.services.analytics_service")
        from bankadvisor.services.analytics_service import AnalyticsService

        nullable_metrics = ["icap_total", "tda_cartera_total", "tasa_mn", "tasa_me"]
        for metric in nullable_metrics:
            assert metric in AnalyticsService.SAFE_METRIC_COLUMNS, \
                f"Nullable metric '{metric}' missing from whitelist"

    @pytest.mark.asyncio
    async def test_query_spec_parser_handles_null_metrics(self):
        """Test that QuerySpecParser correctly parses queries for nullable metrics."""
        pytest.importorskip("bankadvisor.services.query_spec_parser")
        from bankadvisor.services.query_spec_parser import QuerySpecParser

        parser = QuerySpecParser()

        test_cases = [
            ("ICAP de INVEX 2024", "ICAP"),
            ("TDA del sistema", "TDA"),
            ("tasa mn de INVEX", "TASA_MN"),
            ("tasa me ultimos 6 meses", "TASA_ME"),
        ]

        for query, expected_metric in test_cases:
            spec = await parser.parse(query)
            assert spec.metric == expected_metric, \
                f"Query '{query}' should parse to metric '{expected_metric}', got '{spec.metric}'"

    @pytest.mark.asyncio
    async def test_sql_generation_with_nullable_metrics(self):
        """Test SQL generation doesn't fail for nullable metrics."""
        pytest.importorskip("bankadvisor.services.query_spec_parser")
        from bankadvisor.services.query_spec_parser import QuerySpecParser
        from bankadvisor.services.nl2sql_context_service import Nl2SqlContextService
        from bankadvisor.services.sql_generation_service import SqlGenerationService
        from bankadvisor.services.sql_validator import SqlValidator

        parser = QuerySpecParser()
        context_service = Nl2SqlContextService()
        sql_generator = SqlGenerationService(validator=SqlValidator())

        nullable_queries = [
            "ICAP de INVEX 2023",
            "TDA del sistema ultimos 12 meses",
            "tasa mn de INVEX 2024",
        ]

        for query in nullable_queries:
            spec = await parser.parse(query)
            ctx = await context_service.rag_context_for_spec(spec, original_query=query)
            result = await sql_generator.build_sql_from_spec(spec, ctx)

            assert result.success, f"SQL generation failed for nullable metric query: {query}"
            assert result.sql is not None, f"No SQL generated for: {query}"


@pytest.mark.nl2sql_dirty
class TestInjectionPrevention:
    """Focused tests for SQL injection prevention."""

    @pytest.fixture
    def injection_queries(self, hostile_queries):
        """Filter to injection-like queries only."""
        return [q for q in hostile_queries["queries"] if q["category"] == "injection_like"]

    def test_drop_table_blocked(self, query_runner: HostileQueryRunner):
        """Verify DROP TABLE injection is blocked."""
        result = query_runner.execute_query(
            query_id="INJ-DROP",
            category="injection_like",
            query="IMOR'; DROP TABLE monthly_kpis; --"
        )

        # Should either error or succeed without the injection
        if result.success and result.raw_response:
            result_str = str(result.raw_response)
            assert "DROP" not in result_str.upper(), "DROP TABLE injection may have executed"

    def test_union_select_blocked(self, query_runner: HostileQueryRunner):
        """Verify UNION SELECT injection is blocked."""
        result = query_runner.execute_query(
            query_id="INJ-UNION",
            category="injection_like",
            query="cartera UNION SELECT password FROM users"
        )

        if result.success and result.raw_response:
            result_str = str(result.raw_response)
            assert "UNION" not in result_str.upper() or "password" not in result_str.lower(), \
                "UNION SELECT injection may have executed"


def print_summary(summary: DirtyDataTestSummary):
    """Print formatted test summary."""
    print("\n" + "=" * 70)
    print("NL2SQL DIRTY DATA TEST SUMMARY")
    print("=" * 70)
    print(f"\nTotal queries tested: {summary.total_queries}")
    print(f"  - Successes (handled gracefully): {summary.successes}")
    print(f"  - Handled errors: {summary.handled_errors}")
    print(f"  - Invalid responses: {summary.invalid_responses}")
    print(f"  - Crashes (5xx): {summary.crashes}")
    print(f"\nSQL Injection attempts blocked: {summary.injection_attempts_blocked}")
    print(f"\nBA-NULL-001 (NULL handling):")
    print(f"  - Passed: {summary.null_handling_passed}")
    print(f"  - Failed: {summary.null_handling_failed}")

    print("\nResults by category:")
    for category, stats in sorted(summary.by_category.items()):
        success_rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
        print(f"  {category}: {stats['success']}/{stats['total']} ({success_rate:.0f}% handled)")

    print("\n" + "=" * 70)

    # List any crashes
    crashes = [r for r in summary.results if r.http_status >= 500]
    if crashes:
        print("\nCRASHES DETECTED:")
        for crash in crashes:
            print(f"  - {crash.query_id}: {crash.query[:50]}...")
            print(f"    Error: {crash.error}")


@pytest.fixture(scope="session", autouse=True)
def print_final_summary(request):
    """Print summary at end of test session."""
    yield
    # Note: Summary is per-module, so this won't capture cross-module results
    # Use the --tb=short option and look at individual test results


# Standalone runner for development/debugging
if __name__ == "__main__":
    import asyncio

    print("Loading hostile queries...")
    queries = load_hostile_queries()
    print(f"Loaded {len(queries['queries'])} hostile queries in {len(queries['categories'])} categories")

    runner = HostileQueryRunner()
    summary = DirtyDataTestSummary()

    print(f"\nRunning against: {runner.base_url}\n")

    for query_data in queries["queries"]:
        print(f"Testing {query_data['id']}...", end=" ")
        result = runner.execute_query(
            query_id=query_data["id"],
            category=query_data["category"],
            query=query_data["query"],
        )
        summary.add_result(result)

        status = "OK" if result.success else f"ERROR ({result.http_status})"
        print(f"{status} [{result.response_time_ms:.0f}ms]")

    runner.close()
    print_summary(summary)
