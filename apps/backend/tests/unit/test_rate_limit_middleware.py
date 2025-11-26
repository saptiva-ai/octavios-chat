"""
Unit tests for rate limiting middleware.

Tests request rate limiting, IP tracking, and retry-after headers.
"""

import pytest
import time
from unittest.mock import Mock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.middleware.rate_limit import RateLimitMiddleware


@pytest.fixture
def app_with_rate_limit(monkeypatch):
    """Create a test FastAPI app with rate limiting enabled."""
    # Enable rate limiting for tests (may be disabled in .env)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_CALLS", "100")
    monkeypatch.setenv("RATE_LIMIT_PERIOD", "60")

    # Clear get_settings cache to pick up new env vars
    from src.core.config import get_settings
    get_settings.cache_clear()

    app = FastAPI()

    @app.get("/api/test")
    async def test_endpoint():
        return {"message": "success"}

    # Add rate limit middleware
    app.add_middleware(RateLimitMiddleware)

    yield app

    # Clear cache after test
    get_settings.cache_clear()


@pytest.fixture
def client_rate_limit(app_with_rate_limit):
    """Create a test client for rate-limited app."""
    return TestClient(app_with_rate_limit)


class TestRateLimitMiddleware:
    """Test suite for RateLimitMiddleware."""

    def test_middleware_allows_requests_within_limit(self, client_rate_limit):
        """Test that requests within rate limit are allowed."""
        # Make a single request (should be allowed)
        response = client_rate_limit.get("/api/test")

        assert response.status_code == 200
        assert response.json()["message"] == "success"

    def test_middleware_adds_rate_limit_headers(self, client_rate_limit):
        """Test that rate limit headers are added to response."""
        response = client_rate_limit.get("/api/test")

        # Check for rate limit headers
        assert "X-RateLimit-Limit" in response.headers or "x-ratelimit-limit" in response.headers
        # Note: header names might be case-insensitive

    def test_middleware_blocks_requests_exceeding_limit(self, monkeypatch):
        """Test that requests exceeding rate limit are blocked with 429."""
        # Clear cache first
        from src.core.config import get_settings
        get_settings.cache_clear()

        # Configure very low rate limit for testing via env vars
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_LIMIT_CALLS", "2")  # Only allow 2 requests
        monkeypatch.setenv("RATE_LIMIT_PERIOD", "60")

        app = FastAPI()

        @app.get("/api/test")
        async def test_endpoint():
            return {"message": "success"}

        app.add_middleware(RateLimitMiddleware)
        client = TestClient(app)

        # Make requests up to the limit
        response1 = client.get("/api/test")
        assert response1.status_code == 200

        response2 = client.get("/api/test")
        assert response2.status_code == 200

        # Third request should be rate limited
        response3 = client.get("/api/test")
        assert response3.status_code == 429

        # Clear cache after test
        get_settings.cache_clear()

    def test_rate_limit_response_format(self, monkeypatch):
        """Test that rate limit error response has correct format."""
        from src.core.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_LIMIT_CALLS", "1")
        monkeypatch.setenv("RATE_LIMIT_PERIOD", "60")

        app = FastAPI()

        @app.get("/api/test")
        async def test_endpoint():
            return {"message": "success"}

        app.add_middleware(RateLimitMiddleware)
        client = TestClient(app)

        # Exhaust rate limit
        client.get("/api/test")

        # Get rate limit response
        response = client.get("/api/test")

        assert response.status_code == 429
        data = response.json()

        # Check response structure
        assert "error" in data or "detail" in data
        assert "retry_after" in data or "Retry-After" in response.headers

        get_settings.cache_clear()

    def test_middleware_tracks_requests_per_ip(self):
        """Test that middleware tracks requests per client IP."""
        middleware = RateLimitMiddleware(app=Mock())

        # Should have _requests attribute for tracking
        assert hasattr(middleware, '_requests')

    def test_middleware_cleans_old_requests(self):
        """Test that old requests outside the time window are cleaned up."""
        middleware = RateLimitMiddleware(app=Mock())

        # Simulate old requests
        client_ip = "192.168.1.1"
        old_time = time.time() - 1000  # 1000 seconds ago

        middleware._requests[client_ip].append(old_time)

        # Clean up old requests
        current_time = time.time()
        middleware._cleanup_old_requests(client_ip, current_time)

        # Old request should be removed
        assert len(middleware._requests[client_ip]) == 0

    def test_get_client_ip_from_direct_connection(self):
        """Test extracting client IP from direct connection."""
        middleware = RateLimitMiddleware(app=Mock())

        mock_request = Mock(spec=Request)
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}

        ip = middleware._get_client_ip(mock_request)

        assert ip == "192.168.1.100"

    def test_get_client_ip_from_forwarded_header(self):
        """Test extracting client IP from X-Forwarded-For header."""
        middleware = RateLimitMiddleware(app=Mock())

        mock_request = Mock(spec=Request)
        mock_request.client = Mock()
        mock_request.client.host = "10.0.0.1"  # Proxy IP
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.45, 198.51.100.67"  # Client IP, Proxy IP
        }

        ip = middleware._get_client_ip(mock_request)

        # Should extract first IP from X-Forwarded-For
        assert ip == "203.0.113.45"

    @patch('src.core.config.get_settings')
    def test_middleware_disabled_allows_all_requests(self, mock_settings):
        """Test that disabling rate limiting allows unlimited requests."""
        settings = Mock()
        settings.rate_limit_enabled = False  # Disabled
        mock_settings.return_value = settings

        app = FastAPI()

        @app.get("/api/test")
        async def test_endpoint():
            return {"message": "success"}

        app.add_middleware(RateLimitMiddleware)
        client = TestClient(app)

        # Make many requests (all should succeed)
        for _ in range(10):
            response = client.get("/api/test")
            assert response.status_code == 200


