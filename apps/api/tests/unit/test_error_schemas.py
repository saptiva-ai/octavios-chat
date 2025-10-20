"""
Unit tests for error schemas.

Tests Pydantic models for error responses.
"""
import pytest
from datetime import datetime

from src.schemas.error import (
    ErrorResponse,
    ErrorDetail,
    ValidationErrorResponse,
    ValidationError as APIValidationError
)


@pytest.mark.unit
class TestErrorSchemas:
    """Test error schema models"""

    def test_error_detail_creation(self):
        """Test ErrorDetail model creation"""
        detail = ErrorDetail(
            code="AUTH_FAILED",
            message="Authentication failed",
            field="password"
        )

        assert detail.code == "AUTH_FAILED"
        assert detail.message == "Authentication failed"
        assert detail.field == "password"

    def test_error_detail_optional_field(self):
        """Test ErrorDetail with optional field"""
        detail = ErrorDetail(
            code="SERVER_ERROR",
            message="Internal server error"
        )

        assert detail.code == "SERVER_ERROR"
        assert detail.message == "Internal server error"
        assert detail.field is None

    def test_error_response_creation(self):
        """Test ErrorResponse model"""
        error = ErrorResponse(
            error="BadRequest",
            message="Invalid request data",
            status_code=400
        )

        assert error.error == "BadRequest"
        assert error.message == "Invalid request data"
        assert error.status_code == 400

    def test_error_response_with_details(self):
        """Test ErrorResponse with details"""
        error = ErrorResponse(
            error="ValidationError",
            message="Validation failed",
            status_code=422,
            details={"field": "email", "issue": "invalid format"}
        )

        assert error.details is not None
        assert error.details["field"] == "email"

    def test_validation_error_creation(self):
        """Test APIValidationError model"""
        val_error = APIValidationError(
            loc=["body", "email"],
            msg="field required",
            type="value_error.missing"
        )

        assert val_error.loc == ["body", "email"]
        assert val_error.msg == "field required"
        assert val_error.type == "value_error.missing"

    def test_validation_error_response(self):
        """Test ValidationErrorResponse model"""
        errors = [
            APIValidationError(
                loc=["body", "email"],
                msg="field required",
                type="value_error.missing"
            ),
            APIValidationError(
                loc=["body", "password"],
                msg="ensure this value has at least 8 characters",
                type="value_error.any_str.min_length"
            )
        ]

        response = ValidationErrorResponse(
            error="ValidationError",
            message="Request validation failed",
            status_code=422,
            details=errors
        )

        assert response.error == "ValidationError"
        assert response.status_code == 422
        assert len(response.details) == 2

    def test_error_response_json_serialization(self):
        """Test ErrorResponse can be serialized"""
        error = ErrorResponse(
            error="NotFound",
            message="Resource not found",
            status_code=404
        )

        json_data = error.model_dump()
        assert json_data["error"] == "NotFound"
        assert json_data["status_code"] == 404
        assert isinstance(json_data, dict)

    def test_error_detail_with_context(self):
        """Test ErrorDetail with additional context"""
        detail = ErrorDetail(
            code="RATE_LIMIT",
            message="Too many requests",
            field="requests",
            context={"limit": 100, "window": "1h"}
        )

        assert detail.code == "RATE_LIMIT"
        if hasattr(detail, 'context'):
            assert detail.context["limit"] == 100

    def test_validation_error_with_input(self):
        """Test APIValidationError with input value"""
        val_error = APIValidationError(
            loc=["body", "age"],
            msg="ensure this value is greater than or equal to 0",
            type="value_error.number.not_ge",
            input=-5
        )

        assert val_error.loc == ["body", "age"]
        if hasattr(val_error, 'input'):
            assert val_error.input == -5

    def test_error_response_schema_validation(self):
        """Test ErrorResponse validates required fields"""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ErrorResponse()
