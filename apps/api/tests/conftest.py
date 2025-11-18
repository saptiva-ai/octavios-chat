"""
Pytest configuration and fixtures for API tests.

This file is automatically loaded by pytest before running tests.
It configures the Python path to enable proper imports.
"""

import sys
from pathlib import Path

# Add the app directory to Python path (not src/)
# This allows tests to import as: from src.main import app
# This way, src is treated as a package and relative imports work
app_path = Path(__file__).parent.parent
if str(app_path) not in sys.path:
    sys.path.append(str(app_path))

print(f"✓ Added {app_path} to PYTHONPATH for tests (import as: from src.module import ...)")

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from src.mcp.versioning import versioned_registry
from src.core.database import Database


@pytest_asyncio.fixture(scope="session", autouse=True)
async def initialize_database():
    """Initialize database connection for all tests."""
    await Database.connect_to_mongo()
    yield
    await Database.close_mongo_connection()


@pytest.fixture(autouse=True)
def reset_versioned_registry():
    """Ensure versioned tool registry is isolated per test."""
    versioned_registry._tools.clear()
    versioned_registry._latest.clear()
    versioned_registry._deprecated.clear()
    yield
    versioned_registry._tools.clear()
    versioned_registry._latest.clear()
    versioned_registry._deprecated.clear()
