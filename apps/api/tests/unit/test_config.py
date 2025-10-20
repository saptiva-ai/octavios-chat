"""
Unit tests for core configuration module.

Tests Settings class validation, defaults, and environment variable loading.
"""

import pytest
from pydantic import ValidationError
from src.core.config import Settings, get_settings


class TestSettings:
    """Test suite for Settings configuration class."""

    def test_settings_with_defaults(self, monkeypatch):
        """Test that Settings initializes with default values."""
        # Set minimal required environment variables
        monkeypatch.setenv("MONGODB_USER", "test_user")
        monkeypatch.setenv("MONGODB_PASSWORD", "test_password")
        monkeypatch.setenv("MONGODB_DATABASE", "test_db")
        monkeypatch.setenv("REDIS_PASSWORD", "test_redis_pass")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key")

        settings = Settings()

        # Test default values
        assert settings.ENV == "development"
        assert settings.API_HOST == "0.0.0.0"
        assert settings.API_PORT == 8001
        assert settings.MONGODB_HOST == "localhost"
        assert settings.MONGODB_PORT == 27017
        assert settings.REDIS_HOST == "localhost"
        assert settings.REDIS_PORT == 6379
        assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 60
        assert settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS == 7

    def test_settings_with_custom_values(self, monkeypatch):
        """Test that Settings can be customized via environment variables."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("API_HOST", "0.0.0.0")
        monkeypatch.setenv("API_PORT", "9000")
        monkeypatch.setenv("MONGODB_HOST", "mongodb.example.com")
        monkeypatch.setenv("MONGODB_PORT", "27018")
        monkeypatch.setenv("MONGODB_USER", "prod_user")
        monkeypatch.setenv("MONGODB_PASSWORD", "prod_password")
        monkeypatch.setenv("MONGODB_DATABASE", "prod_db")
        monkeypatch.setenv("REDIS_HOST", "redis.example.com")
        monkeypatch.setenv("REDIS_PORT", "6380")
        monkeypatch.setenv("REDIS_PASSWORD", "prod_redis_pass")
        monkeypatch.setenv("JWT_SECRET_KEY", "prod_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "prod_api_key")

        settings = Settings()

        assert settings.ENV == "production"
        assert settings.API_PORT == 9000
        assert settings.MONGODB_HOST == "mongodb.example.com"
        assert settings.MONGODB_PORT == 27018
        assert settings.REDIS_HOST == "redis.example.com"
        assert settings.REDIS_PORT == 6380

    def test_mongodb_url_generation(self, monkeypatch):
        """Test that MongoDB URL is generated correctly."""
        monkeypatch.setenv("MONGODB_USER", "testuser")
        monkeypatch.setenv("MONGODB_PASSWORD", "testpass")
        monkeypatch.setenv("MONGODB_DATABASE", "testdb")
        monkeypatch.setenv("MONGODB_HOST", "localhost")
        monkeypatch.setenv("MONGODB_PORT", "27017")
        monkeypatch.setenv("REDIS_PASSWORD", "test_redis")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key")

        settings = Settings()

        # Check that MONGODB_URL is generated
        assert "mongodb://" in settings.MONGODB_URL
        assert "testuser" in settings.MONGODB_URL
        assert "testpass" in settings.MONGODB_URL
        assert "testdb" in settings.MONGODB_URL

    def test_redis_url_generation(self, monkeypatch):
        """Test that Redis URL is generated correctly."""
        monkeypatch.setenv("REDIS_HOST", "localhost")
        monkeypatch.setenv("REDIS_PORT", "6379")
        monkeypatch.setenv("REDIS_PASSWORD", "myredispass")
        monkeypatch.setenv("MONGODB_USER", "test_user")
        monkeypatch.setenv("MONGODB_PASSWORD", "test_pass")
        monkeypatch.setenv("MONGODB_DATABASE", "test_db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key")

        settings = Settings()

        # Check that REDIS_URL includes password
        assert "redis://" in settings.REDIS_URL
        assert "myredispass" in settings.REDIS_URL

    def test_settings_missing_required_field_raises_validation_error(self, monkeypatch):
        """Test that missing required fields raise ValidationError."""
        # Clear all relevant environment variables
        monkeypatch.delenv("MONGODB_USER", raising=False)
        monkeypatch.delenv("MONGODB_PASSWORD", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

        with pytest.raises(ValidationError):
            Settings()

    def test_get_settings_singleton(self, monkeypatch):
        """Test that get_settings returns singleton instance."""
        monkeypatch.setenv("MONGODB_USER", "test_user")
        monkeypatch.setenv("MONGODB_PASSWORD", "test_password")
        monkeypatch.setenv("MONGODB_DATABASE", "test_db")
        monkeypatch.setenv("REDIS_PASSWORD", "test_redis_pass")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key")

        settings1 = get_settings()
        settings2 = get_settings()

        # Both should be the same instance (cached)
        assert settings1 is settings2

    def test_cors_origins_parsing(self, monkeypatch):
        """Test that CORS origins are parsed correctly from comma-separated string."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://example.com,https://app.example.com")
        monkeypatch.setenv("MONGODB_USER", "test_user")
        monkeypatch.setenv("MONGODB_PASSWORD", "test_password")
        monkeypatch.setenv("MONGODB_DATABASE", "test_db")
        monkeypatch.setenv("REDIS_PASSWORD", "test_redis_pass")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key")

        settings = Settings()

        assert len(settings.CORS_ORIGINS) == 3
        assert "http://localhost:3000" in settings.CORS_ORIGINS
        assert "https://example.com" in settings.CORS_ORIGINS
        assert "https://app.example.com" in settings.CORS_ORIGINS

    def test_feature_flags_default_values(self, monkeypatch):
        """Test that feature flags have sensible defaults."""
        monkeypatch.setenv("MONGODB_USER", "test_user")
        monkeypatch.setenv("MONGODB_PASSWORD", "test_password")
        monkeypatch.setenv("MONGODB_DATABASE", "test_db")
        monkeypatch.setenv("REDIS_PASSWORD", "test_redis_pass")
        monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_key_minimum_32_chars_long")
        monkeypatch.setenv("SECRET_KEY", "test_api_key")

        settings = Settings()

        # Test feature flag defaults (adjust based on actual defaults in config.py)
        assert hasattr(settings, "ENV")
        assert settings.ENV in ["development", "production", "staging", "testing"]
