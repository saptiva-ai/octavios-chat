"""
Unit tests for core exception handlers and custom exceptions.

Tests exception classes, handlers, and error response formatting.
"""

import pytest
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    ConflictError,
    DatabaseError,
    NotFoundError,
    api_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


class TestCustomExceptions:
    """Test suite for custom exception classes."""

    def test_api_error_base_exception(self):
        """Test APIError base exception."""
        error = APIError(message="Test error", status_code=500)
        assert error.message == "Test error"
        assert error.status_code == 500
        assert error.error_code is None

    def test_database_error(self):
        """Test DatabaseError exception."""
        error = DatabaseError(message="Database connection failed")
        assert error.message == "Database connection failed"
        assert error.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "database" in error.error_code.lower()

    def test_bad_request_error(self):
        """Test BadRequestError exception."""
        error = BadRequestError(message="Invalid input")
        assert error.message == "Invalid input"
        assert error.status_code == status.HTTP_400_BAD_REQUEST

    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        error = AuthenticationError(message="Invalid credentials")
        assert error.message == "Invalid credentials"
        assert error.status_code == status.HTTP_401_UNAUTHORIZED

    def test_authorization_error(self):
        """Test AuthorizationError exception."""
        error = AuthorizationError(message="Access denied")
        assert error.message == "Access denied"
        assert error.status_code == status.HTTP_403_FORBIDDEN

    def test_not_found_error(self):
        """Test NotFoundError exception."""
        error = NotFoundError(message="Resource not found")
        assert error.message == "Resource not found"
        assert error.status_code == status.HTTP_404_NOT_FOUND

    def test_conflict_error(self):
        """Test ConflictError exception."""
        error = ConflictError(message="Resource already exists")
        assert error.message == "Resource already exists"
        assert error.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
class TestExceptionHandlers:
    """Test suite for exception handler functions."""

    async def test_api_exception_handler(self):
        """Test API exception handler response format."""
        # Create a mock request
        request = Request(scope={"type": "http", "method": "GET", "path": "/test"})

        # Create an API error
        error = NotFoundError(message="User not found", error_code="USER_NOT_FOUND")

        # Call the handler
        response = await api_exception_handler(request, error)

        # Verify response
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.headers["content-type"] == "application/json"

    async def test_http_exception_handler(self):
        """Test HTTP exception handler response format."""
        request = Request(scope={"type": "http", "method": "GET", "path": "/test"})

        # Create an HTTP exception
        error = StarletteHTTPException(status_code=404, detail="Not found")

        # Call the handler
        response = await http_exception_handler(request, error)

        # Verify response
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_general_exception_handler(self):
        """Test general exception handler for unexpected errors."""
        request = Request(scope={"type": "http", "method": "GET", "path": "/test"})

        # Create a generic exception
        error = ValueError("Unexpected error")

        # Call the handler
        response = await general_exception_handler(request, error)

        # Verify response returns 500 for unexpected errors
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    async def test_validation_exception_handler(self):
        """Test validation exception handler for Pydantic validation errors."""
        request = Request(scope={"type": "http", "method": "POST", "path": "/test"})

        # Create a validation error
        class TestModel(BaseModel):
            name: str = Field(..., min_length=3)
            age: int = Field(..., ge=0)

        try:
            # This should raise a validation error
            TestModel(name="ab", age=-1)
        except ValidationError as ve:
            # Call the handler
            response = await validation_exception_handler(request, ve)

            # Verify response
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestExceptionInheritance:
    """Test exception inheritance and error code propagation."""

    def test_all_custom_exceptions_inherit_from_api_error(self):
        """Verify all custom exceptions inherit from APIError."""
        exceptions = [
            DatabaseError,
            BadRequestError,
            AuthenticationError,
            AuthorizationError,
            NotFoundError,
            ConflictError,
        ]

        for exc_class in exceptions:
            error = exc_class(message="Test")
            assert isinstance(error, APIError)
            assert isinstance(error, Exception)

    def test_exception_with_custom_error_code(self):
        """Test that error codes can be customized."""
        error = NotFoundError(
            message="User not found",
            error_code="CUSTOM_USER_NOT_FOUND"
        )
        assert error.error_code == "CUSTOM_USER_NOT_FOUND"

    def test_exception_str_representation(self):
        """Test string representation of exceptions."""
        error = BadRequestError(message="Invalid email format")
        error_str = str(error)
        assert "Invalid email format" in error_str
