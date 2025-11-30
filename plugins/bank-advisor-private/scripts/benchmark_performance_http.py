"""
Performance Benchmark Script for BankAdvisor Analytics (HTTP Version)

Executes a battery of representative queries via HTTP to the MCP server.

Usage:
    python scripts/benchmark_performance_http.py [--host localhost] [--port 8001]

Outputs:
    - Performance metrics (p50, p95, max) for each query
    - Summary report with recommendations for demo
    - JSON file with detailed results
"""
import requests
import json
import time
from pathlib import Path
from datetime import datetime
from statistics import median
from typing import List, Dict, Any
import argparse


# ============================================================================
# TEST QUERIES (9 Priority Visualizations + Common Variants)
# ============================================================================
BENCHMARK_QUERIES = [
    # Priority Visualization 1: Cartera Comercial CC
    {
        "id": "query_1_cartera_comercial",
        "query": "cartera comercial",
        "category": "simple",
        "expected_mode": "comparison"
    },

    # Priority Visualization 2: Cartera Comercial Sin Gobierno
    {
        "id": "query_2_cartera_sin_gob",
        "query": "cartera comercial sin gobierno",
        "category": "calculated",
        "expected_mode": "comparison"
    },

    # Priority Visualization 3: Pérdida Esperada (Evolution)
    {
        "id": "query_3_perdida_esperada",
        "query": "pérdida esperada total últimos 12 meses",
        "category": "timeline",
        "expected_mode": "evolution"
    },

    # Priority Visualization 4: Reservas Totales
    {
        "id": "query_4_reservas_totales",
        "query": "reservas totales",
        "category": "simple",
        "expected_mode": "comparison"
    },

    # Priority Visualization 6: IMOR (Timeline)
    {
        "id": "query_6_imor_timeline",
        "query": "IMOR de INVEX en los últimos 3 meses",
        "category": "ratio_timeline",
        "expected_mode": "evolution"
    },

    # Priority Visualization 6b: IMOR (Comparison)
    {
        "id": "query_6b_imor_comparison",
        "query": "IMOR de INVEX vs sistema",
        "category": "ratio_comparison",
        "expected_mode": "comparison"
    },

    # Priority Visualization 7: Cartera Vencida
    {
        "id": "query_7_cartera_vencida",
        "query": "cartera vencida últimos 12 meses",
        "category": "timeline",
        "expected_mode": "evolution"
    },

    # Priority Visualization 8: ICOR
    {
        "id": "query_8_icor",
        "query": "ICOR de INVEX 2024",
        "category": "ratio_timeline",
        "expected_mode": "evolution"
    },

    # Priority Visualization 9: ICAP
    {
        "id": "query_9_icap",
        "query": "ICAP de INVEX contra sistema en 2024",
        "category": "ratio_comparison",
        "expected_mode": "comparison"
    },

    # Additional common queries
    {
        "id": "query_extra_1",
        "query": "cartera total INVEX último mes",
        "category": "simple",
        "expected_mode": "point_value"
    }
]


