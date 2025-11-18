"""Excel Data Analysis Tool."""

from typing import Any, Dict, Optional, List
import pandas as pd
import structlog

from ..protocol import ToolSpec, ToolCategory, ToolCapability
from ..tool import Tool
from ...models.document import Document
from ...services.minio_storage import get_minio_storage

logger = structlog.get_logger(__name__)


class ExcelAnalyzerTool(Tool):
    """Excel Data Analysis Tool."""

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="excel_analyzer",
            version="1.0.0",
            display_name="Excel Data Analyzer",
            description="Analyzes Excel files (xlsx/xls) and returns statistics, aggregations, and data validation results.",
            category=ToolCategory.DATA_ANALYTICS,
            capabilities=[ToolCapability.SYNC, ToolCapability.IDEMPOTENT, ToolCapability.CACHEABLE],
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document ID (Excel file)"},
                    "sheet_name": {"type": "string", "description": "Sheet name (default: first sheet)"},
                    "operations": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["stats", "aggregate", "validate", "preview"]},
                        "default": ["stats", "preview"],
                    },
                    "aggregate_columns": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["doc_id"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "sheet_name": {"type": "string"},
                    "stats": {"type": "object"},
                    "aggregates": {"type": "object"},
                    "validation": {"type": "object"},
                    "preview": {"type": "array"},
                },
            },
            tags=["excel", "data", "analytics", "spreadsheet", "pandas"],
            requires_auth=True,
            rate_limit={"calls_per_minute": 20},
            timeout_ms=30000,
            max_payload_size_kb=10,
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        if "doc_id" not in payload:
            raise ValueError("Missing required field: doc_id")

    async def execute(self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        doc_id = payload["doc_id"]
        sheet_name = payload.get("sheet_name")
        operations = payload.get("operations", ["stats", "preview"])
        aggregate_columns = payload.get("aggregate_columns", [])
        user_id = context.get("user_id") if context else None

        logger.info("Excel analyzer tool execution started", doc_id=doc_id, user_id=user_id)

        doc = await Document.get(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")

        if user_id and doc.user_id != user_id:
            raise PermissionError(f"User {user_id} not authorized to analyze document {doc_id}")

        if doc.content_type not in [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        ]:
            raise ValueError(f"Document is not an Excel file: {doc.content_type}")

        minio_storage = get_minio_storage()
        excel_path, is_temp = minio_storage.materialize_document(doc.minio_key, filename=doc.filename)

        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name or 0)
            actual_sheet_name = sheet_name or "Sheet1"

            result: Dict[str, Any] = {"doc_id": doc_id, "sheet_name": actual_sheet_name}

            if "stats" in operations:
                result["stats"] = self._compute_stats(df)

            if "aggregate" in operations:
                result["aggregates"] = self._compute_aggregates(df, aggregate_columns)

            if "validate" in operations:
                result["validation"] = self._validate_data(df)

            if "preview" in operations:
                result["preview"] = df.head(10).to_dict(orient="records")

            return result
        finally:
            if is_temp and excel_path.exists():
                excel_path.unlink()

    def _compute_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        columns_info = []
        for col in df.columns:
            columns_info.append({
                "name": col,
                "dtype": str(df[col].dtype),
                "non_null_count": int(df[col].count()),
                "null_count": int(df[col].isnull().sum()),
            })
        return {"row_count": len(df), "column_count": len(df.columns), "columns": columns_info}

    def _compute_aggregates(self, df: pd.DataFrame, columns: List[str]) -> Dict[str, Dict[str, float]]:
        aggregates = {}
        for col in columns:
            if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
                continue
            aggregates[col] = {
                "sum": float(df[col].sum()),
                "mean": float(df[col].mean()),
                "median": float(df[col].median()),
                "std": float(df[col].std()),
                "min": float(df[col].min()),
                "max": float(df[col].max()),
            }
        return aggregates

    def _validate_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        total_missing = int(df.isnull().sum().sum())
        columns_with_missing = df.columns[df.isnull().any()].tolist()
        return {"total_missing_values": total_missing, "columns_with_missing": columns_with_missing, "type_mismatches": []}
