#!/usr/bin/env python3
"""
HU3.4 Clarification Tests - Comprehensive Test Suite

Tests all clarification scenarios from GUIA_CONSULTAS_AMBIGUAS.md

Usage:
    python tests/test_clarifications.py
    python tests/test_clarifications.py --verbose
    python tests/test_clarifications.py --url http://localhost:8002/rpc
"""

import argparse
import json
import sys
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any
import httpx

# ANSI colors for output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class ClarificationType(Enum):
    METRIC = "metric"           # Missing/ambiguous metric
    BANK = "bank"               # Missing/invalid bank
    TIME = "time"               # Vague time reference
    INTENT = "intent"           # Unclear intent/visualization
    COMPARISON = "comparison"   # Unclear comparison
    MULTI_METRIC = "multi"      # Multiple metrics
    OUT_OF_DOMAIN = "ood"       # Out of domain query
    AMBIGUOUS_TERM = "ambiguous" # Ambiguous term like "cartera", "riesgo"


@dataclass
class TestCase:
    """Single test case for clarification."""
    id: str
    category: str
    query: str
    expected_clarification: bool
    clarification_type: Optional[ClarificationType]
    description: str
    expected_keywords: List[str] = None  # Keywords expected in clarification message

    def __post_init__(self):
        if self.expected_keywords is None:
            self.expected_keywords = []


# ============================================================================
# TEST CASES - From GUIA_CONSULTAS_AMBIGUAS.md + hostile_queries.json
# ============================================================================

