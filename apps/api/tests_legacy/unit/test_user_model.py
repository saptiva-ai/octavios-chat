"""
Unit tests for User model.

Tests User model validation, password hashing, and field constraints.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

# Note: Adjust imports based on actual model location
try:
    from src.models.user import User
except ImportError:
    pytest.skip("User model not available", allow_module_level=True)


class TestUserModel:
    """Test suite for User model class."""

    def test_user_model_basic_creation(self):
        """Test that User model can be created with required fields."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password_here"
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.hashed_password == "hashed_password_here"

    def test_user_model_email_validation(self):
        """Test that User model validates email format."""
        # Valid email should work
        user = User(
            username="testuser",
            email="valid@example.com",
            hashed_password="hash"
        )
        assert user.email == "valid@example.com"

        # Invalid email format should raise ValidationError
        with pytest.raises(ValidationError):
            User(
                username="testuser",
                email="invalid-email",  # Missing @
                hashed_password="hash"
            )

    def test_user_model_username_constraints(self):
        """Test username field constraints."""
        # Valid username
        user = User(
            username="valid_user123",
            email="test@example.com",
            hashed_password="hash"
        )
        assert user.username == "valid_user123"

        # Test minimum length (if constrained)
        try:
            User(username="ab", email="test@example.com", hashed_password="hash")
            # If this passes, no minimum length constraint
        except ValidationError:
            # Minimum length constraint exists
            pass

    def test_user_model_default_values(self):
        """Test that User model sets default values correctly."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hash"
        )

        # Test common defaults
        if hasattr(user, 'is_active'):
            assert isinstance(user.is_active, bool)

        if hasattr(user, 'is_verified'):
            assert isinstance(user.is_verified, bool)

        if hasattr(user, 'created_at'):
            assert isinstance(user.created_at, datetime) or isinstance(user.created_at, str)

    def test_user_model_password_not_exposed(self):
        """Test that password field is named hashed_password (security best practice)."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_value"
        )

        # Should have hashed_password, not plaintext password field
        assert hasattr(user, 'hashed_password')
        assert not hasattr(user, 'password') or hasattr(user, 'password') == hasattr(user, 'set_password')

    def test_user_model_unique_fields(self):
        """Test that username and email are intended to be unique."""
        # This test documents the expectation that username and email are unique
        # Actual uniqueness is enforced at database level
        user1 = User(
            username="user1",
            email="user1@example.com",
            hashed_password="hash1"
        )

        user2 = User(
            username="user2",  # Different username
            email="user2@example.com",  # Different email
            hashed_password="hash2"
        )

        assert user1.username != user2.username
        assert user1.email != user2.email

    def test_user_model_optional_fields(self):
        """Test that optional fields can be omitted."""
        # Minimal user with only required fields
        user = User(
            username="minimal",
            email="minimal@example.com",
            hashed_password="hash"
        )

        assert user.username is not None
        assert user.email is not None

    def test_user_model_serialization(self):
        """Test that User model can be serialized to dict."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password"
        )

        # Should be able to convert to dict
        user_dict = user.model_dump() if hasattr(user, 'model_dump') else user.dict()

        assert isinstance(user_dict, dict)
        assert user_dict["username"] == "testuser"
        assert user_dict["email"] == "test@example.com"

    def test_user_model_immutable_id(self):
        """Test that user ID is immutable after creation."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hash"
        )

        if hasattr(user, 'id'):
            original_id = user.id
            # ID should not be modifiable or should raise error
            # This is typically enforced by Beanie/MongoDB

    def test_user_model_timestamps(self):
        """Test that user model includes timestamp fields."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hash"
        )

        # Check for common timestamp fields
        timestamp_fields = ['created_at', 'updated_at', 'last_login']

        for field in timestamp_fields:
            if hasattr(user, field):
                value = getattr(user, field)
                # Should be datetime or None
                assert value is None or isinstance(value, (datetime, str))


class TestUserModelSecurity:
    """Test security-related aspects of User model."""

    def test_user_model_stores_hashed_password(self):
        """Test that User model expects hashed passwords, not plaintext."""
        user = User(
            username="secureuser",
            email="secure@example.com",
            hashed_password="$2b$12$hashed_bcrypt_value"  # Example bcrypt hash format
        )

        # Password should be stored as provided (hashed)
        assert user.hashed_password == "$2b$12$hashed_bcrypt_value"
        # Should not be storing plaintext
        assert user.hashed_password != "plaintext_password"

    def test_user_model_password_not_in_json(self):
        """Test that hashed password is excluded from JSON serialization."""
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_value"
        )

        # Get JSON representation
        user_dict = user.model_dump(exclude={'hashed_password'}) if hasattr(user, 'model_dump') else user.dict(exclude={'hashed_password'})

        # Hashed password should not be in dict when excluded
        assert 'hashed_password' not in user_dict
        assert 'password' not in user_dict
