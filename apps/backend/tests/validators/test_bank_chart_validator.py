"""
Tests for bank chart validators.
"""

import pytest
from pydantic import ValidationError

from src.validators.bank_chart import (
    ALLOWED_METRICS,
    BankChartDataValidator,
    validate_bank_chart_content,
)


@pytest.fixture
def valid_chart_data():
    """Valid bank chart data fixture."""
    return {
        "metric_name": "imor",
        "bank_names": ["INVEX", "BBVA", "Santander"],
        "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
        "data_as_of": "2024-12-01T00:00:00Z",
        "source": "CNBV",
        "plotly_config": {
            "data": [
                {
                    "x": ["2024-01", "2024-02"],
                    "y": [2.5, 2.3],
                    "type": "bar",
                    "name": "INVEX",
                }
            ],
            "layout": {"title": "IMOR"},
        },
        "metadata": {
            "sql_generated": "SELECT * FROM metrics WHERE metric = 'imor'",
            "metric_interpretation": "El IMOR representa...",
        },
    }


class TestBankChartDataValidator:
    """Tests for BankChartDataValidator."""

    def test_valid_chart_data(self, valid_chart_data):
        """Should validate correct chart data."""
        validator = BankChartDataValidator(**valid_chart_data)
        assert validator.metric_name == "imor"
        assert len(validator.bank_names) == 3
        assert validator.bank_names[0] == "INVEX"

    def test_metric_name_normalization(self, valid_chart_data):
        """Should normalize metric name to lowercase."""
        valid_chart_data["metric_name"] = "IMOR"
        validator = BankChartDataValidator(**valid_chart_data)
        assert validator.metric_name == "imor"

    def test_invalid_metric_name(self, valid_chart_data):
        """Should reject invalid metric names."""
        valid_chart_data["metric_name"] = "invalid_metric"
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "Invalid metric" in str(exc_info.value)

    def test_empty_metric_name(self, valid_chart_data):
        """Should reject empty metric name."""
        valid_chart_data["metric_name"] = ""
        with pytest.raises(ValidationError):
            BankChartDataValidator(**valid_chart_data)

    def test_empty_bank_names(self, valid_chart_data):
        """Should reject empty bank list."""
        valid_chart_data["bank_names"] = []
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "At least one bank is required" in str(exc_info.value)

    def test_too_many_banks(self, valid_chart_data):
        """Should reject more than 10 banks."""
        valid_chart_data["bank_names"] = [f"Bank{i}" for i in range(15)]
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "Maximum 10 banks allowed" in str(exc_info.value)

    def test_duplicate_bank_names(self, valid_chart_data):
        """Should reject duplicate bank names."""
        valid_chart_data["bank_names"] = ["INVEX", "BBVA", "invex"]  # Duplicate (case-insensitive)
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "Duplicate bank names" in str(exc_info.value)

    def test_empty_bank_name(self, valid_chart_data):
        """Should reject empty bank names."""
        valid_chart_data["bank_names"] = ["INVEX", "", "BBVA"]
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "Bank name cannot be empty" in str(exc_info.value)

    def test_missing_plotly_data(self, valid_chart_data):
        """Should reject plotly_config without data."""
        valid_chart_data["plotly_config"] = {"layout": {"title": "Test"}}
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "plotly_config.data is required" in str(exc_info.value)

    def test_empty_plotly_data(self, valid_chart_data):
        """Should reject empty plotly_config.data."""
        valid_chart_data["plotly_config"]["data"] = []
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "plotly_config.data cannot be empty" in str(exc_info.value)

    def test_missing_time_range_start(self, valid_chart_data):
        """Should reject time_range without start."""
        valid_chart_data["time_range"] = {"end": "2024-12-31"}
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "must have 'start' and 'end'" in str(exc_info.value)

    def test_sql_query_too_long(self, valid_chart_data):
        """Should reject SQL query exceeding max length."""
        valid_chart_data["metadata"]["sql_generated"] = "SELECT " + "x" * 10000
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "SQL query too long" in str(exc_info.value)

    def test_interpretation_too_long(self, valid_chart_data):
        """Should reject interpretation exceeding max length."""
        valid_chart_data["metadata"]["metric_interpretation"] = "x" * 15000
        with pytest.raises(ValidationError) as exc_info:
            BankChartDataValidator(**valid_chart_data)

        assert "Interpretation too long" in str(exc_info.value)

    def test_allowed_metrics_list(self):
        """Should have expected allowed metrics."""
        expected_metrics = {"imor", "cartera", "capitalizacion", "roe", "roa"}
        assert expected_metrics.issubset(ALLOWED_METRICS)

    def test_bank_name_trimming(self, valid_chart_data):
        """Should trim whitespace from bank names."""
        valid_chart_data["bank_names"] = ["  INVEX  ", " BBVA "]
        validator = BankChartDataValidator(**valid_chart_data)
        assert validator.bank_names == ["INVEX", "BBVA"]


class TestValidateBankChartContent:
    """Tests for validate_bank_chart_content helper function."""

    def test_validate_valid_content(self, valid_chart_data):
        """Should return validator for valid content."""
        result = validate_bank_chart_content(valid_chart_data)
        assert isinstance(result, BankChartDataValidator)
        assert result.metric_name == "imor"

    def test_validate_invalid_content(self, valid_chart_data):
        """Should raise ValueError for invalid content."""
        valid_chart_data["metric_name"] = "invalid"
        with pytest.raises(ValueError):
            validate_bank_chart_content(valid_chart_data)

    def test_validate_missing_required_field(self, valid_chart_data):
        """Should raise ValueError for missing required field."""
        del valid_chart_data["metric_name"]
        with pytest.raises(ValueError):
            validate_bank_chart_content(valid_chart_data)
