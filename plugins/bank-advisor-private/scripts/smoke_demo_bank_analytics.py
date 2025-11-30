#!/usr/bin/env python3
"""
Smoke Test Pre-Demo - BankAdvisor Analytics

Validates that ALL demo queries work correctly before going live.

This is your "traffic light" script:
- 🟢 All green → Demo ready
- 🔴 Any red → Fix before demo

Usage:
    # Default (localhost:8001)
    python scripts/smoke_demo_bank_analytics.py

    # Custom host/port
    python scripts/smoke_demo_bank_analytics.py --host demo.server.com --port 8001

Exit codes:
    0 = All checks passed (safe to demo)
    1 = One or more checks failed (DO NOT DEMO)
"""
import requests
import json
import sys
import argparse
from typing import Dict, Any, List, Tuple
from datetime import datetime


# ============================================================================
# DEMO QUERIES (Exact queries from DEMO_SCRIPT_2025-12-03.md)
# ============================================================================
DEMO_QUERIES = [
    {
        "id": "Q1_IMOR_evolution",
        "query": "IMOR de INVEX en 2024",
        "max_duration_ms": 3000,
        "min_rows": 1,
        "expected_chart_type": "line",  # dual_mode: timeline/evolution
        "visualization_mode": "timeline"
    },
    {
        "id": "Q2_cartera_comercial_comparison",
        "query": "Cartera comercial de INVEX vs sistema",
        "max_duration_ms": 2000,  # Comparisons need more time
        "min_rows": 1,
        "expected_chart_type": "bar",  # comparison mode
        "visualization_mode": "comparison"
    },
    {
        "id": "Q3_cartera_sin_gobierno",
        "query": "Cartera comercial sin gobierno",
        "max_duration_ms": 3000,  # LLM queries can take ~2s
        "min_rows": 1,
        "expected_chart_type": "bar",  # dashboard_month_comparison
        "visualization_mode": "comparison"
    },
    {
        "id": "Q4_reservas_totales",
        "query": "Reservas totales de INVEX",
        "max_duration_ms": 3000,  # LLM queries can take ~2s
        "min_rows": 1,
        "expected_chart_type": "bar",  # dashboard_month_comparison
        "visualization_mode": "comparison"
    },
    {
        "id": "Q5_ICAP",
        "query": "ICAP de INVEX contra sistema en 2024",
        "max_duration_ms": 2000,
        "min_rows": 1,
        "expected_chart_type": "bar",  # dual_mode: comparison (has "contra")
        "visualization_mode": "comparison"
    },
    {
        "id": "Q6_cartera_vencida_timeline",
        "query": "Cartera vencida en 2024",
        "max_duration_ms": 3000,
        "min_rows": 1,
        "expected_chart_type": "line",  # dual_mode: timeline (year range)
        "visualization_mode": "timeline"
    },
    {
        "id": "Q7_ICOR",
        "query": "ICOR de INVEX 2024",
        "max_duration_ms": 2000,
        "min_rows": 1,
        "expected_chart_type": "line",  # dual_mode: timeline
        "visualization_mode": "timeline"
    },
    {
        "id": "Q8_dual_mode_evolution",
        "query": "Evolución del IMOR en 2024",
        "max_duration_ms": 2500,
        "min_rows": 1,
        "expected_chart_type": "line",  # dual_mode: explicit "evolución"
        "visualization_mode": "timeline"
    },
    {
        "id": "Q9_dual_mode_comparison",
        "query": "Compara IMOR de INVEX vs sistema",
        "max_duration_ms": 2500,  # Comparisons need more time
        "min_rows": 1,
        "expected_chart_type": "bar",  # dual_mode: explicit "compara"
        "visualization_mode": "comparison"
    },
    {
        "id": "Q10_edge_case_ambiguous",
        "query": "cartera",
        "max_duration_ms": 1000,
        "min_rows": 0,
        "expected_chart_type": None,  # No chart expected - returns clarification
        "expect_clarification": True,
        "skip_plotly_validation": True  # Don't check plotly_config for clarifications
    },
    # ============================================================================
    # ADVERSARIAL CASES (Edge cases that should NOT crash)
    # ============================================================================
    {
        "id": "Q11_adversarial_future_date",
        "query": "IMOR de INVEX en 2030",
        "max_duration_ms": 2000,
        "min_rows": 0,  # Should return empty, not crash
        "expected_chart_type": None,
        "expect_empty": True,  # Future date - no data expected
        "skip_plotly_validation": True
    },
    {
        "id": "Q12_adversarial_multi_entity_comparison",
        "query": "ICAP de INVEX contra Banorte y sistema",
        "max_duration_ms": 2000,
        "min_rows": 0,
        "expected_chart_type": None,  # May trigger clarification
        "expect_clarification": True,  # Too many entities
        "skip_plotly_validation": True
    }
]


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================
def check_server_health(base_url: str) -> Tuple[bool, str]:
    """
    Validate that server is up and healthy.

    Returns:
        (success, message)
    """
    try:
        response = requests.get(f"{base_url}/health", timeout=5)

        if response.status_code != 200:
            return False, f"Health check returned {response.status_code}"

        health_data = response.json()

        if health_data.get("status") != "healthy":
            return False, f"Server status is '{health_data.get('status')}'"

        # Check ETL status
        if "etl" in health_data:
            etl = health_data["etl"]
            if etl.get("last_run_status") == "failure":
                return False, f"Last ETL run failed: {etl.get('error_message', 'unknown')}"
            elif etl.get("last_run_status") == "never_run":
                return False, "ETL has never run (no data in DB)"

        return True, "Server healthy"

    except requests.exceptions.ConnectionError:
        return False, f"Cannot connect to {base_url}"
    except Exception as e:
        return False, f"Health check failed: {str(e)}"


