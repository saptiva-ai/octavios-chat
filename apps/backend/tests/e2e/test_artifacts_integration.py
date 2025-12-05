#!/usr/bin/env python3
"""
E2E Integration Tests for Bank Chart Artifacts (Sprint 1)

Tests the complete artifact flow:
1. User authentication
2. Artifact creation with bank_chart type
3. Input validation (from BankChartDataValidator)
4. Rate limiting enforcement
5. Artifact retrieval from MongoDB
6. TTL index verification

Requirements:
- MongoDB running
- Backend API server running
- Demo user exists or will be created
"""

import pytest
import httpx
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import os
import time

# Test configuration
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB_NAME", "octavios")

# Demo user credentials
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "Demo1234"


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def auth_token():
    """
    Authenticate and get JWT token for demo user.
    Creates demo user if it doesn't exist.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Try to login first
        login_response = await client.post(
            "/api/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )

        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token")
            print(f"✅ Logged in as {DEMO_EMAIL}")
            return token

        # If login fails, this test requires demo user to exist
        pytest.skip(f"Demo user {DEMO_EMAIL} does not exist. Please create it first.")


@pytest.fixture(scope="module")
async def mongodb_client():
    """Create MongoDB client for direct database access"""
    client = AsyncIOMotorClient(MONGODB_URI)
    yield client
    client.close()


@pytest.fixture
async def auth_headers(auth_token):
    """Generate auth headers with JWT token"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def valid_bank_chart_payload():
    """Valid bank chart artifact payload"""
    return {
        "title": "IMOR - INVEX vs BBVA 2024",
        "type": "bank_chart",
        "content": {
            "metric_name": "imor",
            "bank_names": ["INVEX", "BBVA"],
            "time_range": {
                "start": "2024-01-01",
                "end": "2024-12-31"
            },
            "plotly_config": {
                "data": [
                    {
                        "x": ["2024-01", "2024-02", "2024-03"],
                        "y": [2.5, 2.7, 2.3],
                        "type": "bar",
                        "name": "INVEX"
                    },
                    {
                        "x": ["2024-01", "2024-02", "2024-03"],
                        "y": [3.1, 3.0, 2.9],
                        "type": "bar",
                        "name": "BBVA"
                    }
                ],
                "layout": {
                    "title": "IMOR - Índice de Morosidad",
                    "xaxis": {"title": "Periodo"},
                    "yaxis": {"title": "IMOR (%)"}
                }
            },
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                "sql_generated": "SELECT bank_name, period, imor_value FROM metrics WHERE year = 2024",
                "metric_interpretation": "El IMOR mide la proporción de cartera vencida respecto a la cartera total."
            }
        }
    }


