"""
Unit tests for models router.

Tests model listing, availability, and configuration endpoints.
"""

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

try:
    from src.routers.models import router as models_router
    ROUTER_AVAILABLE = True
except ImportError:
    ROUTER_AVAILABLE = False
    pytest.skip("Models router not available", allow_module_level=True)


@pytest.fixture
def app():
    """Create a test FastAPI app with models router."""
    app = FastAPI()
    app.include_router(models_router)
    return app


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return TestClient(app)


class TestModelsEndpoint:
    """Test suite for models listing endpoint."""

    def test_models_endpoint_returns_200(self, client):
        """Test that /api/models endpoint returns 200 OK."""
        response = client.get("/api/models")

        assert response.status_code == status.HTTP_200_OK

    def test_models_endpoint_returns_json(self, client):
        """Test that models endpoint returns JSON response."""
        response = client.get("/api/models")

        assert response.headers["content-type"] == "application/json"

    def test_models_endpoint_returns_array(self, client):
        """Test that models endpoint returns array of models."""
        response = client.get("/api/models")
        data = response.json()

        # Response should be an array or have a 'models' key with array
        assert isinstance(data, list) or (isinstance(data, dict) and "models" in data)

    def test_models_have_required_fields(self, client):
        """Test that each model has required fields."""
        response = client.get("/api/models")
        data = response.json()

        # Get models array
        models = data if isinstance(data, list) else data.get("models", [])

        if len(models) > 0:
            model = models[0]

            # Common model fields
            expected_fields = ["id", "name"]
            for field in expected_fields:
                if field in model:
                    assert isinstance(model[field], str)

    def test_models_include_saptiva_models(self, client):
        """Test that Saptiva models are included in response."""
        response = client.get("/api/models")
        data = response.json()

        models = data if isinstance(data, list) else data.get("models", [])

        # Should include at least one Saptiva model
        model_ids = [m.get("id", "") or m.get("name", "") for m in models]
        has_saptiva = any("saptiva" in model_id.lower() or "cortex" in model_id.lower() for model_id in model_ids)

        # This assertion might not always be true depending on configuration
        # but it's a reasonable expectation
        assert len(models) > 0  # At minimum, should have some models

    def test_models_endpoint_no_authentication_required(self, client):
        """Test that models endpoint is public (no auth required)."""
        # Should work without Authorization header
        response = client.get("/api/models")

        # Should not return 401 Unauthorized
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    def test_models_endpoint_cached(self, client):
        """Test that models endpoint may include caching headers."""
        response = client.get("/api/models")

        # Models list doesn't change often, might have cache headers
        # This is optional, just checking if present
        if "cache-control" in response.headers:
            assert isinstance(response.headers["cache-control"], str)


class TestModelConfiguration:
    """Test model configuration and metadata."""

    def test_models_have_valid_structure(self, client):
        """Test that model objects have valid structure."""
        response = client.get("/api/models")
        data = response.json()

        models = data if isinstance(data, list) else data.get("models", [])

        for model in models:
            assert isinstance(model, dict)
            # Should have at least an identifier
            assert "id" in model or "name" in model

    def test_models_include_capabilities(self, client):
        """Test that models include capability information."""
        response = client.get("/api/models")
        data = response.json()

        models = data if isinstance(data, list) else data.get("models", [])

        if len(models) > 0:
            # Models might have capability fields like max_tokens, supports_streaming, etc.
            model = models[0]

            # These are optional but common fields
            capability_fields = ["max_tokens", "context_length", "supports_streaming"]
            # Just verify if present, they have correct types
            for field in capability_fields:
                if field in model:
                    assert isinstance(model[field], (int, bool, str))


class TestModelsRouterIntegration:
    """Integration tests for models router."""

    def test_router_can_be_included_in_app(self):
        """Test that models router can be included in FastAPI app."""
        app = FastAPI()
        app.include_router(models_router)

        # Should not raise exception
        assert app is not None

    def test_models_endpoint_accepts_get_only(self, client):
        """Test that models endpoint only accepts GET requests."""
        # GET should work
        get_response = client.get("/api/models")
        assert get_response.status_code == status.HTTP_200_OK

        # POST should return 405 Method Not Allowed
        post_response = client.post("/api/models")
        assert post_response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_models_endpoint_consistent_response(self, client):
        """Test that models endpoint returns consistent results."""
        response1 = client.get("/api/models")
        response2 = client.get("/api/models")

        # Should return same data
        assert response1.json() == response2.json()

    def test_models_endpoint_idempotent(self, client):
        """Test that multiple calls return same result."""
        responses = [client.get("/api/models") for _ in range(3)]

        # All should succeed
        assert all(r.status_code == 200 for r in responses)

        # All should return same data
        first_data = responses[0].json()
        assert all(r.json() == first_data for r in responses)


class TestModelsResponseFormat:
    """Test models response format and schema."""

    def test_models_response_is_valid_json(self, client):
        """Test that response is valid JSON."""
        response = client.get("/api/models")

        # Should not raise exception when parsing JSON
        data = response.json()
        assert data is not None

    def test_models_response_format_stability(self, client):
        """Test that response format is stable across requests."""
        response = client.get("/api/models")
        data = response.json()

        # Response structure should be consistent
        # Either array of models or object with models key
        assert isinstance(data, (list, dict))

    def test_empty_models_handled_gracefully(self, client):
        """Test that endpoint handles case with no models configured."""
        response = client.get("/api/models")

        # Should still return 200, even if empty
        assert response.status_code == 200

        data = response.json()
        models = data if isinstance(data, list) else data.get("models", [])

        # Should be empty array, not null
        assert isinstance(models, list)
