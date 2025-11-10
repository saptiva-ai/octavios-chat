"""Visualization tool that emits Plotly-compatible specs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.mcp.base import BaseTool, ToolExecutionError
from backend.mcp.protocol import ToolLimits
from backend.mcp._logging import get_logger

logger = get_logger(__name__)


class VizToolInput(BaseModel):
    query: str = Field(..., description="SQL or semantic query to execute")
    chart_type: str = Field(
        default="bar",
        pattern="^(bar|line|pie|table|scatter)$",
        description="Type of visualization to render",
    )
    x: Optional[str] = Field(default=None, description="Dimension column for X axis")
    y: List[str] = Field(default_factory=list, description="Metric columns for Y axis / values")
    dataset: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Inline dataset for preview rendering. If omitted, tool schedules the query.",
    )
    connection_id: Optional[str] = Field(default=None, description="Data source identifier")
    limit: int = Field(default=250, ge=1, le=5000)


class VizToolOutput(BaseModel):
    status: str
    spec: Dict[str, Any]
    insights: List[str] = Field(default_factory=list)
    result_preview: Optional[List[Dict[str, Any]]] = None


class VizTool(BaseTool):
    """Generates Plotly specs from preview data or defers heavy jobs."""

    name = "viz_tool"
    version = "v1"
    description = "Ejecuta queries SQL y regresa un spec Plotly/ECharts."
    capabilities = ("analytics", "visualization", "sql-gateway")
    input_model = VizToolInput
    output_model = VizToolOutput
    limits = ToolLimits(timeout_ms=20_000, max_payload_kb=32, max_attachment_mb=10)

    async def _execute(self, payload: VizToolInput, context) -> Dict[str, Any]:
        if payload.dataset:
            logger.info(
                "Viz tool generating inline spec",
                chart_type=payload.chart_type,
                request_id=context.request_id,
            )
            spec = _build_plotly_spec(payload)
            insights = _generate_insights(payload)
            preview = payload.dataset[: payload.limit]
            return VizToolOutput(
                status="inline",
                spec=spec,
                insights=insights,
                result_preview=preview,
            ).model_dump()

        if not payload.connection_id:
            raise ToolExecutionError(
                "connection_id is required when dataset preview is absent",
                code="invalid_payload",
                retryable=False,
            )

        logger.info(
            "Viz tool queued execution",
            connection_id=payload.connection_id,
            request_id=context.request_id,
            chart_type=payload.chart_type,
        )
        return VizToolOutput(
            status="queued",
            spec={
                "type": payload.chart_type,
                "config": {"query": payload.query, "status": "pending"},
            },
            insights=[],
            result_preview=None,
        ).model_dump()


def _build_plotly_spec(payload: VizToolInput) -> Dict[str, Any]:
    x_values = [row.get(payload.x) for row in payload.dataset] if payload.x else list(range(len(payload.dataset or [])))
    traces = []
    for metric in payload.y or ["value"]:
        traces.append(
            {
                "type": "scatter" if payload.chart_type == "line" else payload.chart_type,
                "mode": "lines+markers" if payload.chart_type == "line" else "markers",
                "name": metric,
                "x": x_values,
                "y": [row.get(metric) for row in payload.dataset or []],
            }
        )

    return {
        "data": traces,
        "layout": {
            "title": payload.query[:80] + ("..." if len(payload.query) > 80 else ""),
            "xaxis": {"title": payload.x or "index"},
            "yaxis": {"title": ", ".join(payload.y) or "value"},
        },
    }


def _generate_insights(payload: VizToolInput) -> List[str]:
    if not payload.dataset or not payload.y:
        return []

    first_metric = payload.y[0]
    values = [row.get(first_metric) for row in payload.dataset if isinstance(row.get(first_metric), (int, float))]
    if not values:
        return []

    max_value = max(values)
    min_value = min(values)
    avg_value = sum(values) / len(values)
    return [
        f"Valor máximo de {first_metric}: {max_value}",
        f"Valor mínimo de {first_metric}: {min_value}",
        f"Promedio de {first_metric}: {round(avg_value, 2)}",
    ]