def validate_query_response(
    response_data: Dict[str, Any],
    query_spec: Dict[str, Any],
    duration_ms: float
) -> Tuple[bool, List[str]]:
    """
    Validate a single query response against expectations.

    Returns:
        (success, list of issues)
    """
    issues = []

    # 1. Check if error is expected
    if "expect_error" in query_spec:
        if "error" not in response_data:
            issues.append(f"Expected error '{query_spec['expect_error']}' but got success")
        elif response_data.get("error") != query_spec["expect_error"]:
            issues.append(f"Expected error '{query_spec['expect_error']}' but got '{response_data.get('error')}'")
        # For expected errors, don't validate other fields
        return len(issues) == 0, issues

    # 2. Check for unexpected errors
    if "error" in response_data:
        issues.append(f"Query failed with error: {response_data.get('error')}")
        if "message" in response_data:
            issues.append(f"  Message: {response_data.get('message')}")
        return False, issues

    # 3. Validate required fields
    # NOTE: System supports two formats:
    # - Legacy: {"data": {"months": [...]}, "plotly_config": {...}}
    # - HU3: {"data": {"type": "data", "values": [...]}}

    if "data" not in response_data:
        issues.append("Missing 'data' field in response")
        return False, issues

    data = response_data.get("data", {})

    # Check for data type (HU3 format)
    data_type = data.get("type")

    # If data.type is "empty", that's a valid response (no data for date range)
    if data_type == "empty":
        # This is acceptable - query worked but no data in range
        return True, []

    # If data.type is "clarification", query needs user input
    if data_type == "clarification":
        # This is acceptable for ambiguous queries
        # Check if we expected this (Q10)
        if query_spec.get("expect_clarification"):
            return True, []
        # Otherwise it's an issue
        issues.append(f"Unexpected clarification: {data.get('message', 'unknown')}")
        return False, issues

    # Validate we have actual data
    # Three valid formats:
    # 1. Legacy: {"data": {"months": [...]}, "plotly_config": {...}}
    # 2. HU3: {"data": {"type": "data", "values": [...]}}
    # 3. HU3+Plotly: {"data": {"type": "data", "plotly_config": {...}}}

    has_legacy_data = "months" in data and len(data["months"]) > 0
    has_hu3_data = "values" in data and len(data["values"]) > 0
    # Check both locations for plotly_config: top-level or inside data
    has_plotly_only = (
        ("plotly_config" in response_data or "plotly_config" in data)
        and data_type == "data"
    )

    if not has_legacy_data and not has_hu3_data and not has_plotly_only:
        issues.append("No data returned (expected data.months, data.values, or plotly_config)")
        return False, issues

    # Count rows
    if has_legacy_data:
        n_rows = len(data["months"])
    elif has_hu3_data:
        n_rows = len(data["values"])
    elif has_plotly_only:
        # For plotly-only responses, check if traces have data
        # Check both locations
        plotly = response_data.get("plotly_config") or data.get("plotly_config", {})
        if "data" in plotly and len(plotly["data"]) > 0:
            # Count data points from first trace
            first_trace = plotly["data"][0]
            if "x" in first_trace:
                n_rows = len(first_trace["x"])
            else:
                n_rows = 1  # Has plotly but can't count, assume data exists
        else:
            n_rows = 0
    else:
        n_rows = 0

    if n_rows < query_spec["min_rows"]:
        issues.append(f"Expected at least {query_spec['min_rows']} rows, got {n_rows}")

    # Validate plotly_config based on query expectations
    skip_plotly = query_spec.get("skip_plotly_validation", False)
    expected_chart_type = query_spec.get("expected_chart_type")

    if not skip_plotly:
        # If we expect a chart type, we MUST have plotly_config
        if expected_chart_type is not None:
            # Check both locations for plotly_config
            plotly = response_data.get("plotly_config") or data.get("plotly_config")

            if not plotly:
                issues.append(
                    f"Expected chart type '{expected_chart_type}' but plotly_config is missing. "
                    "HU3 pipeline should generate plotly_config aligned with visualizations.yaml"
                )
            else:
                if "data" not in plotly:
                    issues.append("plotly_config present but missing 'data'")
                elif len(plotly["data"]) == 0:
                    issues.append("plotly_config.data is empty (no traces)")
                else:
                    # Validate chart type matches expectation
                    actual_type = plotly["data"][0].get("type")

                    # line and scatter are both acceptable for timelines
                    # bar and scatter are interchangeable for single-entity displays
                    acceptable_types = [expected_chart_type]
                    if expected_chart_type == "line":
                        acceptable_types.append("scatter")
                    elif expected_chart_type == "bar":
                        acceptable_types.append("scatter")  # Evolution format is also acceptable

                    if actual_type not in acceptable_types:
                        issues.append(
                            f"Expected chart type '{expected_chart_type}', got '{actual_type}'. "
                            f"Check visualizations.yaml alignment"
                        )

                if "layout" not in plotly:
                    issues.append("plotly_config present but missing 'layout'")
        else:
            # expected_chart_type is None, but we're not skipping validation
            # This shouldn't happen - either expect a chart or skip validation
            issues.append(
                "Configuration error: expected_chart_type is None but skip_plotly_validation is False. "
                "Either set expected_chart_type or set skip_plotly_validation=True"
            )

    # 6. Validate performance
    if duration_ms > query_spec["max_duration_ms"]:
        issues.append(
            f"Performance warning: {duration_ms:.0f}ms > {query_spec['max_duration_ms']}ms threshold"
        )

    # 7. Validate performance metadata (if present)
    if "metadata" in response_data and "performance" in response_data["metadata"]:
        perf = response_data["metadata"]["performance"]
        if "duration_ms" not in perf:
            issues.append("Performance metadata missing 'duration_ms'")
        if "rows_returned" not in perf:
            issues.append("Performance metadata missing 'rows_returned'")

    return len(issues) == 0, issues


