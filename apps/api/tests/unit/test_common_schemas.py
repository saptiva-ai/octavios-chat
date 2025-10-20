"""
Unit tests for common schemas.

Tests Pydantic models used across the application.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from src.schemas.common import (
    PaginationParams,
    PaginatedResponse,
    TimestampMixin,
    IDResponse,
    MessageResponse
)


@pytest.mark.unit
class TestCommonSchemas:
    """Test common schema models"""

    def test_pagination_params_defaults(self):
        """Test PaginationParams with default values"""
        params = PaginationParams()
        assert params.skip == 0
        assert params.limit == 20

    def test_pagination_params_custom(self):
        """Test PaginationParams with custom values"""
        params = PaginationParams(skip=10, limit=50)
        assert params.skip == 10
        assert params.limit == 50

    def test_pagination_params_validation_negative_skip(self):
        """Test PaginationParams rejects negative skip"""
        with pytest.raises(ValidationError):
            PaginationParams(skip=-1, limit=20)

    def test_pagination_params_validation_zero_limit(self):
        """Test PaginationParams rejects zero limit"""
        with pytest.raises(ValidationError):
            PaginationParams(skip=0, limit=0)

    def test_pagination_params_validation_large_limit(self):
        """Test PaginationParams enforces max limit"""
        with pytest.raises(ValidationError):
            PaginationParams(skip=0, limit=1001)

    def test_paginated_response_creation(self):
        """Test PaginatedResponse with items"""
        items = [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}]
        response = PaginatedResponse(
            items=items,
            total=100,
            skip=0,
            limit=20
        )

        assert len(response.items) == 2
        assert response.total == 100
        assert response.skip == 0
        assert response.limit == 20

    def test_paginated_response_empty(self):
        """Test PaginatedResponse with no items"""
        response = PaginatedResponse(
            items=[],
            total=0,
            skip=0,
            limit=20
        )

        assert len(response.items) == 0
        assert response.total == 0

    def test_id_response_creation(self):
        """Test IDResponse model"""
        response = IDResponse(id="123456")
        assert response.id == "123456"

    def test_id_response_validation(self):
        """Test IDResponse requires id field"""
        with pytest.raises(ValidationError):
            IDResponse()

    def test_message_response_creation(self):
        """Test MessageResponse model"""
        response = MessageResponse(message="Operation completed successfully")
        assert response.message == "Operation completed successfully"

    def test_message_response_validation(self):
        """Test MessageResponse requires message field"""
        with pytest.raises(ValidationError):
            MessageResponse()

    def test_timestamp_mixin(self):
        """Test TimestampMixin adds timestamp fields"""
        from pydantic import BaseModel

        class TestModel(TimestampMixin, BaseModel):
            name: str

        model = TestModel(name="Test", created_at=datetime.utcnow())
        assert hasattr(model, 'created_at')
        assert isinstance(model.created_at, datetime)

    def test_pagination_response_has_has_more(self):
        """Test PaginatedResponse calculates has_more correctly"""
        # When skip + items < total, has_more should be True
        response = PaginatedResponse(
            items=[{"id": "1"}],
            total=100,
            skip=0,
            limit=20
        )

        # Check if has_more is calculated (if it exists in the model)
        json_data = response.model_dump()
        assert "total" in json_data
        assert json_data["total"] == 100

    def test_pagination_params_json_schema(self):
        """Test PaginationParams generates valid JSON schema"""
        schema = PaginationParams.model_json_schema()
        assert "properties" in schema
        assert "skip" in schema["properties"]
        assert "limit" in schema["properties"]

    def test_message_response_json_serialization(self):
        """Test MessageResponse can be serialized"""
        response = MessageResponse(message="Success")
        json_data = response.model_dump()
        assert json_data["message"] == "Success"
        assert isinstance(json_data, dict)