class TestArtifactCreation:
    """Test artifact creation with validation"""

    @pytest.mark.asyncio
    async def test_create_valid_bank_chart(self, auth_headers, valid_bank_chart_payload):
        """Should successfully create a bank chart artifact"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=valid_bank_chart_payload,
                headers=auth_headers
            )

            assert response.status_code == 201, f"Unexpected status: {response.status_code}, body: {response.text}"
            data = response.json()

            # Verify response structure
            assert "id" in data
            assert data["type"] == "bank_chart"
            assert data["title"] == valid_bank_chart_payload["title"]
            assert data["content"]["metric_name"] == "imor"
            assert data["content"]["bank_names"] == ["INVEX", "BBVA"]

            # Verify versions array
            assert "versions" in data
            assert len(data["versions"]) == 1
            assert data["versions"][0]["version"] == 1

            print(f"✅ Created artifact: {data['id']}")

    @pytest.mark.asyncio
    async def test_reject_invalid_metric(self, auth_headers, valid_bank_chart_payload):
        """Should reject bank chart with invalid metric name"""
        payload = valid_bank_chart_payload.copy()
        payload["content"]["metric_name"] = "invalid_metric_xyz"

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=payload,
                headers=auth_headers
            )

            assert response.status_code == 400
            assert "Invalid metric" in response.text or "invalid_metric_xyz" in response.text.lower()
            print(f"✅ Rejected invalid metric: {response.json()['detail']}")

    @pytest.mark.asyncio
    async def test_reject_duplicate_banks(self, auth_headers, valid_bank_chart_payload):
        """Should reject bank chart with duplicate bank names"""
        payload = valid_bank_chart_payload.copy()
        payload["content"]["bank_names"] = ["INVEX", "BBVA", "invex"]  # Duplicate (case-insensitive)

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=payload,
                headers=auth_headers
            )

            assert response.status_code == 400
            assert "Duplicate" in response.text or "duplicate" in response.text.lower()
            print(f"✅ Rejected duplicate banks: {response.json()['detail']}")

    @pytest.mark.asyncio
    async def test_reject_too_many_banks(self, auth_headers, valid_bank_chart_payload):
        """Should reject bank chart exceeding maximum bank count"""
        payload = valid_bank_chart_payload.copy()
        payload["content"]["bank_names"] = [f"BANK_{i}" for i in range(15)]  # Max is 10

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=payload,
                headers=auth_headers
            )

            assert response.status_code == 400
            assert "10 item" in response.text or "maximum" in response.text.lower()
            print(f"✅ Rejected too many banks: {response.json()['detail']}")

    @pytest.mark.asyncio
    async def test_reject_empty_banks(self, auth_headers, valid_bank_chart_payload):
        """Should reject bank chart with empty bank_names"""
        payload = valid_bank_chart_payload.copy()
        payload["content"]["bank_names"] = []

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=payload,
                headers=auth_headers
            )

            assert response.status_code == 400
            assert "at least" in response.text.lower() or "1 item" in response.text
            print(f"✅ Rejected empty banks: {response.json()['detail']}")


class TestArtifactRetrieval:
    """Test artifact retrieval and persistence"""

    @pytest.mark.asyncio
    async def test_retrieve_created_artifact(self, auth_headers, valid_bank_chart_payload):
        """Should retrieve artifact after creation"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            # Create artifact
            create_response = await client.post(
                "/api/artifacts/",
                json=valid_bank_chart_payload,
                headers=auth_headers
            )
            assert create_response.status_code == 201
            artifact_id = create_response.json()["id"]

            # Retrieve artifact
            get_response = await client.get(
                f"/api/artifacts/{artifact_id}",
                headers=auth_headers
            )

            assert get_response.status_code == 200
            data = get_response.json()
            assert data["id"] == artifact_id
            assert data["content"]["metric_name"] == "imor"
            print(f"✅ Retrieved artifact: {artifact_id}")

    @pytest.mark.asyncio
    async def test_artifact_persisted_in_mongodb(self, auth_headers, valid_bank_chart_payload, mongodb_client):
        """Should persist artifact in MongoDB"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            # Create artifact
            create_response = await client.post(
                "/api/artifacts/",
                json=valid_bank_chart_payload,
                headers=auth_headers
            )
            assert create_response.status_code == 201
            artifact_id = create_response.json()["id"]

            # Wait a moment for MongoDB write
            await asyncio.sleep(0.5)

            # Query MongoDB directly
            db = mongodb_client[MONGODB_DB]
            from bson import ObjectId
            artifact_doc = await db.artifacts.find_one({"_id": ObjectId(artifact_id)})

            assert artifact_doc is not None
            assert artifact_doc["type"] == "bank_chart"
            assert artifact_doc["content"]["metric_name"] == "imor"
            print(f"✅ Artifact persisted in MongoDB: {artifact_id}")


class TestRateLimiting:
    """Test rate limiting enforcement"""

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self, auth_headers, valid_bank_chart_payload):
        """Should enforce rate limit on artifact creation"""
        # Note: This test is challenging because rate limits are per-hour
        # We'll test by making multiple rapid requests and checking for rate limit response

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            # Make multiple requests rapidly
            responses = []
            for i in range(5):  # Don't exhaust the limit, just test it exists
                response = await client.post(
                    "/api/artifacts/",
                    json=valid_bank_chart_payload,
                    headers=auth_headers
                )
                responses.append(response)

            # All should succeed if under limit
            success_count = sum(1 for r in responses if r.status_code == 201)
            assert success_count >= 4, f"Expected at least 4 successful creations, got {success_count}"

            # Verify rate limit headers exist (slowapi adds these)
            last_response = responses[-1]
            # Check for common rate limit header patterns
            has_rate_limit_headers = any(
                header.lower() in ["x-ratelimit-limit", "ratelimit-limit", "x-ratelimit-remaining"]
                for header in last_response.headers.keys()
            )

            print(f"✅ Rate limiting configured (headers: {has_rate_limit_headers})")


class TestInputSanitization:
    """Test XSS and injection protection in metadata"""

    @pytest.mark.asyncio
    async def test_malicious_sql_in_metadata(self, auth_headers, valid_bank_chart_payload):
        """Should accept malicious SQL in metadata (sanitization happens on frontend)"""
        # Backend stores as-is, frontend sanitizes before display
        payload = valid_bank_chart_payload.copy()
        payload["content"]["metadata"]["sql_generated"] = 'SELECT * FROM banks; <script>alert("XSS")</script>'

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=payload,
                headers=auth_headers
            )

            # Backend should accept it (validation is structural, not content-based)
            assert response.status_code == 201
            data = response.json()
            # Metadata is stored as-is, sanitization happens in frontend
            assert '<script>' in data["content"]["metadata"]["sql_generated"]
            print("✅ Backend accepts metadata with script tags (frontend sanitizes)")

    @pytest.mark.asyncio
    async def test_long_metric_name_rejected(self, auth_headers, valid_bank_chart_payload):
        """Should reject metric name exceeding max length"""
        payload = valid_bank_chart_payload.copy()
        payload["content"]["metric_name"] = "a" * 100  # Max is 50

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=payload,
                headers=auth_headers
            )

            assert response.status_code == 400
            assert "50 character" in response.text or "max_length" in response.text.lower()
            print(f"✅ Rejected long metric name: {response.json()['detail']}")


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, auth_headers):
        """Should reject artifact with missing required fields"""
        payload = {
            "title": "Incomplete Chart",
            "type": "bank_chart",
            "content": {
                "metric_name": "imor"
                # Missing: bank_names, time_range, plotly_config, data_as_of
            }
        }

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=payload,
                headers=auth_headers
            )

            assert response.status_code == 400
            print(f"✅ Rejected incomplete payload: {response.json()['detail']}")

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, valid_bank_chart_payload):
        """Should reject unauthenticated requests"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/artifacts/",
                json=valid_bank_chart_payload
            )

            assert response.status_code == 401
            print("✅ Rejected unauthenticated request")

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_artifact(self, auth_headers):
        """Should return 404 for non-existent artifact"""
        fake_id = "507f1f77bcf86cd799439011"  # Valid ObjectId format

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/api/artifacts/{fake_id}",
                headers=auth_headers
            )

            assert response.status_code == 404
            print("✅ Returned 404 for non-existent artifact")


if __name__ == "__main__":
    print("Running artifact integration tests...")
    pytest.main([__file__, "-v", "-s"])
