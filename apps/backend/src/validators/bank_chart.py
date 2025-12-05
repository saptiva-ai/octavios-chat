"""
Bank Chart Validation - Input validation for BankChartData artifacts.

Prevents invalid or malicious data from being persisted.
"""

from typing import Any, Dict, List, Set
from pydantic import BaseModel, Field, field_validator

# Allowed metric names (lowercase)
ALLOWED_METRICS: Set[str] = {
    "imor",
    "cartera",
    "capitalizacion",
    "mora",
    "utilidad",
    "activos",
    "pasivos",
    "roe",
    "roa",
    "morosidad",
    "provisiones",
    "credito",
    "captacion",
}

# Known bank identifiers (can be expanded)
KNOWN_BANKS: Set[str] = {
    "INVEX",
    "BBVA",
    "Santander",
    "HSBC",
    "Banamex",
    "Banorte",
    "Scotiabank",
    "Inbursa",
    "Azteca",
    "Sistema",  # Aggregate for all banks
}

# Maximum allowed values
MAX_BANKS = 10
MAX_METRIC_NAME_LENGTH = 50
MAX_BANK_NAME_LENGTH = 100
MAX_SQL_LENGTH = 5000
MAX_INTERPRETATION_LENGTH = 10000


class BankChartDataValidator(BaseModel):
    """
    Validated request for creating bank_chart artifacts.

    Enforces:
    - Metric name whitelist
    - Bank count limits
    - String length constraints
    - Required fields presence
    """

    metric_name: str = Field(
        ...,
        description="Metric identifier (e.g., 'imor', 'cartera')",
        min_length=1,
        max_length=MAX_METRIC_NAME_LENGTH,
    )
    bank_names: List[str] = Field(
        ...,
        description="List of bank identifiers",
        min_length=1,
        max_length=MAX_BANKS,
    )
    time_range: Dict[str, str] = Field(
        ..., description="Date range with 'start' and 'end' keys"
    )
    data_as_of: str = Field(..., description="Data snapshot timestamp")
    source: str = Field(..., description="Data source identifier")
    plotly_config: Dict[str, Any] = Field(..., description="Plotly chart configuration")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")

    @field_validator("metric_name")
    @classmethod
    def validate_metric_name(cls, v: str) -> str:
        """Validate metric name is in allowed list."""
        normalized = v.lower().strip()

        if not normalized:
            raise ValueError("Metric name cannot be empty")

        if normalized not in ALLOWED_METRICS:
            raise ValueError(
                f"Invalid metric '{v}'. Allowed metrics: {sorted(ALLOWED_METRICS)}"
            )

        return normalized

    @field_validator("bank_names")
    @classmethod
    def validate_bank_names(cls, v: List[str]) -> List[str]:
        """Validate bank names and count."""
        if not v:
            raise ValueError("At least one bank is required")

        if len(v) > MAX_BANKS:
            raise ValueError(f"Maximum {MAX_BANKS} banks allowed, got {len(v)}")

        # Validate each bank name
        validated_banks = []
        for bank in v:
            if not isinstance(bank, str):
                raise ValueError(f"Bank name must be string, got {type(bank)}")

            if not bank.strip():
                raise ValueError("Bank name cannot be empty")

            if len(bank) > MAX_BANK_NAME_LENGTH:
                raise ValueError(
                    f"Bank name too long (max {MAX_BANK_NAME_LENGTH} chars): {bank[:50]}..."
                )

            # Warn about unknown banks (but don't reject)
            # This allows for new banks without code updates
            normalized = bank.strip()
            validated_banks.append(normalized)

        # Remove duplicates while preserving order
        seen = set()
        unique_banks = []
        for bank in validated_banks:
            if bank.lower() not in seen:
                seen.add(bank.lower())
                unique_banks.append(bank)

        if len(unique_banks) != len(validated_banks):
            raise ValueError("Duplicate bank names detected")

        return unique_banks

    @field_validator("plotly_config")
    @classmethod
    def validate_plotly_config(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate plotly configuration has required structure."""
        if not isinstance(v, dict):
            raise ValueError("plotly_config must be a dictionary")

        if "data" not in v:
            raise ValueError("plotly_config.data is required")

        if not isinstance(v["data"], list):
            raise ValueError("plotly_config.data must be a list")

        if len(v["data"]) == 0:
            raise ValueError("plotly_config.data cannot be empty")

        if "layout" not in v:
            raise ValueError("plotly_config.layout is required")

        return v

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Validate time_range has start and end dates."""
        if not isinstance(v, dict):
            raise ValueError("time_range must be a dictionary")

        if "start" not in v or "end" not in v:
            raise ValueError("time_range must have 'start' and 'end' keys")

        # Basic date format validation (ISO format expected)
        for key in ["start", "end"]:
            if not isinstance(v[key], str):
                raise ValueError(f"time_range.{key} must be a string")

            if not v[key].strip():
                raise ValueError(f"time_range.{key} cannot be empty")

        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate metadata size constraints."""
        if not isinstance(v, dict):
            return {}

        # Validate SQL query length
        sql = v.get("sql_generated")
        if sql and isinstance(sql, str) and len(sql) > MAX_SQL_LENGTH:
            raise ValueError(
                f"SQL query too long (max {MAX_SQL_LENGTH} chars), got {len(sql)}"
            )

        # Validate interpretation length
        interpretation = v.get("metric_interpretation")
        if (
            interpretation
            and isinstance(interpretation, str)
            and len(interpretation) > MAX_INTERPRETATION_LENGTH
        ):
            raise ValueError(
                f"Interpretation too long (max {MAX_INTERPRETATION_LENGTH} chars), got {len(interpretation)}"
            )

        return v


def validate_bank_chart_content(content: Dict[str, Any]) -> BankChartDataValidator:
    """
    Validate bank chart content before artifact creation.

    Args:
        content: Raw chart data dictionary

    Returns:
        Validated BankChartDataValidator instance

    Raises:
        ValueError: If validation fails

    Example:
        >>> try:
        ...     validator = validate_bank_chart_content(chart_data)
        ...     # Proceed with artifact creation
        ... except ValueError as e:
        ...     return HTTPException(400, detail=str(e))
    """
    return BankChartDataValidator(**content)
