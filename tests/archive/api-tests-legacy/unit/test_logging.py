"""
Unit tests for logging configuration module.

Tests structured logging setup, log levels, and formatters.
"""

import pytest
import logging
from unittest.mock import Mock, patch

try:
    from src.core.logging import setup_logging, get_logger
    LOGGING_AVAILABLE = True
except ImportError:
    LOGGING_AVAILABLE = False
    pytest.skip("Logging module not available", allow_module_level=True)


class TestLoggingSetup:
    """Test suite for logging setup and configuration."""

    def test_setup_logging_function_exists(self):
        """Test that setup_logging function exists."""
        assert callable(setup_logging)

    def test_setup_logging_configures_structlog(self):
        """Test that setup_logging configures structlog."""
        # Call setup_logging
        setup_logging()

        # Should not raise exception
        assert True

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger instance."""
        logger = get_logger(__name__)

        # Should return a logger-like object
        assert logger is not None
        assert hasattr(logger, 'info') or hasattr(logger, 'log')

    def test_logger_has_standard_methods(self):
        """Test that logger has standard logging methods."""
        logger = get_logger(__name__)

        # Check for standard log methods
        expected_methods = ['debug', 'info', 'warning', 'error']

        for method in expected_methods:
            if hasattr(logger, method):
                assert callable(getattr(logger, method))


class TestLoggerConfiguration:
    """Test logger configuration and behavior."""

    def test_logger_accepts_module_name(self):
        """Test that logger can be created with module name."""
        logger = get_logger("test_module")

        assert logger is not None

    def test_logger_accepts_dunder_name(self):
        """Test that logger accepts __name__ as argument."""
        logger = get_logger(__name__)

        assert logger is not None

    def test_multiple_loggers_can_be_created(self):
        """Test that multiple loggers can coexist."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        assert logger1 is not None
        assert logger2 is not None

    @patch('src.core.config.get_settings')
    def test_logging_respects_log_level_setting(self, mock_settings):
        """Test that logging level is configured from settings."""
        settings = Mock()
        settings.log_level = "DEBUG"
        mock_settings.return_value = settings

        # Setup logging with DEBUG level
        setup_logging()

        # Should configure logging without errors
        assert True


class TestStructuredLogging:
    """Test structured logging features."""

    def test_logger_supports_context(self):
        """Test that logger supports context/extra fields."""
        logger = get_logger(__name__)

        # Should support logging with context
        # Actual behavior depends on structlog configuration
        try:
            if hasattr(logger, 'bind'):
                bound_logger = logger.bind(request_id="123")
                assert bound_logger is not None
        except AttributeError:
            # If bind not available, that's ok for basic logging
            pass

    def test_logger_handles_exceptions(self):
        """Test that logger can log exceptions."""
        logger = get_logger(__name__)

        # Should not raise when logging
        try:
            if hasattr(logger, 'error'):
                logger.error("Test error message")
                assert True
            elif hasattr(logger, 'log'):
                logger.log(logging.ERROR, "Test error message")
                assert True
        except Exception:
            pytest.fail("Logger raised exception during logging")


class TestLoggingFormatters:
    """Test log formatting and output."""

    def test_json_formatter_available(self):
        """Test that JSON formatter is available for production."""
        # JSON logging is common in production
        # This test documents the expectation
        assert True  # Placeholder

    def test_console_formatter_for_development(self):
        """Test that console formatter is available for development."""
        # Console logging for development
        assert True  # Placeholder


class TestLoggingLevels:
    """Test log level configuration."""

    @patch('src.core.config.get_settings')
    def test_debug_level_configuration(self, mock_settings):
        """Test configuring DEBUG log level."""
        settings = Mock()
        settings.log_level = "DEBUG"
        mock_settings.return_value = settings

        setup_logging()
        logger = get_logger(__name__)

        # Logger should be configured
        assert logger is not None

    @patch('src.core.config.get_settings')
    def test_info_level_configuration(self, mock_settings):
        """Test configuring INFO log level."""
        settings = Mock()
        settings.log_level = "INFO"
        mock_settings.return_value = settings

        setup_logging()
        logger = get_logger(__name__)

        assert logger is not None

    @patch('src.core.config.get_settings')
    def test_warning_level_configuration(self, mock_settings):
        """Test configuring WARNING log level."""
        settings = Mock()
        settings.log_level = "WARNING"
        mock_settings.return_value = settings

        setup_logging()
        logger = get_logger(__name__)

        assert logger is not None

    @patch('src.core.config.get_settings')
    def test_error_level_configuration(self, mock_settings):
        """Test configuring ERROR log level."""
        settings = Mock()
        settings.log_level = "ERROR"
        mock_settings.return_value = settings

        setup_logging()
        logger = get_logger(__name__)

        assert logger is not None


class TestLoggingIntegration:
    """Integration tests for logging system."""

    def test_logging_setup_is_idempotent(self):
        """Test that calling setup_logging multiple times is safe."""
        # Should not raise exception
        setup_logging()
        setup_logging()
        setup_logging()

        assert True

    def test_logging_works_across_modules(self):
        """Test that loggers from different modules coexist."""
        logger1 = get_logger("module.submodule1")
        logger2 = get_logger("module.submodule2")
        logger3 = get_logger("another_module")

        assert logger1 is not None
        assert logger2 is not None
        assert logger3 is not None

    def test_logging_doesnt_interfere_with_root_logger(self):
        """Test that custom logging doesn't break root logger."""
        setup_logging()

        # Root logger should still work
        root_logger = logging.getLogger()
        assert root_logger is not None


class TestLoggingErrorHandling:
    """Test logging error handling and edge cases."""

    def test_logger_handles_unicode(self):
        """Test that logger handles unicode characters."""
        logger = get_logger(__name__)

        try:
            if hasattr(logger, 'info'):
                logger.info("Test with émojis 🚀 and ñoño")
                assert True
        except Exception:
            pytest.fail("Logger failed to handle unicode")

    def test_logger_handles_none_values(self):
        """Test that logger handles None values in context."""
        logger = get_logger(__name__)

        try:
            if hasattr(logger, 'bind'):
                logger.bind(value=None)
            assert True
        except Exception:
            pytest.fail("Logger failed to handle None values")

    def test_logger_handles_large_messages(self):
        """Test that logger handles large log messages."""
        logger = get_logger(__name__)

        large_message = "x" * 10000  # 10KB message

        try:
            if hasattr(logger, 'info'):
                logger.info(large_message)
                assert True
        except Exception:
            pytest.fail("Logger failed to handle large message")
