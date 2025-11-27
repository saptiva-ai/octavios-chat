"""
BankAdvisor chart data schemas (BA-P0-003).

Defines the message contract for bank visualization data
between backend and frontend.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PlotlyTrace(BaseModel):
    """Single trace in a Plotly chart."""

    x: List[str] = Field(..., description="X-axis values (dates)")
    y: List[float] = Field(..., description="Y-axis values (metrics)")
    type: str = Field(default="scatter", description="Chart type: scatter, bar, line")
    name: Optional[str] = Field(None, description="Trace name for legend")
    mode: Optional[str] = Field(None, description="Display mode: lines, markers, lines+markers")
    marker: Optional[Dict[str, Any]] = Field(None, description="Marker styling")
    line: Optional[Dict[str, Any]] = Field(None, description="Line styling")


class PlotlyLayout(BaseModel):
    """Plotly chart layout configuration."""

    title: Optional[str] = None
    xaxis: Optional[Dict[str, Any]] = None
    yaxis: Optional[Dict[str, Any]] = None
    legend: Optional[Dict[str, Any]] = None
    margin: Optional[Dict[str, Any]] = None
    height: Optional[int] = Field(default=400, description="Chart height in pixels")
    showlegend: Optional[bool] = True

    class Config:
        extra = "allow"


class PlotlyConfig(BaseModel):
    """Plotly chart display configuration."""

    responsive: bool = True
    displayModeBar: bool = True
    displaylogo: bool = False

    class Config:
        extra = "allow"


class PlotlyChartSpec(BaseModel):
    """Complete Plotly chart specification."""

    data: List[PlotlyTrace]
    layout: PlotlyLayout = Field(default_factory=PlotlyLayout)
    config: PlotlyConfig = Field(default_factory=PlotlyConfig)


class TimeRange(BaseModel):
    """Time range for the data query."""

    start: str = Field(..., description="Start date ISO format")
    end: str = Field(..., description="End date ISO format")


class BankChartData(BaseModel):
    """
    Bank chart artifact payload.

    This is the data structure embedded in ChatMessage.artifact
    when kind === 'bank_chart'.
    """

    type: str = Field(default="bank_chart", description="Artifact type identifier")
    metric_name: str = Field(..., description="Name of the metric being displayed")
    bank_names: List[str] = Field(..., description="Banks included in the visualization")
    time_range: TimeRange = Field(..., description="Time range of the data")
    plotly_config: PlotlyChartSpec = Field(..., description="Plotly.js chart configuration")
    data_as_of: str = Field(..., description="Data freshness timestamp")
    source: str = Field(default="bank-advisor-mcp", description="Data source identifier")
    title: Optional[str] = Field(None, description="Human-readable chart title")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "bank_chart",
                "metric_name": "imor",
                "bank_names": ["INVEX", "Sistema"],
                "time_range": {"start": "2024-01-01", "end": "2025-07-01"},
                "plotly_config": {
                    "data": [
                        {
                            "x": ["2024-01", "2024-02", "2024-03"],
                            "y": [2.1, 2.3, 2.0],
                            "type": "scatter",
                            "mode": "lines+markers",
                            "name": "INVEX",
                        }
                    ],
                    "layout": {"title": "IMOR - INVEX vs Sistema"},
                    "config": {"responsive": True},
                },
                "data_as_of": "2025-07-01T00:00:00Z",
                "source": "bank-advisor-mcp",
                "title": "Índice de Morosidad (IMOR) - INVEX",
            }
        }


class BankAnalyticsRequest(BaseModel):
    """Request payload for bank analytics queries."""

    metric_or_query: str = Field(
        ...,
        description="Metric name or natural language query",
        examples=["IMOR", "cartera comercial", "ICAP de INVEX últimos 3 meses"],
    )
    mode: str = Field(
        default="dashboard",
        description="Visualization mode: dashboard or timeline",
    )
    bank: Optional[str] = Field(
        None,
        description="Specific bank to query (optional)",
    )
    time_range: Optional[str] = Field(
        None,
        description="Time range specification: last_3_months, year_2024, etc.",
    )


class BankAnalyticsResponse(BaseModel):
    """Response from bank analytics MCP tool."""

    success: bool = True
    data: Optional[BankChartData] = None
    error: Optional[str] = None
    message: Optional[str] = None
