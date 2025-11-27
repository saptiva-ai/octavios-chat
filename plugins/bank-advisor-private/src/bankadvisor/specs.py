"""
Query Specification Models for NL2SQL Pipeline

This module defines the structured representation of banking queries
parsed from natural language input.

Architecture:
    NL Query → QuerySpec → RAG Context → SQL → Execution

Design Principles:
    1. Explicit typing for all parameters
    2. Support for common time expressions ("últimos 3 meses", "2024")
    3. Bank normalization (INVEX, SISTEMA)
    4. Clarification mechanism for incomplete queries
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date


class TimeRangeSpec(BaseModel):
    """
    Structured representation of time range expressions.

    Supported types:
        - last_n_months: "últimos 3 meses" → n=3
        - last_n_quarters: "último trimestre" → n=1
        - year: "2024" → start_date="2024-01-01", end_date="2024-12-31"
        - between_dates: "desde 2023-06-01 hasta 2024-01-01"
        - all: No time filter (entire history)

    Examples:
        TimeRangeSpec(type="last_n_months", n=3)
        TimeRangeSpec(type="year", start_date="2024-01-01", end_date="2024-12-31")
        TimeRangeSpec(type="between_dates", start_date="2023-01-01", end_date="2023-12-31")
    """

    type: Literal["last_n_months", "last_n_quarters", "year", "between_dates", "all"]
    n: Optional[int] = Field(None, description="Number of months/quarters for last_n_* types")
    start_date: Optional[str] = Field(None, description="ISO date YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="ISO date YYYY-MM-DD")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_iso_date(cls, v: Optional[str]) -> Optional[str]:
        """Validate ISO date format."""
        if v is None:
            return None
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid ISO date format: {v}. Expected YYYY-MM-DD")

    @field_validator("n")
    @classmethod
    def validate_n_positive(cls, v: Optional[int]) -> Optional[int]:
        """Validate n is positive."""
        if v is not None and v <= 0:
            raise ValueError(f"n must be positive, got {v}")
        return v


class QuerySpec(BaseModel):
    """
    Structured representation of a banking analytics query.

    This is the central data structure for the NL2SQL pipeline.
    It captures all dimensions of a user's query in a machine-readable format.

    Attributes:
        metric: Canonical metric name (e.g., "IMOR", "CARTERA_COMERCIAL")
        bank_names: List of normalized bank names (["INVEX"], ["SISTEMA"], or [] for all)
        time_range: Structured time range specification
        granularity: Temporal aggregation level
        visualization_type: Preferred chart type
        comparison_mode: True if comparing multiple banks
        requires_clarification: True if query is incomplete/ambiguous
        missing_fields: Fields that need clarification
        confidence_score: Parser confidence [0.0, 1.0]

    Examples:
        # Simple query: "IMOR de INVEX últimos 3 meses"
        QuerySpec(
            metric="IMOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="last_n_months", n=3),
            granularity="month",
            visualization_type="line"
        )

        # Comparison query: "Compara cartera comercial INVEX vs Sistema en 2024"
        QuerySpec(
            metric="CARTERA_COMERCIAL",
            bank_names=["INVEX", "SISTEMA"],
            time_range=TimeRangeSpec(type="year", start_date="2024-01-01", end_date="2024-12-31"),
            comparison_mode=True
        )

        # Ambiguous query: "cartera" (requires clarification)
        QuerySpec(
            metric="",
            bank_names=[],
            time_range=TimeRangeSpec(type="all"),
            requires_clarification=True,
            missing_fields=["metric", "time_range"],
            confidence_score=0.3
        )
    """

    metric: str = Field(..., description="Canonical metric name (e.g., IMOR, CARTERA_COMERCIAL)")
    bank_names: List[str] = Field(default_factory=list, description="Normalized bank names (INVEX, SISTEMA)")
    time_range: TimeRangeSpec
    granularity: Literal["month", "quarter", "year"] = "month"
    visualization_type: Literal["line", "bar", "table"] = "line"
    comparison_mode: bool = False
    requires_clarification: bool = False
    missing_fields: List[str] = Field(default_factory=list)
    confidence_score: float = Field(1.0, ge=0.0, le=1.0)

    @field_validator("metric")
    @classmethod
    def normalize_metric(cls, v: str) -> str:
        """Normalize metric name to uppercase."""
        return v.upper().strip()

    @field_validator("bank_names")
    @classmethod
    def normalize_bank_names(cls, v: List[str]) -> List[str]:
        """Normalize bank names to uppercase."""
        return [b.upper().strip() for b in v]

    def is_complete(self) -> bool:
        """Check if query spec is complete and ready for SQL generation."""
        return (
            not self.requires_clarification
            and bool(self.metric)
            and self.confidence_score >= 0.6
        )


class RagContext(BaseModel):
    """
    RAG-retrieved context for SQL generation.

    This structure holds the relevant schema, metric definitions,
    and example queries retrieved from Qdrant vector database.

    Attributes:
        metric_definitions: Metric formulas and metadata
        schema_snippets: Table/column definitions
        example_queries: Similar NL→SQL examples
        available_columns: Whitelist of available DB columns

    Example:
        RagContext(
            metric_definitions=[
                {
                    "metric_name": "IMOR",
                    "formula": "(etapa_3 + castigos) / cartera_comercial",
                    "columns_required": ["imor"],
                    "description": "Índice de Morosidad"
                }
            ],
            schema_snippets=[
                {
                    "table": "monthly_kpis",
                    "column": "imor",
                    "data_type": "float",
                    "description": "Índice de morosidad mensual"
                }
            ],
            example_queries=[
                {
                    "nl_query": "IMOR de INVEX últimos 6 meses",
                    "sql_template": "SELECT fecha, imor FROM monthly_kpis WHERE..."
                }
            ],
            available_columns=["imor", "icor", "cartera_total", ...]
        )
    """

    metric_definitions: List[dict] = Field(default_factory=list)
    schema_snippets: List[dict] = Field(default_factory=list)
    example_queries: List[dict] = Field(default_factory=list)
    available_columns: List[str] = Field(default_factory=list)

    def has_column(self, column_name: str) -> bool:
        """Check if column is available in schema."""
        return column_name.lower() in [c.lower() for c in self.available_columns]

    def get_metric_definition(self, metric_name: str) -> Optional[dict]:
        """Get definition for specific metric."""
        for defn in self.metric_definitions:
            if defn.get("metric_name", "").upper() == metric_name.upper():
                return defn
        return None


class SqlGenerationResult(BaseModel):
    """
    Result of SQL generation process.

    Attributes:
        success: True if SQL was generated successfully
        sql: Generated SQL query (SELECT only)
        error_code: Error code if failed (e.g., "missing_columns", "unsupported_metric")
        error_message: Human-readable error message
        used_template: True if pre-defined template was used (not LLM-generated)
        metadata: Additional information (template name, LLM tokens, etc.)

    Error Codes:
        - missing_columns: Required DB columns don't exist
        - unsupported_metric: Metric not in whitelist
        - ambiguous_spec: QuerySpec is incomplete
        - generation_failed: LLM failed to generate valid SQL

    Examples:
        # Success
        SqlGenerationResult(
            success=True,
            sql="SELECT fecha, imor FROM monthly_kpis WHERE...",
            used_template=True,
            metadata={"template": "IMOR_last_n_months"}
        )

        # Failure - missing columns
        SqlGenerationResult(
            success=False,
            sql=None,
            error_code="missing_columns",
            error_message="ICAP metric requires 'icap_total' column which doesn't exist in database",
            metadata={"missing": ["icap_total"]}
        )
    """

    success: bool
    sql: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    used_template: bool = False
    metadata: dict = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """
    Result of SQL security validation.

    Attributes:
        valid: True if SQL passed all security checks
        error_message: Validation error if failed
        sanitized_sql: SQL with safety modifications (e.g., added LIMIT)
        warnings: Non-fatal warnings

    Security Checks:
        1. No DDL/DML keywords (INSERT, UPDATE, DELETE, DROP, etc.)
        2. Only SELECT statements
        3. Only whitelisted tables
        4. No suspicious patterns (UNION, EXEC, --, /*)
        5. LIMIT injection for unbounded queries

    Examples:
        # Valid query
        ValidationResult(
            valid=True,
            sanitized_sql="SELECT fecha, imor FROM monthly_kpis WHERE... LIMIT 1000"
        )

        # Invalid - DDL detected
        ValidationResult(
            valid=False,
            error_message="Forbidden keyword detected: DROP",
            sanitized_sql=None
        )
    """

    valid: bool
    error_message: Optional[str] = None
    sanitized_sql: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