TEST_CASES: List[TestCase] = [
    # -------------------------------------------------------------------------
    # METRIC AMBIGUITY (MF = Missing Field)
    # -------------------------------------------------------------------------
    TestCase(
        id="MF-001",
        category="Métrica",
        query="datos del banco",
        expected_clarification=True,
        clarification_type=ClarificationType.METRIC,
        description="No metric specified - should ask which metric",
        expected_keywords=["métrica", "indicador", "qué"]
    ),
    TestCase(
        id="MF-002",
        category="Completo",
        query="ultimo mes",
        expected_clarification=True,
        clarification_type=ClarificationType.METRIC,
        description="Missing everything - should ask for metric",
        expected_keywords=["métrica", "indicador"]
    ),
    TestCase(
        id="MF-004",
        category="Métrica",
        query="INVEX 2024",
        expected_clarification=True,
        clarification_type=ClarificationType.METRIC,
        description="Bank and year but no metric - should ask which metric",
        expected_keywords=["métrica", "indicador", "qué"]
    ),
    TestCase(
        id="MF-005",
        category="Banco/Tiempo",
        query="morosidad",
        expected_clarification=True,
        clarification_type=ClarificationType.BANK,
        description="Metric found (morosidad=IMOR) but no bank - should ask which bank",
        expected_keywords=["entidad", "banco", "INVEX", "Sistema"]
    ),

    # -------------------------------------------------------------------------
    # BANK AMBIGUITY (IB = Invalid Bank)
    # -------------------------------------------------------------------------
    TestCase(
        id="IB-001",
        category="Banco",
        query="IMOR de BancoFantasma",
        expected_clarification=True,
        clarification_type=ClarificationType.BANK,
        description="Invalid bank name - should ask for valid bank",
        expected_keywords=["entidad", "INVEX", "Sistema"]
    ),
    TestCase(
        id="IB-004",
        category="Banco",
        query="IMOR de Bank of America",
        expected_clarification=True,
        clarification_type=ClarificationType.BANK,
        description="Bank not in dataset - should ask for available banks",
        expected_keywords=["entidad", "INVEX", "Sistema"]
    ),
    TestCase(
        id="BANK-001",
        category="Banco",
        query="IMOR actual",
        expected_clarification=True,
        clarification_type=ClarificationType.BANK,
        description="Metric found but no bank - should ask which bank",
        expected_keywords=["entidad", "qué", "INVEX"]
    ),

    # -------------------------------------------------------------------------
    # TIME AMBIGUITY
    # -------------------------------------------------------------------------
    TestCase(
        id="TIME-001",
        category="Tiempo",
        query="IMOR de INVEX reciente",
        expected_clarification=True,
        clarification_type=ClarificationType.TIME,
        description="Vague time 'reciente' - should ask for specific period",
        expected_keywords=["período", "tiempo", "meses"]
    ),
    TestCase(
        id="TIME-002",
        category="Tiempo",
        query="evolución del ICOR de INVEX",
        expected_clarification=True,
        clarification_type=ClarificationType.TIME,
        description="'evolución' implies time but no range - should ask period",
        expected_keywords=["período", "tiempo"]
    ),
    TestCase(
        id="TIME-003",
        category="Tiempo",
        query="tendencia histórica de morosidad",
        expected_clarification=True,
        clarification_type=ClarificationType.TIME,
        description="'histórica' is vague - should ask specific range",
        expected_keywords=["período", "tiempo"]
    ),

    # -------------------------------------------------------------------------
    # COMPARISON AMBIGUITY
    # -------------------------------------------------------------------------
    TestCase(
        id="CMP-001",
        category="Comparación",
        query="compara el IMOR",
        expected_clarification=True,
        clarification_type=ClarificationType.COMPARISON,
        description="Comparison without targets - should ask what to compare",
        expected_keywords=["comparación", "tipo", "INVEX", "Sistema"]
    ),
    TestCase(
        id="CMP-002",
        category="Comparación",
        query="diferencia de morosidad",
        expected_clarification=True,
        clarification_type=ClarificationType.COMPARISON,
        description="'diferencia' implies comparison - should ask targets",
        expected_keywords=["comparación", "tipo"]
    ),

    # -------------------------------------------------------------------------
    # MULTI-METRIC AMBIGUITY (MM)
    # -------------------------------------------------------------------------
    TestCase(
        id="MM-001",
        category="Multi",
        query="IMOR y ICOR de INVEX",
        expected_clarification=True,
        clarification_type=ClarificationType.MULTI_METRIC,
        description="Multiple metrics - should ask how to visualize",
        expected_keywords=["métricas", "visualizar", "gráfica"]
    ),
    TestCase(
        id="MM-002",
        category="Multi",
        query="morosidad e índice de cobertura",
        expected_clarification=True,
        clarification_type=ClarificationType.MULTI_METRIC,
        description="Multiple metrics with 'e' - should ask visualization",
        expected_keywords=["métricas", "visualizar"]
    ),
    TestCase(
        id="MM-003",
        category="Multi",
        query="todas las metricas",
        expected_clarification=True,
        clarification_type=ClarificationType.METRIC,
        description="Too broad - should ask for specific metric",
        expected_keywords=["métrica", "cuál"]
    ),
    TestCase(
        id="MM-005",
        category="Multi",
        query="resumen financiero",
        expected_clarification=True,
        clarification_type=ClarificationType.METRIC,
        description="Ambiguous - should ask what metric",
        expected_keywords=["métrica", "indicador"]
    ),

    # -------------------------------------------------------------------------
    # AMBIGUOUS TERMS (cartera, riesgo, etc.)
    # -------------------------------------------------------------------------
    TestCase(
        id="AMB-001",
        category="Ambiguo",
        query="cartera de INVEX",
        expected_clarification=True,
        clarification_type=ClarificationType.AMBIGUOUS_TERM,
        description="'cartera' is ambiguous - should ask which type",
        expected_keywords=["cartera", "tipo", "comercial", "consumo"]
    ),
    TestCase(
        id="AMB-002",
        category="Ambiguo",
        query="indicadores de riesgo",
        expected_clarification=True,
        clarification_type=ClarificationType.AMBIGUOUS_TERM,
        description="'riesgo' is ambiguous - should ask which indicator",
        expected_keywords=["riesgo", "IMOR", "ICOR"]
    ),
    TestCase(
        id="AMB-003",
        category="Ambiguo",
        query="tasa de INVEX",
        expected_clarification=True,
        clarification_type=ClarificationType.AMBIGUOUS_TERM,
        description="'tasa' is ambiguous - should ask which rate",
        expected_keywords=["tasa", "tipo"]
    ),

    # -------------------------------------------------------------------------
    # OUT OF DOMAIN (NS = Non-Sense / OOD)
    # -------------------------------------------------------------------------
    TestCase(
        id="NS-002",
        category="Irrelevante",
        query="clima en Cancun",
        expected_clarification=True,
        clarification_type=ClarificationType.OUT_OF_DOMAIN,
        description="Out of domain - should ask for banking query",
        expected_keywords=["métrica", "indicador"]
    ),
    TestCase(
        id="NS-006",
        category="Social",
        query="hola buenos dias",
        expected_clarification=True,
        clarification_type=ClarificationType.OUT_OF_DOMAIN,
        description="Greeting not query - should ask for metric",
        expected_keywords=["métrica", "indicador"]
    ),

    # -------------------------------------------------------------------------
    # SHOULD NOT TRIGGER CLARIFICATION (negative tests)
    # -------------------------------------------------------------------------
    TestCase(
        id="OK-001",
        category="Válida",
        query="IMOR de INVEX últimos 3 meses",
        expected_clarification=False,
        clarification_type=None,
        description="Complete query - should NOT ask clarification",
        expected_keywords=[]
    ),
    TestCase(
        id="OK-002",
        category="Válida",
        query="cartera comercial de INVEX 2024",
        expected_clarification=False,
        clarification_type=None,
        description="Specific cartera type - should NOT ask clarification",
        expected_keywords=[]
    ),
]


