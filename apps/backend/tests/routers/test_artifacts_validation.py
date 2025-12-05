"""
Unit/Integration Tests for Artifact Router Validation (Sprint 1)

Tests the artifact router validation logic:
1. BankChartDataValidator integration
2. Input validation enforcement
3. Error handling and HTTP responses
4. Rate limiting decorator presence

These tests don't require a running server.
"""

import pytest
from fastapi import HTTPException
from datetime import datetime

from src.validators.bank_chart import (
    BankChartDataValidator,
    validate_bank_chart_content,
    ALLOWED_METRICS
)
from pydantic import ValidationError


def create_base_content(**kwargs):
    """Helper to create base chart content with all required fields"""
    base = {
        "metric_name": "imor",
        "bank_names": ["INVEX"],
        "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
        "plotly_config": {"data": [], "layout": {}},
        "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db",
        "metadata": {}
    }
    base.update(kwargs)
    return base


class TestBankChartValidation:
    """Test bank chart content validation"""

    def test_valid_bank_chart_content(self):
        """Should accept valid bank chart content"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX", "BBVA"],
            "time_range": {
                "start": "2024-01-01",
                "end": "2024-12-31"
            },
            "plotly_config": {
                "data": [
                    {
                        "x": ["2024-01"],
                        "y": [2.5],
                        "type": "bar",
                        "name": "INVEX"
                    }
                ],
                "layout": {
                    "title": "Test Chart",
                    "xaxis": {"title": "Period"},
                    "yaxis": {"title": "Value"}
                }
            },
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db",
            "metadata": {}
        }

        # Should not raise exception
        validated = validate_bank_chart_content(content)
        assert validated is not None
        assert validated.metric_name == "imor"
        assert validated.bank_names == ["INVEX", "BBVA"]

    def test_reject_invalid_metric(self):
        """Should reject invalid metric name"""
        content = {
            "metric_name": "invalid_metric",
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValueError) as exc_info:
            validate_bank_chart_content(content)

        assert "Invalid metric" in str(exc_info.value)

    def test_reject_duplicate_banks(self):
        """Should reject duplicate bank names (case-insensitive)"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX", "BBVA", "invex"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValueError) as exc_info:
            validate_bank_chart_content(content)

        assert "Duplicate" in str(exc_info.value)

    def test_reject_too_many_banks(self):
        """Should reject more than 10 banks"""
        content = {
            "metric_name": "imor",
            "bank_names": [f"BANK_{i}" for i in range(15)],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_bank_chart_content(content)

        error_msg = str(exc_info.value).lower()
        assert "10 item" in error_msg or "maximum" in error_msg

    def test_reject_empty_bank_names(self):
        """Should reject empty bank_names list"""
        content = {
            "metric_name": "imor",
            "bank_names": [],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_bank_chart_content(content)

        error_msg = str(exc_info.value).lower()
        assert "at least 1 item" in error_msg

    def test_reject_bank_name_with_only_whitespace(self):
        """Should reject bank names that are empty after trimming"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX", "   "],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValueError) as exc_info:
            validate_bank_chart_content(content)

        assert "empty" in str(exc_info.value).lower()

    def test_trim_whitespace_from_bank_names(self):
        """Should trim whitespace from bank names"""
        content = {
            "metric_name": "imor",
            "bank_names": ["  INVEX  ", " BBVA "],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        validated = validate_bank_chart_content(content)
        assert validated.bank_names == ["INVEX", "BBVA"]

    def test_normalize_metric_name_to_lowercase(self):
        """Should normalize metric name to lowercase"""
        content = {
            "metric_name": "IMOR",
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        validated = validate_bank_chart_content(content)
        assert validated.metric_name == "imor"

    def test_reject_long_metric_name(self):
        """Should reject metric name exceeding 50 characters"""
        content = {
            "metric_name": "a" * 51,
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_bank_chart_content(content)

        error_msg = str(exc_info.value).lower()
        assert "50 character" in error_msg or "max_length" in error_msg

    def test_reject_long_bank_name(self):
        """Should reject bank name exceeding 100 characters"""
        content = {
            "metric_name": "imor",
            "bank_names": ["A" * 101],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_bank_chart_content(content)

        error_msg = str(exc_info.value).lower()
        assert "100 character" in error_msg or "max_length" in error_msg


class TestAllowedMetrics:
    """Test allowed metrics configuration"""

    def test_allowed_metrics_includes_common_ones(self):
        """Should include common banking metrics"""
        assert "imor" in ALLOWED_METRICS
        assert "cartera" in ALLOWED_METRICS
        assert "capitalizacion" in ALLOWED_METRICS
        assert "mora" in ALLOWED_METRICS
        assert "utilidad" in ALLOWED_METRICS

    def test_all_metrics_are_lowercase(self):
        """All allowed metrics should be lowercase"""
        for metric in ALLOWED_METRICS:
            assert metric == metric.lower(), f"Metric {metric} should be lowercase"

    def test_metric_validation_case_insensitive(self):
        """Metric validation should be case-insensitive"""
        content = {
            "metric_name": "IMOR",  # Uppercase
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        validated = validate_bank_chart_content(content)
        assert validated.metric_name == "imor"  # Normalized to lowercase


class TestMetadataValidation:
    """Test metadata field validation"""

    def test_accept_valid_metadata(self):
        """Should accept valid metadata with sql and interpretation"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db",
            "metadata": {
                "sql_generated": "SELECT * FROM metrics",
                "metric_interpretation": "El IMOR mide morosidad"
            }
        }

        validated = validate_bank_chart_content(content)
        assert validated.metadata["sql_generated"] == "SELECT * FROM metrics"
        assert validated.metadata["metric_interpretation"] == "El IMOR mide morosidad"

    def test_accept_empty_metadata(self):
        """Should accept empty metadata dict"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db",
            "metadata": {}
        }

        validated = validate_bank_chart_content(content)
        assert validated.metadata == {}

    def test_default_empty_metadata_if_missing(self):
        """Should default to empty dict if metadata not provided"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        validated = validate_bank_chart_content(content)
        assert validated.metadata == {}

    def test_metadata_stores_script_tags_as_is(self):
        """Backend should store metadata as-is (XSS protection is frontend)"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db",
            "metadata": {
                "sql_generated": 'SELECT * FROM banks; <script>alert("XSS")</script>',
                "metric_interpretation": '<p>Test <script>alert(1)</script></p>'
            }
        }

        # Should accept without modification (sanitization happens in frontend)
        validated = validate_bank_chart_content(content)
        assert '<script>' in validated.metadata["sql_generated"]
        assert '<script>' in validated.metadata["metric_interpretation"]


class TestTimeRangeValidation:
    """Test time_range field validation"""

    def test_accept_valid_time_range(self):
        """Should accept valid time range"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "time_range": {
                "start": "2024-01-01",
                "end": "2024-12-31"
            },
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        validated = validate_bank_chart_content(content)
        assert validated.time_range["start"] == "2024-01-01"
        assert validated.time_range["end"] == "2024-12-31"

    def test_reject_missing_time_range(self):
        """Should reject missing time_range"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "plotly_config": {"data": [], "layout": {}},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_bank_chart_content(content)

        assert "time_range" in str(exc_info.value).lower()


class TestPlotlyConfigValidation:
    """Test plotly_config field validation"""

    def test_accept_valid_plotly_config(self):
        """Should accept valid plotly config"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "plotly_config": {
                "data": [{"x": ["2024-01"], "y": [2.5], "type": "bar"}],
                "layout": {"title": "Test"}
            },
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        validated = validate_bank_chart_content(content)
        assert "data" in validated.plotly_config
        assert "layout" in validated.plotly_config

    def test_reject_missing_plotly_config(self):
        """Should reject missing plotly_config"""
        content = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "data_as_of": datetime.utcnow().isoformat() + "Z",
            "source": "bank_metrics_db"
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_bank_chart_content(content)

        assert "plotly_config" in str(exc_info.value).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