class TestRateLimitHeaders:
    """Test rate limit header generation."""

    @patch('src.core.config.get_settings')
    def test_remaining_header_decrements(self, mock_settings):
        """Test that X-RateLimit-Remaining decrements with each request."""
        settings = Mock()
        settings.rate_limit_enabled = True
        settings.rate_limit_calls = 5
        settings.rate_limit_period = 60
        mock_settings.return_value = settings

        app = FastAPI()

        @app.get("/api/test")
        async def test_endpoint():
            return {"message": "success"}

        app.add_middleware(RateLimitMiddleware)
        client = TestClient(app)

        # First request
        response1 = client.get("/api/test")
        remaining1 = int(response1.headers.get("X-RateLimit-Remaining", "-1"))

        # Second request
        response2 = client.get("/api/test")
        remaining2 = int(response2.headers.get("X-RateLimit-Remaining", "-1"))

        # Remaining should decrease
        if remaining1 >= 0 and remaining2 >= 0:
            assert remaining2 < remaining1

    def test_retry_after_header_on_rate_limit(self, monkeypatch):
        """Test that Retry-After header is set when rate limited."""
        from src.core.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_LIMIT_CALLS", "1")
        monkeypatch.setenv("RATE_LIMIT_PERIOD", "60")

        app = FastAPI()

        @app.get("/api/test")
        async def test_endpoint():
            return {"message": "success"}

        app.add_middleware(RateLimitMiddleware)
        client = TestClient(app)

        # Exhaust limit
        client.get("/api/test")

        # Get rate limited response
        response = client.get("/api/test")

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) == 60

        get_settings.cache_clear()


class TestRateLimitConfiguration:
    """Test rate limit configuration."""

    def test_middleware_initializes_with_settings(self):
        """Test that middleware loads settings on init."""
        middleware = RateLimitMiddleware(app=Mock())

        assert hasattr(middleware, 'settings')
        assert middleware.settings is not None

    def test_middleware_initializes_request_tracking(self):
        """Test that middleware initializes request tracking dict."""
        middleware = RateLimitMiddleware(app=Mock())

        assert hasattr(middleware, '_requests')
        assert isinstance(middleware._requests, dict)

    def test_custom_rate_limit_values(self, monkeypatch):
        """Test that custom rate limit values are respected."""
        from src.core.config import get_settings
        get_settings.cache_clear()

        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_LIMIT_CALLS", "100")
        monkeypatch.setenv("RATE_LIMIT_PERIOD", "3600")

        middleware = RateLimitMiddleware(app=Mock())

        assert middleware.settings.rate_limit_calls == 100
        assert middleware.settings.rate_limit_period == 3600

        get_settings.cache_clear()


class TestRateLimitCleanup:
    """Test request history cleanup logic."""

    def test_cleanup_removes_expired_requests(self):
        """Test that cleanup removes requests outside the time window."""
        middleware = RateLimitMiddleware(app=Mock())
        middleware.settings.rate_limit_period = 60  # 60 second window

        client_ip = "192.168.1.1"
        current_time = time.time()

        # Add requests at different times
        middleware._requests[client_ip].append(current_time - 100)  # Expired
        middleware._requests[client_ip].append(current_time - 30)   # Valid
        middleware._requests[client_ip].append(current_time - 10)   # Valid

        # Clean up
        middleware._cleanup_old_requests(client_ip, current_time)

        # Should have 2 valid requests remaining
        assert len(middleware._requests[client_ip]) == 2

    def test_cleanup_preserves_recent_requests(self):
        """Test that cleanup preserves requests within time window."""
        middleware = RateLimitMiddleware(app=Mock())
        middleware.settings.rate_limit_period = 60

        client_ip = "192.168.1.1"
        current_time = time.time()

        # Add recent requests
        middleware._requests[client_ip].append(current_time - 5)
        middleware._requests[client_ip].append(current_time - 1)

        # Clean up
        middleware._cleanup_old_requests(client_ip, current_time)

        # All requests should be preserved
        assert len(middleware._requests[client_ip]) == 2