def send_query(url: str, query: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Send a query to bank-advisor RPC endpoint."""
    payload = {
        "jsonrpc": "2.0",
        "id": f"test-{query[:20]}",
        "method": "tools/call",
        "params": {
            "name": "bank_analytics",
            "arguments": {
                "metric_or_query": query,
                "mode": "dashboard"
            }
        }
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def parse_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Parse JSON-RPC response and extract the actual data."""
    if "error" in response:
        return {"error": response["error"]}

    result = response.get("result", {})
    content = result.get("content", [])

    if content and isinstance(content[0], dict) and "text" in content[0]:
        try:
            data = json.loads(content[0]["text"])
            # Handle wrapped response
            if "data" in data:
                return data["data"]
            return data
        except json.JSONDecodeError:
            return {"raw": content[0]["text"]}

    return result


def is_clarification_response(data: Dict[str, Any]) -> bool:
    """Check if response is a clarification request."""
    return data.get("type") == "clarification"


def normalize_spanish(text: str) -> str:
    """Remove accents and normalize Spanish text for comparison."""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u', '¿': '', '¡': ''
    }
    result = text.lower()
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def check_keywords(message: str, keywords: List[str]) -> List[str]:
    """Check which expected keywords are present in message (accent-insensitive)."""
    message_normalized = normalize_spanish(message)
    found = [kw for kw in keywords if normalize_spanish(kw) in message_normalized]
    missing = [kw for kw in keywords if normalize_spanish(kw) not in message_normalized]
    return found, missing


def run_test(test: TestCase, url: str, verbose: bool = False) -> bool:
    """Run a single test case and return success status."""
    try:
        response = send_query(url, test.query)
        data = parse_response(response)

        is_clarification = is_clarification_response(data)

        # Check if result matches expectation (MAIN TEST)
        if test.expected_clarification:
            success = is_clarification
        else:
            success = not is_clarification

        # Print result
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if success else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  [{status}] {test.id}: {test.query[:40]}...")

        if verbose:
            print(f"       Expected clarification: {test.expected_clarification}")
            print(f"       Got clarification: {is_clarification}")
            if is_clarification:
                print(f"       Message: {data.get('message', 'N/A')[:60]}...")
                options = data.get("options", [])
                print(f"       Options: {[o.get('label', o.get('id')) for o in options[:4]]}")

        if not success:
            print(f"       {Colors.RED}Expected clarification: {test.expected_clarification}, Got: {is_clarification}{Colors.RESET}")
            if is_clarification:
                print(f"       Message: {data.get('message', 'N/A')[:60]}...")

        return success

    except Exception as e:
        print(f"  [{Colors.RED}ERROR{Colors.RESET}] {test.id}: {test.query[:40]}...")
        print(f"       Error: {str(e)}")
        return False


def run_all_tests(url: str, verbose: bool = False, category_filter: str = None):
    """Run all test cases."""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}HU3.4 Clarification Tests{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"URL: {url}")
    print(f"Total test cases: {len(TEST_CASES)}")
    print()

    # Group tests by category
    categories = {}
    for test in TEST_CASES:
        if category_filter and category_filter.lower() not in test.category.lower():
            continue
        if test.category not in categories:
            categories[test.category] = []
        categories[test.category].append(test)

    total_passed = 0
    total_failed = 0

    for category, tests in categories.items():
        print(f"\n{Colors.CYAN}{Colors.BOLD}Category: {category}{Colors.RESET}")
        print("-" * 50)

        for test in tests:
            if run_test(test, url, verbose):
                total_passed += 1
            else:
                total_failed += 1

    # Summary
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}SUMMARY{Colors.RESET}")
    print(f"{'='*70}")
    total = total_passed + total_failed
    pass_rate = (total_passed / total * 100) if total > 0 else 0

    if total_failed == 0:
        print(f"{Colors.GREEN}All {total_passed} tests passed!{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}Passed: {total_passed}{Colors.RESET}")
        print(f"{Colors.RED}Failed: {total_failed}{Colors.RESET}")
        print(f"Pass rate: {pass_rate:.1f}%")

    return total_failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="Test HU3.4 clarification scenarios"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8002/rpc",
        help="Bank-advisor RPC endpoint URL"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output for all tests"
    )
    parser.add_argument(
        "--category", "-c",
        help="Filter tests by category (e.g., 'Métrica', 'Banco', 'Tiempo')"
    )

    args = parser.parse_args()

    success = run_all_tests(args.url, args.verbose, args.category)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
