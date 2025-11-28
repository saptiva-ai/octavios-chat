"""
Pytest configuration and shared fixtures for BankAdvisor tests.

Marker Registration:
- @pytest.mark.unit: Fast unit tests, no external deps
- @pytest.mark.integration: Integration tests, may need DB
- @pytest.mark.nl2sql_dirty: Hostile query tests (BA-QA-001)
- @pytest.mark.ba_null_001: NULL handling tests for ICAP/TDA/TASA
"""

import pytest
import sys
from pathlib import Path

# Ensure src is in path for imports
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (may require DB or services)"
    )
    config.addinivalue_line(
        "markers", "nl2sql_dirty: NL2SQL Dirty Data / Hostile Query tests (BA-QA-001)"
    )
    config.addinivalue_line(
        "markers", "ba_null_001: BA-NULL-001 NULL handling tests for ICAP/TDA/TASA metrics"
    )


@pytest.fixture(scope="session")
def test_data_path():
    """Path to test data directory."""
    return Path(__file__).parent.parent.parent.parent / "tests" / "data"


@pytest.fixture(scope="session")
def hostile_queries_path(test_data_path):
    """Path to hostile queries JSON file."""
    return test_data_path / "hostile_queries.json"
