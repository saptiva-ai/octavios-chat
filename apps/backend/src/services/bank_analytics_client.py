"""
MCP Client for BankAdvisor Analytics Plugin (BA-P0-001).

This module provides a client wrapper to invoke the bank_analytics
MCP tool on the bank-advisor microservice.

Usage:
    from services.bank_analytics_client import query_bank_analytics

    result = await query_bank_analytics(
        metric_or_query="IMOR de INVEX últimos 3 meses",
        mode="dashboard",
    )
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import httpx
import structlog

from ..schemas.bank_chart import BankChartData, BankAnalyticsResponse

logger = structlog.get_logger(__name__)

# Configuration from environment
BANK_ADVISOR_URL = os.getenv("BANK_ADVISOR_URL", "http://bank-advisor:8002")
BANK_ADVISOR_TIMEOUT = int(os.getenv("BANK_ADVISOR_TIMEOUT", "30"))
USE_BANK_ADVISOR = os.getenv("USE_BANK_ADVISOR", "true").lower() == "true"


class BankAdvisorUnavailableError(Exception):
    """Raised when the bank-advisor MCP service is unavailable."""
    pass


class BankAdvisorQueryError(Exception):
    """Raised when a query to bank-advisor fails."""
    pass


async def query_bank_analytics(
    metric_or_query: str,
    mode: str = "dashboard",
) -> BankAnalyticsResponse:
    """
    Query banking analytics via MCP protocol to bank-advisor service.

    Args:
        metric_or_query: Natural language query or metric name
            Examples: "IMOR", "cartera comercial", "ICAP de INVEX últimos 3 meses"
        mode: Visualization mode ("dashboard" or "timeline")

    Returns:
        BankAnalyticsResponse with BankChartData if successful

    Raises:
        BankAdvisorUnavailableError: If bank-advisor service is unavailable
        BankAdvisorQueryError: If the query fails (ambiguous, invalid, etc.)
    """
    if not USE_BANK_ADVISOR:
        raise BankAdvisorUnavailableError(
            "Bank advisor is disabled. Set USE_BANK_ADVISOR=true in environment."
        )

    logger.info(
        "bank_analytics.query",
        url=BANK_ADVISOR_URL,
        metric_or_query=metric_or_query,
        mode=mode,
    )

    try:
        async with httpx.AsyncClient(timeout=BANK_ADVISOR_TIMEOUT) as client:
            # JSON-RPC 2.0 call to RPC endpoint (direct endpoint, not FastMCP)
            response = await client.post(
                f"{BANK_ADVISOR_URL}/rpc",
                json={
                    "jsonrpc": "2.0",
                    "id": "bank-analytics-call",
                    "method": "tools/call",
                    "params": {
                        "name": "bank_analytics",
                        "arguments": {
                            "metric_or_query": metric_or_query,
                            "mode": mode,
                        },
                    },
                },
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            rpc_response = response.json()

            # Handle JSON-RPC error
            if "error" in rpc_response:
                error = rpc_response["error"]
                raise BankAdvisorQueryError(
                    f"MCP error: {error.get('message', str(error))}"
                )

            # Extract result from JSON-RPC response
            result = rpc_response.get("result", {})

            # Handle nested content structure from FastMCP
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                if isinstance(content, list) and len(content) > 0:
                    first_content = content[0]
                    if isinstance(first_content, dict) and "text" in first_content:
                        result = json.loads(first_content["text"])

            # Check for tool-level errors (ambiguous query, validation failed)
            if isinstance(result, dict) and result.get("error"):
                error_type = result.get("error")
                message = result.get("message", "Unknown error")

                if error_type == "ambiguous_query":
                    options = result.get("options", [])
                    suggestion = result.get("suggestion", "")
                    raise BankAdvisorQueryError(
                        f"Ambiguous query: {message}. Options: {options}. {suggestion}"
                    )
                elif error_type == "validation_failed":
                    raise BankAdvisorQueryError(f"Validation failed: {message}")
                else:
                    raise BankAdvisorQueryError(f"{error_type}: {message}")

            # Build BankChartData from successful result
            chart_data = _build_chart_data(result, metric_or_query)

            logger.info(
                "bank_analytics.success",
                metric=chart_data.metric_name,
                banks=chart_data.bank_names,
                data_as_of=chart_data.data_as_of,
            )

            return BankAnalyticsResponse(
                success=True,
                data=chart_data,
            )

    except httpx.HTTPStatusError as e:
        logger.error(
            "bank_analytics.http_error",
            status_code=e.response.status_code,
            detail=e.response.text,
        )
        raise BankAdvisorUnavailableError(
            f"Bank advisor returned HTTP {e.response.status_code}: {e.response.text}"
        )

    except httpx.RequestError as e:
        logger.error("bank_analytics.connection_error", error=str(e))
        raise BankAdvisorUnavailableError(
            f"Failed to connect to bank advisor at {BANK_ADVISOR_URL}: {str(e)}"
        )

    except BankAdvisorQueryError:
        raise  # Re-raise query errors as-is

    except Exception as e:
        logger.error("bank_analytics.unexpected_error", error=str(e), exc_info=True)
        raise BankAdvisorQueryError(f"Unexpected error: {str(e)}")


def _build_chart_data(result: Dict[str, Any], query: str) -> BankChartData:
    """
    Transform MCP tool result into BankChartData schema.

    Args:
        result: Raw result from bank_analytics MCP tool
        query: Original query string

    Returns:
        BankChartData instance
    """
    # Extract metadata
    metadata = result.get("metadata", {})
    data = result.get("data", {})
    plotly_config = result.get("plotly_config", {})

    # Extract time range from data
    months = data.get("months", [])
    time_range = {
        "start": months[0].get("fecha", "") if months else "",
        "end": months[-1].get("fecha", "") if months else "",
    }

    # Extract bank names from plotly traces
    bank_names = []
    if "data" in plotly_config:
        for trace in plotly_config["data"]:
            if trace.get("name"):
                bank_names.append(trace["name"])

    # Determine metric name from result or query
    metric_name = metadata.get("metric", query)
    if "title" in result:
        # Try to extract metric from title
        title = result["title"]
        if " - " in title:
            metric_name = title.split(" - ")[0].strip()

    return BankChartData(
        type="bank_chart",
        metric_name=metric_name,
        bank_names=bank_names or ["INVEX", "Sistema"],
        time_range={"start": time_range["start"], "end": time_range["end"]},
        plotly_config={
            "data": plotly_config.get("data", []),
            "layout": plotly_config.get("layout", {}),
            "config": plotly_config.get("config", {"responsive": True}),
        },
        data_as_of=result.get("data_as_of", metadata.get("data_as_of", "")),
        source="bank-advisor-mcp",
        title=result.get("title"),
    )


async def check_bank_advisor_health() -> bool:
    """
    Check if the bank-advisor service is healthy.

    Returns:
        True if service is available, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{BANK_ADVISOR_URL}/health")
            return response.status_code == 200
    except Exception:
        return False


