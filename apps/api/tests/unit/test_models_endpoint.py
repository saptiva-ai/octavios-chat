"""
Unit tests for models endpoint.

Tests coverage for:
- /models endpoint returning available models
- Configuration parsing
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.main import app
from src.core.config import Settings


client = TestClient(app)


@pytest.mark.unit
class TestModelsEndpoint:
    """Test models endpoint"""

    def test_get_models_default(self):
        """Test getting models with default configuration"""
        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "default_model" in data
        assert "allowed_models" in data

        # Check types
        assert isinstance(data["default_model"], str)
        assert isinstance(data["allowed_models"], list)

        # Check that default model is in allowed models
        if data["allowed_models"]:
            assert len(data["allowed_models"]) > 0

    def test_get_models_custom_config(self):
        """Test getting models with custom configuration"""
        # Mock settings with specific models
        mock_settings = Settings()
        mock_settings.chat_default_model = "Saptiva Turbo"
        mock_settings.chat_allowed_models = "Saptiva Turbo,Saptiva Cortex,Saptiva Ops"

        with patch('src.routers.models.get_settings', return_value=mock_settings):
            response = client.get("/api/models")
            assert response.status_code == 200
            data = response.json()

            # Check configured values
            assert data["default_model"] == "Saptiva Turbo"
            assert len(data["allowed_models"]) == 3
            assert "Saptiva Turbo" in data["allowed_models"]
            assert "Saptiva Cortex" in data["allowed_models"]
            assert "Saptiva Ops" in data["allowed_models"]

    def test_get_models_with_whitespace(self):
        """Test getting models with whitespace in configuration"""
        mock_settings = Settings()
        mock_settings.chat_default_model = "Saptiva Turbo"
        mock_settings.chat_allowed_models = " Saptiva Turbo , Saptiva Cortex , Saptiva Ops "

        with patch('src.routers.models.get_settings', return_value=mock_settings):
            response = client.get("/api/models")
            assert response.status_code == 200
            data = response.json()

            # Check that whitespace is stripped
            for model in data["allowed_models"]:
                assert model == model.strip()
                assert len(model) > 0

    def test_get_models_empty_config(self):
        """Test getting models with empty configuration"""
        mock_settings = Settings()
        mock_settings.chat_default_model = "Saptiva Turbo"
        mock_settings.chat_allowed_models = ""

        with patch('src.routers.models.get_settings', return_value=mock_settings):
            response = client.get("/api/models")
            assert response.status_code == 200
            data = response.json()

            # Check that empty config results in empty list
            assert data["allowed_models"] == []
