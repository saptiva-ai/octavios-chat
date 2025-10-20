"""
Unit tests for health schemas.

Tests Pydantic models for health check responses.
"""
import pytest
from datetime import datetime

from src.schemas.health import (
    HealthStatus,
    ServiceStatus,
    HealthCheckResponse,
    LivenessResponse,
    ReadinessResponse
)


@pytest.mark.unit
class TestHealthSchemas:
    """Test health check schema models"""

    def test_service_status_creation(self):
        """Test ServiceStatus model creation"""
        service = ServiceStatus(
            name="database",
            status=HealthStatus.HEALTHY,
            latency_ms=15.5,
            message="Connection successful"
        )

        assert service.name == "database"
        assert service.status == HealthStatus.HEALTHY
        assert service.latency_ms == 15.5
        assert service.message == "Connection successful"

    def test_service_status_optional_fields(self):
        """Test ServiceStatus with optional fields"""
        service = ServiceStatus(
            name="redis",
            status=HealthStatus.UNHEALTHY
        )

        assert service.name == "redis"
        assert service.status == HealthStatus.UNHEALTHY
        assert service.latency_ms is None
        assert service.message is None

    def test_health_check_response_healthy(self):
        """Test HealthCheckResponse for healthy system"""
        service = ServiceStatus(
            name="database",
            status=HealthStatus.HEALTHY,
            latency_ms=10.0
        )

        response = HealthCheckResponse(
            status=HealthStatus.HEALTHY,
            timestamp=datetime.utcnow(),
            version="1.0.0",
            uptime_seconds=3600.0,
            services=[service]
        )

        assert response.status == HealthStatus.HEALTHY
        assert isinstance(response.timestamp, datetime)
        assert response.version == "1.0.0"
        assert response.uptime_seconds == 3600.0
        assert len(response.services) == 1
        assert response.services[0].name == "database"

    def test_health_check_response_degraded(self):
        """Test HealthCheckResponse for degraded system"""
        db_service = ServiceStatus(
            name="database",
            status=HealthStatus.HEALTHY
        )
        redis_service = ServiceStatus(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            message="Connection timeout"
        )

        response = HealthCheckResponse(
            status=HealthStatus.DEGRADED,
            timestamp=datetime.utcnow(),
            version="1.0.0",
            uptime_seconds=100.0,
            services=[db_service, redis_service]
        )

        assert response.status == HealthStatus.DEGRADED
        assert len(response.services) == 2

    def test_liveness_response(self):
        """Test LivenessResponse model"""
        response = LivenessResponse(status="alive")
        assert response.status == "alive"

    def test_readiness_response(self):
        """Test ReadinessResponse model"""
        response = ReadinessResponse(status="ready")
        assert response.status == "ready"

    def test_health_status_enum_values(self):
        """Test HealthStatus enum has expected values"""
        assert hasattr(HealthStatus, 'HEALTHY')
        assert hasattr(HealthStatus, 'UNHEALTHY')
        assert hasattr(HealthStatus, 'DEGRADED')

    def test_service_status_json_serialization(self):
        """Test ServiceStatus can be serialized to JSON"""
        service = ServiceStatus(
            name="database",
            status=HealthStatus.HEALTHY,
            latency_ms=15.5,
            message="OK"
        )

        json_data = service.model_dump()
        assert json_data["name"] == "database"
        assert json_data["latency_ms"] == 15.5

    def test_health_check_response_json_serialization(self):
        """Test HealthCheckResponse can be serialized to JSON"""
        service = ServiceStatus(
            name="api",
            status=HealthStatus.HEALTHY
        )

        response = HealthCheckResponse(
            status=HealthStatus.HEALTHY,
            timestamp=datetime.utcnow(),
            version="1.0.0",
            uptime_seconds=100.0,
            services=[service]
        )

        json_data = response.model_dump()
        assert json_data["status"] == HealthStatus.HEALTHY
        assert "timestamp" in json_data
        assert json_data["version"] == "1.0.0"
        assert len(json_data["services"]) == 1