async def is_bank_query(message: str) -> bool:
    """
    Simple heuristic to detect if a message is a banking query.

    This is a basic implementation - can be enhanced with ML/NLP later.

    Args:
        message: User message text

    Returns:
        True if message appears to be a banking query
    """
    message_lower = message.lower()

    # Banking-specific keywords
    banking_keywords = [
        "imor", "icor", "icap",
        "cartera", "comercial", "consumo", "vivienda",
        "morosidad", "mora",
        "invex", "banorte", "bancomer", "banamex", "santander", "hsbc", "scotiabank",
        "banco", "bancos", "bancario", "bancaria",
        "cnbv", "indicador", "indicadores",
        "crédito", "credito", "préstamo", "prestamo",
        "financiero", "financiera",
        "cartera vencida", "reservas",
    ]

    # Check for any banking keyword
    for keyword in banking_keywords:
        if keyword in message_lower:
            return True

    return False


# Convenience function for chat integration
async def get_bank_chart_for_message(
    message: str,
    mode: str = "dashboard",
) -> Optional[BankChartData]:
    """
    Convenience function to get bank chart data for a message.

    Returns None if:
    - Message doesn't appear to be a banking query
    - Bank advisor is unavailable
    - Query fails for any reason

    Args:
        message: User message text
        mode: Visualization mode

    Returns:
        BankChartData if successful, None otherwise
    """
    # Quick check if it's a banking query
    if not await is_bank_query(message):
        return None

    try:
        response = await query_bank_analytics(
            metric_or_query=message,
            mode=mode,
        )
        return response.data
    except (BankAdvisorUnavailableError, BankAdvisorQueryError) as e:
        logger.warning(
            "bank_analytics.skipped",
            message=message[:100],
            reason=str(e),
        )
        return None