# ============================================================================
# BENCHMARK RUNNER
# ============================================================================
def run_single_benchmark(query_spec: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    """
    Execute a single query and measure performance via HTTP.

    Returns:
        {
            "query_id": str,
            "query": str,
            "success": bool,
            "duration_ms": float,
            "rows_returned": int,
            "error": str (if failed)
        }
    """
    query_id = query_spec["id"]
    query_text = query_spec["query"]

    print(f"  Running: {query_id} - '{query_text}'")

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

        if response.status_code == 200:
            result = response.json()

            # Check if result contains error
            if "error" in result:
                return {
                    "query_id": query_id,
                    "query": query_text,
                    "category": query_spec["category"],
                    "success": False,
                    "duration_ms": round(duration_ms, 2),
                    "rows_returned": 0,
                    "error": result["error"],
                    "timestamp": datetime.utcnow().isoformat()
                }

            # Extract metrics
            rows_returned = 0
            if "data" in result and "months" in result.get("data", {}):
                rows_returned = len(result["data"]["months"])

            return {
                "query_id": query_id,
                "query": query_text,
                "category": query_spec["category"],
                "success": True,
                "duration_ms": round(duration_ms, 2),
                "rows_returned": rows_returned,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "query_id": query_id,
                "query": query_text,
                "category": query_spec["category"],
                "success": False,
                "duration_ms": round(duration_ms, 2),
                "rows_returned": 0,
                "error": f"HTTP {response.status_code}: {response.text[:100]}",
                "timestamp": datetime.utcnow().isoformat()
            }

    except Exception as e:
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        return {
            "query_id": query_id,
            "query": query_text,
            "category": query_spec["category"],
            "success": False,
            "duration_ms": round(duration_ms, 2),
            "rows_returned": 0,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


def run_all_benchmarks(base_url: str) -> List[Dict[str, Any]]:
    """
    Execute all benchmark queries sequentially.

    Returns list of results.
    """
    print(f"\n{'='*80}")
    print("🚀 BankAdvisor Performance Benchmark (HTTP)")
    print(f"{'='*80}")
    print(f"Target: {base_url}")
    print(f"Running {len(BENCHMARK_QUERIES)} queries...\n")

    results = []

    for i, query_spec in enumerate(BENCHMARK_QUERIES, 1):
        print(f"[{i}/{len(BENCHMARK_QUERIES)}]", end=" ")
        result = run_single_benchmark(query_spec, base_url)
        results.append(result)

        # Print immediate feedback
        status = "✅" if result["success"] else "❌"
        print(f"    {status} {result['duration_ms']:.0f}ms")

        # Small delay to avoid overwhelming server
        time.sleep(0.5)

    return results


def analyze_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate statistics and generate summary report.
    """
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    durations = [r["duration_ms"] for r in successful]

    if not durations:
        return {
            "total_queries": len(results),
            "successful": 0,
            "failed": len(failed),
            "error": "All queries failed"
        }

    durations_sorted = sorted(durations)
    n = len(durations_sorted)

    p50 = durations_sorted[int(n * 0.5)] if n > 0 else 0
    p95 = durations_sorted[int(n * 0.95)] if n > 1 else durations_sorted[-1]
    p99 = durations_sorted[int(n * 0.99)] if n > 2 else durations_sorted[-1]

    # Group by category
    by_category = {}
    for result in successful:
        cat = result["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(result["duration_ms"])

    category_stats = {}
    for cat, times in by_category.items():
        category_stats[cat] = {
            "count": len(times),
            "avg_ms": round(sum(times) / len(times), 2),
            "median_ms": round(median(times), 2),
            "max_ms": round(max(times), 2)
        }

    return {
        "total_queries": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "durations": {
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "max_ms": round(max(durations), 2),
            "min_ms": round(min(durations), 2),
            "avg_ms": round(sum(durations) / len(durations), 2)
        },
        "by_category": category_stats,
        "failed_queries": [
            {"query_id": r["query_id"], "error": r.get("error", "unknown")}
            for r in failed
        ]
    }


def print_report(results: List[Dict[str, Any]], stats: Dict[str, Any]):
    """
    Print formatted performance report to console.
    """
    print(f"\n{'='*80}")
    print("📊 PERFORMANCE REPORT")
    print(f"{'='*80}\n")

    print(f"Total Queries:    {stats['total_queries']}")
    print(f"✅ Successful:     {stats['successful']}")
    print(f"❌ Failed:         {stats['failed']}")
    print()

    if stats["successful"] > 0:
        durations = stats["durations"]
        print("⏱️  RESPONSE TIMES (ms):")
        print(f"  p50 (median):   {durations['p50_ms']:.0f} ms")
        print(f"  p95:            {durations['p95_ms']:.0f} ms")
        print(f"  p99:            {durations['p99_ms']:.0f} ms")
        print(f"  Max:            {durations['max_ms']:.0f} ms")
        print(f"  Min:            {durations['min_ms']:.0f} ms")
        print(f"  Avg:            {durations['avg_ms']:.0f} ms")
        print()

        print("📂 BY CATEGORY:")
        for cat, cat_stats in stats["by_category"].items():
            print(f"  {cat:20s} - {cat_stats['count']} queries, avg: {cat_stats['avg_ms']:.0f}ms, median: {cat_stats['median_ms']:.0f}ms")
        print()

    if stats["failed"] > 0:
        print("❌ FAILED QUERIES:")
        for fail in stats["failed_queries"]:
            print(f"  - {fail['query_id']}: {fail['error']}")
        print()

    print(f"{'='*80}")
    print("💡 DEMO TALKING POINTS:")
    print(f"{'='*80}\n")

    if stats["successful"] > 0:
        d = stats["durations"]
        print(f"\"En pruebas internas, las consultas típicas responden en ~{d['p50_ms']:.0f}ms (p50),")
        print(f" con el 95% de las queries completándose en menos de {d['p95_ms']:.0f}ms.\"")
        print()
        print(f"\"Los casos más complejos (agregaciones temporales) pueden tomar hasta {d['max_ms']:.0f}ms,")
        print(f" pero el sistema mantiene una latencia promedio de {d['avg_ms']:.0f}ms.\"")
    else:
        print("⚠️  WARNING: All queries failed. Check:")
        print("  1. Server is running (docker ps | grep bank-advisor)")
        print("  2. Database has data (curl http://localhost:8001/health)")
        print("  3. ETL has been executed (python -m bankadvisor.etl_runner)")

    print()


def main():
    """Main benchmark execution."""
    parser = argparse.ArgumentParser(description="BankAdvisor Performance Benchmark")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    parser.add_argument("--port", default="8001", help="Server port (default: 8001)")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # Check server health first
    try:
        health_response = requests.get(f"{base_url}/health", timeout=5)
        if health_response.status_code != 200:
            print(f"❌ Server health check failed: {health_response.status_code}")
            print(f"   Response: {health_response.text[:200]}")
            return
        print(f"✅ Server is healthy: {base_url}")
    except Exception as e:
        print(f"❌ Cannot connect to server at {base_url}")
        print(f"   Error: {e}")
        print("\n💡 Start the server with: docker-compose up -d")
        return

    # Run benchmarks
    results = run_all_benchmarks(base_url)

    # Analyze results
    stats = analyze_results(results)

    # Print report
    print_report(results, stats)

    # Save detailed results to JSON
    output_file = Path(__file__).parent.parent / "docs" / "performance_baseline.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "server": base_url,
        "stats": stats,
        "results": results
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"📁 Detailed results saved to: {output_file}")
    print()


if __name__ == "__main__":
    main()
