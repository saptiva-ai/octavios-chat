"""Excel analyzer tool placeholder with deterministic schema."""

from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.mcp.base import BaseTool, ToolExecutionError
from backend.mcp.protocol import ToolLimits
from backend.mcp._logging import get_logger

logger = get_logger(__name__)


class AggregationOperation(BaseModel):
    """Supported aggregations for inline previews."""

    type: str = Field(..., pattern="^(sum|avg|min|max|count)$")
    column: str


class ExcelAnalyzerInput(BaseModel):
    file_id: Optional[str] = Field(
        default=None,
        description="Identifier of the spreadsheet stored on the platform",
    )
    sheet_name: Optional[str] = Field(default=None, description="Optional sheet to target")
    operations: List[AggregationOperation] = Field(default_factory=list)
    sample_rows: Optional[List[Dict[str, float]]] = Field(
        default=None,
        description="Optional inline rows for quick aggregations (used for previews)",
    )
    limit_rows: int = Field(default=500, ge=1, le=5000)

    @field_validator("operations")
    @classmethod
    def _require_operations(cls, value: List[AggregationOperation]) -> List[AggregationOperation]:
        if not value:
            raise ValueError("At least one operation is required")
        return value


class AggregationResult(BaseModel):
    operation: str
    column: str
    value: Optional[float]
    rows_scanned: int


class ExcelAnalyzerOutput(BaseModel):
    status: str = Field(..., description="inline | queued")
    message: str
    operations: List[AggregationResult] = Field(default_factory=list)
    data_preview: Optional[List[Dict[str, float]]] = None


class ExcelAnalyzerTool(BaseTool):
    """Executes lightweight aggregations or enqueues heavy jobs."""

    name = "excel_analyzer"
    version = "v1"
    description = "Lee hojas de cálculo, valida tipos básicos y genera agregados."
    capabilities = ("spreadsheets", "analytics", "preview")
    input_model = ExcelAnalyzerInput
    output_model = ExcelAnalyzerOutput
    limits = ToolLimits(timeout_ms=15_000, max_payload_kb=32, max_attachment_mb=100)

    async def _execute(self, payload: ExcelAnalyzerInput, context) -> Dict[str, Any]:
        # Inline analysis if sample rows provided, otherwise mark as queued
        if payload.sample_rows:
            logger.info(
                "Excel analyzer running inline preview",
                request_id=context.request_id,
                operations=len(payload.operations),
                sheet=payload.sheet_name,
            )
            return ExcelAnalyzerOutput(
                status="inline",
                message="Preview generated from supplied rows",
                operations=_run_aggregations(payload),
                data_preview=payload.sample_rows[: payload.limit_rows],
            ).model_dump()

        if not payload.file_id:
            raise ToolExecutionError(
                "file_id is required when sample_rows are not provided",
                code="invalid_payload",
                retryable=False,
            )

        logger.info(
            "Excel analyzer scheduled asynchronous run",
            file_id=payload.file_id,
            sheet=payload.sheet_name,
            request_id=context.request_id,
        )
        return ExcelAnalyzerOutput(
            status="queued",
            message="Requested analysis was queued; results will be attached asynchronously.",
            operations=[],
            data_preview=None,
        ).model_dump()


def _run_aggregations(payload: ExcelAnalyzerInput) -> List[AggregationResult]:
    rows = payload.sample_rows or []
    normalized_rows = rows[: payload.limit_rows]
    results: List[AggregationResult] = []

    for operation in payload.operations:
        column_values = [
            float(row[operation.column])
            for row in normalized_rows
            if operation.column in row and _is_number(row[operation.column])
        ]

        if operation.type == "count":
            value = len(column_values)
        elif not column_values:
            value = None
        elif operation.type == "sum":
            value = sum(column_values)
        elif operation.type == "avg":
            value = mean(column_values)
        elif operation.type == "min":
            value = min(column_values)
        elif operation.type == "max":
            value = max(column_values)
        else:
            value = None

        results.append(
            AggregationResult(
                operation=operation.type,
                column=operation.column,
                value=value,
                rows_scanned=len(normalized_rows),
            )
        )

    return results


def _is_number(value: object) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