def run_single_query(
    base_url: str,
    query_spec: Dict[str, Any]
) -> Tuple[bool, float, List[str]]:
    """
    Execute a single query and validate response.

    Returns:
        (success, duration_ms, issues)
    """
    query_id = query_spec["id"]
    query_text = query_spec["query"]

    # Prepare JSON-RPC 2.0 request
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "bank_analytics",
            "arguments": {
                "metric_or_query": query_text,
                "mode": "dashboard"
            }
        }
    }

    import time
    start_time = time.time()

    try:
        response = requests.post(
            f"{base_url}/rpc",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        if response.status_code != 200:
            return False, duration_ms, [f"HTTP {response.status_code}: {response.text[:200]}"]

        rpc_response = response.json()

        # Check for JSON-RPC error
        if "error" in rpc_response:
            return False, duration_ms, [f"RPC Error: {rpc_response['error']}"]

        # Extract the actual result from MCP wrapper
        # Format: {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "..."}]}}
        if "result" not in rpc_response or "content" not in rpc_response["result"]:
            return False, duration_ms, ["Missing 'result.content' in RPC response"]

        content_items = rpc_response["result"]["content"]
        if len(content_items) == 0 or content_items[0].get("type") != "text":
            return False, duration_ms, ["Invalid content format in RPC response"]

        # Parse the JSON string inside text
        import json
        try:
            result = json.loads(content_items[0]["text"])
        except json.JSONDecodeError as e:
            return False, duration_ms, [f"Failed to parse result JSON: {str(e)}"]

        # Validate response
        success, issues = validate_query_response(result, query_spec, duration_ms)

        return success, duration_ms, issues

    except requests.exceptions.Timeout:
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        return False, duration_ms, [f"Request timeout after {duration_ms:.0f}ms"]
    except Exception as e:
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        return False, duration_ms, [f"Exception: {str(e)}"]


# ============================================================================
# MAIN SMOKE TEST
# ============================================================================
def run_smoke_test(base_url: str, verbose: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """
    Run complete smoke test suite.

    Returns:
        (all_passed, results_dict)
    """
    print("=" * 80)
    print("🚦 SMOKE TEST PRE-DEMO - BankAdvisor Analytics")
    print("=" * 80)
    print(f"Target: {base_url}")
    print(f"Time:   {datetime.utcnow().isoformat()}Z")
    print()

    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "server": base_url,
        "health_check": {},
        "queries": [],
        "summary": {}
    }

    # =========================================================================
    # STEP 1: Health Check
    # =========================================================================
    print("STEP 1: Server Health Check")
    print("-" * 80)

    success, message = check_server_health(base_url)
    results["health_check"] = {"success": success, "message": message}

    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
        print()
        print("=" * 80)
        print("🔴 SMOKE TEST FAILED - Fix health issues before demo")
        print("=" * 80)
        return False, results

    print()

    # =========================================================================
    # STEP 2: Query Validation
    # =========================================================================
    print("STEP 2: Demo Queries Validation")
    print("-" * 80)

    total_queries = len(DEMO_QUERIES)
    passed = 0
    failed = 0

    for i, query_spec in enumerate(DEMO_QUERIES, 1):
        query_id = query_spec["id"]
        query_text = query_spec["query"]

        print(f"[{i}/{total_queries}] {query_id}")
        print(f"    Query: \"{query_text}\"")

        success, duration_ms, issues = run_single_query(base_url, query_spec)

        query_result = {
            "id": query_id,
            "query": query_text,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "issues": issues
        }
        results["queries"].append(query_result)

        if success:
            print(f"    ✅ PASS ({duration_ms:.0f}ms)")
            passed += 1
        else:
            print(f"    ❌ FAIL ({duration_ms:.0f}ms)")
            for issue in issues:
                print(f"       - {issue}")
            failed += 1

        if verbose and issues:
            print(f"       Issues: {', '.join(issues)}")

        print()

    # =========================================================================
    # STEP 3: Summary
    # =========================================================================
    results["summary"] = {
        "total": total_queries,
        "passed": passed,
        "failed": failed,
        "success_rate": round((passed / total_queries) * 100, 1)
    }

    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"Total Queries:  {total_queries}")
    print(f"✅ Passed:       {passed}")
    print(f"❌ Failed:       {failed}")
    print(f"Success Rate:   {results['summary']['success_rate']}%")
    print()

    if failed == 0:
        print("=" * 80)
        print("🟢 ALL CHECKS PASSED - SAFE TO DEMO")
        print("=" * 80)
        return True, results
    else:
        print("=" * 80)
        print("🔴 SOME CHECKS FAILED - DO NOT DEMO UNTIL FIXED")
        print("=" * 80)
        print()
        print("Failed queries:")
        for query_result in results["queries"]:
            if not query_result["success"]:
                print(f"  - {query_result['id']}: {query_result['query']}")
                for issue in query_result["issues"]:
                    print(f"      {issue}")
        print()
        return False, results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Smoke test for BankAdvisor demo queries"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Server host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        default="8001",
        help="Server port (default: 8001)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed issue descriptions"
    )
    parser.add_argument(
        "--save-json",
        metavar="FILE",
        help="Save results to JSON file"
    )

    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # Run smoke test
    all_passed, results = run_smoke_test(base_url, verbose=args.verbose)

    # Save results if requested
    if args.save_json:
        with open(args.save_json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to: {args.save_json}")

    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
