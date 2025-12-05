#!/usr/bin/env python3
"""
E2E Integration Test for BankAdvisor NL2SQL Frontend Integration (BA-P0-003)

Tests the complete flow:
1. User authenticates with demo@example.com
2. Sends "IMOR de INVEX en 2024" message
3. Backend detects banking query
4. Calls bank-advisor RPC endpoint
5. NL2SQL pipeline generates SQL and chart data
6. Artifact created in MongoDB
7. Response includes artifact_id
8. Frontend can fetch artifact content

Requirements:
- Docker containers running (backend, bank-advisor, postgres, mongodb)
- Demo user exists (demo@example.com / Demo1234)
- Database populated with 191 records
"""

import pytest
import httpx
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import time
import sys

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E_BANK_ANALYTICS", "false").lower() != "true",
    reason="Bank analytics E2E deshabilitado por defecto (requires full stack running)",
)

# Test configuration
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
BANK_ADVISOR_URL = os.getenv("BANK_ADVISOR_URL", "http://localhost:8002")
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
            json={"identifier": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )

        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("access_token")
            print(f"✅ Logged in as {DEMO_EMAIL}")
            return token

        # If login failed, try to create demo user
        print(f"⚠️  Login failed, attempting to create demo user...")

        # Create demo user via script
        import subprocess
        result = subprocess.run(
            [sys.executable, "apps/backend/scripts/create_demo_user.py"],
            capture_output=True,
            text=True,
            cwd="/home/jazielflo/Proyects/octavios-chat-bajaware_invex"
        )

        if result.returncode != 0:
            pytest.fail(f"Failed to create demo user: {result.stderr}")

        # Try login again
        login_response = await client.post(
            "/api/auth/login",
            json={"identifier": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )

        if login_response.status_code != 200:
            pytest.fail(f"Failed to login after creating user: {login_response.text}")

        data = login_response.json()
        token = data.get("access_token")
        print(f"✅ Demo user created and logged in")
        return token


@pytest.fixture(scope="module")
async def mongo_client():
    """MongoDB client for artifact verification"""
    client = AsyncIOMotorClient(MONGODB_URI)
    yield client
    client.close()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_bank_analytics_e2e_flow(auth_token, mongo_client):
    """
    E2E Test: Complete BankAdvisor integration flow

    Steps:
    1. Create new chat session
    2. Send banking query: "IMOR de INVEX en 2024"
    3. Verify backend response includes artifact
    4. Verify artifact persisted in MongoDB
    5. Fetch artifact via API
    6. Verify BankChartData structure
    """

    headers = {"Authorization": f"Bearer {auth_token}"}

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        # Step 1: Create new chat session
        print("\n📝 Step 1: Creating new chat session...")
        session_response = await client.post(
            "/api/chat/sessions",
            headers=headers,
            json={"title": "Test BankAdvisor Integration"}
        )

        assert session_response.status_code == 201, f"Failed to create session: {session_response.text}"
        session_data = session_response.json()
        chat_id = session_data["id"]
        print(f"✅ Chat session created: {chat_id}")

        # Step 2: Send banking query
        print("\n💬 Step 2: Sending banking query...")
        query = "IMOR de INVEX en 2024"

        start_time = time.time()
        message_response = await client.post(
            f"/api/chat/sessions/{chat_id}/messages",
            headers=headers,
            json={"content": query}
        )
        elapsed_time = time.time() - start_time

        assert message_response.status_code == 200, f"Failed to send message: {message_response.text}"
        message_data = message_response.json()
        print(f"✅ Message sent and response received in {elapsed_time:.2f}s")

        # Verify response structure
        assert "id" in message_data, "Response missing message id"
        assert "content" in message_data, "Response missing content"

        print(f"📊 Response preview: {message_data['content'][:100]}...")

        # Step 3: Verify metadata includes artifact reference
        print("\n🔍 Step 3: Checking for artifact reference...")
        metadata = message_data.get("metadata", {})
        tool_invocations = metadata.get("tool_invocations", [])

        # Find bank_analytics artifact
        artifact_id = None
        for invocation in tool_invocations:
            if invocation.get("tool_name") == "create_artifact":
                result = invocation.get("result", {})
                if result.get("type") == "bank_chart":
                    artifact_id = result.get("id")
                    print(f"✅ Found bank_chart artifact: {artifact_id}")
                    break

        if not artifact_id:
            print(f"⚠️  No artifact found in tool_invocations")
            print(f"Tool invocations: {tool_invocations}")
            # Don't fail yet - check MongoDB directly

            # Query MongoDB for artifacts created in this session
            db = mongo_client[MONGODB_DB]
            artifacts = await db.artifacts.find(
                {
                    "chat_session_id": chat_id,
                    "type": "bank_chart"
                }
            ).to_list(length=10)

            if artifacts:
                artifact_id = artifacts[0]["_id"]
                print(f"✅ Found artifact in MongoDB: {artifact_id}")
            else:
                pytest.fail("No bank_chart artifact created")

        # Step 4: Verify artifact in MongoDB
        print("\n💾 Step 4: Verifying artifact in MongoDB...")
        db = mongo_client[MONGODB_DB]
        artifact_doc = await db.artifacts.find_one({"_id": artifact_id})

        assert artifact_doc is not None, f"Artifact {artifact_id} not found in MongoDB"
        assert artifact_doc["type"] == "bank_chart", "Artifact type is not bank_chart"
        assert "content" in artifact_doc, "Artifact missing content"

        content = artifact_doc["content"]
        print(f"✅ Artifact verified in MongoDB")
        print(f"   Type: {artifact_doc['type']}")
        print(f"   Title: {artifact_doc['title']}")
        print(f"   Created: {artifact_doc['created_at']}")

        # Step 5: Fetch artifact via API (simulate frontend)
        print("\n🌐 Step 5: Fetching artifact via API...")
        artifact_response = await client.get(
            f"/api/artifacts/{artifact_id}",
            headers=headers
        )

        assert artifact_response.status_code == 200, f"Failed to fetch artifact: {artifact_response.text}"
        artifact_data = artifact_response.json()
        print(f"✅ Artifact fetched via API")

        # Step 6: Verify BankChartData structure
        print("\n🔬 Step 6: Validating BankChartData structure...")
        content = artifact_data["content"]

        # Required fields
        assert content["type"] == "bank_chart", "Missing or wrong type"
        assert "metric_name" in content, "Missing metric_name"
        assert "bank_names" in content, "Missing bank_names"
        assert "time_range" in content, "Missing time_range"
        assert "plotly_config" in content, "Missing plotly_config"
        assert "data_as_of" in content, "Missing data_as_of"

        # Verify Plotly config structure
        plotly_config = content["plotly_config"]
        assert "data" in plotly_config, "Missing plotly_config.data"
        assert "layout" in plotly_config, "Missing plotly_config.layout"
        assert isinstance(plotly_config["data"], list), "plotly_config.data is not a list"
        assert len(plotly_config["data"]) > 0, "plotly_config.data is empty"

        # Verify data points
        first_trace = plotly_config["data"][0]
        assert "x" in first_trace, "Missing x axis data"
        assert "y" in first_trace, "Missing y axis data"
        assert isinstance(first_trace["x"], list), "x is not a list"
        assert isinstance(first_trace["y"], list), "y is not a list"

        print(f"✅ BankChartData structure valid")
        print(f"   Metric: {content['metric_name']}")
        print(f"   Banks: {', '.join(content['bank_names'])}")
        print(f"   Data points: {len(first_trace['x'])}")
        print(f"   Time range: {content['time_range']['start']} to {content['time_range']['end']}")

        # Performance check
        if elapsed_time < 3.0:
            print(f"\n✅ Performance PASS: Response time {elapsed_time:.2f}s < 3s target")
        else:
            print(f"\n⚠️  Performance WARNING: Response time {elapsed_time:.2f}s > 3s target")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_bank_advisor_health():
    """Verify bank-advisor service is healthy"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{BANK_ADVISOR_URL}/health")
        assert response.status_code == 200, f"Bank advisor unhealthy: {response.text}"
        data = response.json()
        assert data["status"] == "healthy", f"Bank advisor status: {data['status']}"
        print(f"✅ Bank advisor healthy: {data}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_bank_advisor_direct_rpc():
    """Test bank-advisor RPC endpoint directly"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "test-rpc",
            "method": "tools/call",
            "params": {
                "name": "bank_analytics",
                "arguments": {
                    "metric_or_query": "IMOR de INVEX en 2024",
                    "mode": "dashboard"
                }
            }
        }

        response = await client.post(
            f"{BANK_ADVISOR_URL}/rpc",
            json=payload
        )

        assert response.status_code == 200, f"RPC failed: {response.text}"
        data = response.json()

        assert "result" in data, "RPC response missing result"
        assert "content" in data["result"], "RPC result missing content"

        # Parse nested content
        import json
        content = data["result"]["content"]
        if isinstance(content, list) and len(content) > 0:
            text = content[0].get("text")
            if text:
                parsed = json.loads(text)

                # Check for enhanced metadata wrapper (v1.0.0+)
                if "success" in parsed and "data" in parsed:
                    print(f"✅ Enhanced metadata format detected")
                    assert parsed["success"] is True, "RPC returned success=false"
                    assert "metadata" in parsed, "Missing metadata wrapper"

                    metadata = parsed["metadata"]
                    print(f"   Version: {metadata.get('version')}")
                    print(f"   Pipeline: {metadata.get('pipeline')}")
                    print(f"   Execution time: {metadata.get('execution_time_ms')}ms")

                    # Verify data payload
                    data_payload = parsed["data"]
                    assert "plotly_config" in data_payload, "Missing plotly_config in data"
                    print(f"✅ RPC response structure valid")
                else:
                    print(f"⚠️  Legacy format (no metadata wrapper)")


if __name__ == "__main__":
    """Run tests with pytest"""
    import sys

    # Check if services are running
    print("🔍 Pre-flight checks...")

    try:
        import requests

        # Check backend
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code != 200:
            print(f"❌ Backend not healthy at {BASE_URL}")
            sys.exit(1)
        print(f"✅ Backend healthy at {BASE_URL}")

        # Check bank-advisor
        r = requests.get(f"{BANK_ADVISOR_URL}/health", timeout=5)
        if r.status_code != 200:
            print(f"❌ Bank advisor not healthy at {BANK_ADVISOR_URL}")
            sys.exit(1)
        print(f"✅ Bank advisor healthy at {BANK_ADVISOR_URL}")

    except Exception as e:
        print(f"❌ Pre-flight check failed: {e}")
        sys.exit(1)

    print("\n🚀 Running E2E tests...\n")
    sys.exit(pytest.main([__file__, "-v", "-s", "-m", "e2e"]))
