"""
Performance Benchmark Script for BankAdvisor Analytics

Executes a battery of representative queries to establish performance baselines.

Usage:
    python scripts/benchmark_performance.py

Outputs:
    - Performance metrics (p50, p95, max) for each query
    - Summary report with recommendations for demo
    - JSON file with detailed results
"""
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from statistics import median
from typing import List, Dict, Any

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from main import _bank_analytics_impl
from bankadvisor.db import init_db


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

    # Priority Visualization 5: Reservas Variación
    {
        "id": "query_5_reservas_variacion",
        "query": "reservas totales variación últimos 6 meses",
        "category": "variation",
        "expected_mode": "variation"
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
    },

    {
        "id": "query_extra_2",
        "query": "compara reservas INVEX vs sistema últimos 6 meses",
        "category": "comparison_timeline",
        "expected_mode": "evolution"
    }
]


# ============================================================================
# BENCHMARK RUNNER
# ============================================================================
async def run_single_benchmark(query_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a single query and measure performance.

    Returns:
        {
            "query_id": str,
            "query": str,
            "success": bool,
            "duration_ms": float,
            "rows_returned": int,
            "pipeline": str,
            "error": str (if failed)
        }
    """
    query_id = query_spec["id"]
    query_text = query_spec["query"]

    print(f"  Running: {query_id} - '{query_text}'")

    start_time = datetime.utcnow()

    try:
        result = await _bank_analytics_impl(query_text, mode="dashboard")

        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        # Extract metrics from result
        success = "error" not in result
        rows_returned = 0
        pipeline = "unknown"

        if success:
            # Try to extract row count
            if "data" in result and "months" in result.get("data", {}):
                rows_returned = len(result["data"]["months"])

            # Try to extract pipeline from metadata
            if "metadata" in result and "performance" in result.get("metadata", {}):
                # Performance was logged
                pass

            # Infer pipeline from result structure
            if "metadata" in result:
                meta = result["metadata"]
                if "metric" in meta:
                    pipeline = "legacy"

        return {
            "query_id": query_id,
            "query": query_text,
            "category": query_spec["category"],
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "rows_returned": rows_returned,
            "pipeline": pipeline,
            "timestamp": start_time.isoformat()
        }

    except Exception as e:
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        return {
            "query_id": query_id,
            "query": query_text,
            "category": query_spec["category"],
            "success": False,
            "duration_ms": round(duration_ms, 2),
            "rows_returned": 0,
            "pipeline": "error",
            "error": str(e),
            "timestamp": start_time.isoformat()
        }


async def run_all_benchmarks() -> List[Dict[str, Any]]:
    """
    Execute all benchmark queries sequentially.

    Returns list of results.
    """
    print(f"\n{'='*80}")
    print("🚀 BankAdvisor Performance Benchmark")
    print(f"{'='*80}")
    print(f"Running {len(BENCHMARK_QUERIES)} queries...\n")

    results = []

    for i, query_spec in enumerate(BENCHMARK_QUERIES, 1):
        print(f"[{i}/{len(BENCHMARK_QUERIES)}]", end=" ")
        result = await run_single_benchmark(query_spec)
        results.append(result)

        # Print immediate feedback
        status = "✅" if result["success"] else "❌"
        print(f"    {status} {result['duration_ms']:.0f}ms")

    return results


def analyze_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate statistics and generate summary report.

    Returns:
        {
            "total_queries": int,
            "successful": int,
            "failed": int,
            "durations": {
                "p50": float,
                "p95": float,
                "p99": float,
                "max": float,
                "min": float,
                "avg": float
            },
            "by_category": {...},
            "failed_queries": [...]
        }
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
        print("⚠️  WARNING: All queries failed. Check database connection and ETL status.")

    print()


async def main():
    """Main benchmark execution."""
    # Initialize database connection
    await init_db()

    # Run benchmarks
    results = await run_all_benchmarks()

    # Analyze results
    stats = analyze_results(results)

    # Print report
    print_report(results, stats)

    # Save detailed results to JSON
    output_file = Path(__file__).parent.parent / "docs" / "performance_baseline.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats,
        "results": results
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"📁 Detailed results saved to: {output_file}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
