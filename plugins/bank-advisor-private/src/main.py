"""
BankAdvisor MCP Server - Enterprise Banking Analytics Microservice

Exposes banking analytics tools via MCP (Model Context Protocol) over HTTP.
This service is completely decoupled from the octavios-core monolith.

Architecture:
- FastMCP handles MCP protocol and tool registration
- FastAPI handles health checks and SSE endpoint
- Uses HTTP transport for remote access from octavios-core
"""
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict

import json
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastmcp import FastMCP
from sqlalchemy import text

# Import bankadvisor modules
from bankadvisor.db import AsyncSessionLocal, init_db
from bankadvisor.services.analytics_service import AnalyticsService
from bankadvisor.services.intent_service import IntentService
from bankadvisor.services.visualization_service import VisualizationService

logger = structlog.get_logger(__name__)


# ============================================================================
# STARTUP LOGIC: ETL Auto-Execution
# ============================================================================
async def ensure_data_populated():
    """
    Verifica si la base de datos tiene datos. Si está vacía, ejecuta el ETL.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Check if table exists and has data
            result = await session.execute(
                text("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'monthly_kpis'
                """)
            )
            table_exists = result.scalar() > 0

            if not table_exists:
                logger.info("database.table_missing", message="Table monthly_kpis doesn't exist yet")
                return

            # Check if table has recent data
            result = await session.execute(
                text("SELECT COUNT(*) FROM monthly_kpis WHERE fecha > '2025-01-01'")
            )
            row_count = result.scalar()

            if row_count == 0:
                logger.info("database.empty", message="No data found. ETL must be run manually via: python -m bankadvisor.etl_loader")
                # Skip automatic ETL - it's too slow for startup (228MB file)
                # ETL should be run manually after first deployment
            else:
                logger.info(
                    "database.ready",
                    message=f"Data already present ({row_count} records)"
                )

    except Exception as e:
        logger.error("startup.etl_check_failed", error=str(e))
        # Don't crash the server if ETL fails - may be transient DB issue
        pass


# ============================================================================
# FASTAPI APP WITH LIFESPAN
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic"""
    logger.info("bankadvisor.starting", version="1.0.0")

    # Initialize database
    await init_db()
    logger.info("database.initialized")

    # Initialize NLP Intent Service
    IntentService.initialize()
    logger.info("nlp.initialized")

    # Ensure data is populated
    await ensure_data_populated()

    port = int(os.getenv("PORT", "8002"))
    logger.info("bankadvisor.ready", port=port)
    yield

    logger.info("bankadvisor.shutdown")


# Create FastAPI app for health checks
app = FastAPI(
    title="BankAdvisor MCP Server",
    description="Enterprise Banking Analytics via MCP",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# MCP SERVER INITIALIZATION
# ============================================================================
mcp = FastMCP("BankAdvisor Enterprise")


# ============================================================================
# CORE BANK ANALYTICS LOGIC (callable directly)
# ============================================================================
async def _bank_analytics_impl(
    metric_or_query: str,
    mode: str = "dashboard"
) -> Dict[str, Any]:
    """
    Consulta métricas bancarias (INVEX + Sistema Financiero Mexicano).

    Esta tool consulta 103 meses de datos históricos (2017-2025) de la CNBV.
    Incluye validación de seguridad (whitelist) y NLP para entender queries.

    Args:
        metric_or_query: Nombre de métrica o query natural.
                        Ejemplos: "cartera comercial", "IMOR", "cartera total"
        mode: Modo de visualización ("dashboard" o "timeline")

    Returns:
        Dict con:
        - data: {months: [...], metadata: {...}}
        - plotly_config: Configuración de gráfico Plotly.js
        - title: Título del reporte
        - data_as_of: Fecha de corte de datos

    Examples:
        >>> await bank_analytics("cartera comercial")
        >>> await bank_analytics("IMOR", mode="timeline")

    Security:
        - Whitelist SAFE_METRIC_COLUMNS (15 métricas autorizadas)
        - Guard method _get_safe_column() previene inyección
        - NLP fuzzy matching con cutoff 0.8 (80% similitud)
    """
    logger.info(
        "tool.bank_analytics.invoked",
        metric_or_query=metric_or_query,
        mode=mode
    )

    try:
        # Disambiguate user query using NLP
        intent = IntentService.disambiguate(metric_or_query)

        if intent.is_ambiguous:
            logger.warning(
                "tool.bank_analytics.ambiguous",
                query=metric_or_query,
                options=intent.options[:3]
            )
            return {
                "error": "ambiguous_query",
                "message": f"Query '{metric_or_query}' es ambigua",
                "options": intent.options[:5],
                "suggestion": "Por favor, especifica: " + ", ".join(intent.options[:3])
            }

        # Get section config (contains field name, title, etc.)
        config = IntentService.get_section_config(intent.resolved_id)

        # Execute SQL query with security hardening
        async with AsyncSessionLocal() as session:
            payload = await AnalyticsService.get_dashboard_data(
                session,
                metric_or_query=config["field"],
                mode=mode
            )

        # Build Plotly visualization config
        plotly_config = VisualizationService.build_plotly_config(
            payload["data"]["months"],
            config
        )

        # Extract data_as_of from payload (structure varies)
        data_as_of = payload.get("data_as_of", payload.get("metadata", {}).get("data_as_of", "N/A"))

        logger.info(
            "tool.bank_analytics.success",
            metric=config["field"],
            months_returned=len(payload["data"]["months"]),
            data_as_of=data_as_of
        )

        return {
            "data": payload["data"],
            "metadata": {
                "metric": config["field"],
                "data_as_of": data_as_of,
                "title": payload.get("title", config.get("title", "Análisis Bancario")),
            },
            "plotly_config": plotly_config,
            "title": config.get("title", payload.get("title", "Análisis Bancario")),
            "data_as_of": data_as_of
        }

    except ValueError as ve:
        # Security validation failure (invalid metric)
        logger.warning("tool.bank_analytics.validation_error", error=str(ve))
        return {
            "error": "validation_failed",
            "message": str(ve)
        }

    except Exception as e:
        logger.error("tool.bank_analytics.error", error=str(e), exc_info=True)
        return {
            "error": "internal_error",
            "message": "Error interno procesando la consulta"
        }


# ============================================================================
# MCP TOOL WRAPPER (registered with FastMCP)
# ============================================================================
@mcp.tool()
async def bank_analytics(
    metric_or_query: str,
    mode: str = "dashboard"
) -> Dict[str, Any]:
    """
    Consulta métricas bancarias (INVEX + Sistema Financiero Mexicano).
    Wrapper para FastMCP que llama a la implementación real.
    """
    return await _bank_analytics_impl(metric_or_query, mode)


# ============================================================================
# HEALTH CHECK ENDPOINT (FastAPI)
# ============================================================================
@app.get("/health")
async def health_check():
    """Health check endpoint for Docker healthcheck"""
    try:
        # Check database connectivity
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "service": "bank-advisor-mcp",
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error("health_check.failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# ============================================================================
# JSON-RPC 2.0 ENDPOINT FOR BACKEND COMPATIBILITY
# ============================================================================
@app.post("/rpc")
async def json_rpc_endpoint(request: Request):
    """
    JSON-RPC 2.0 endpoint for direct tool invocation from OctaviOS backend.

    This endpoint provides a simple JSON-RPC interface that matches the
    pattern used by other MCP clients in the monolith (audit_mcp_client).
    """
    try:
        body = await request.json()

        # Validate JSON-RPC 2.0 structure
        if body.get("jsonrpc") != "2.0":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {"code": -32600, "message": "Invalid Request: jsonrpc must be '2.0'"}
            }, status_code=400)

        method = body.get("method")
        params = body.get("params", {})
        rpc_id = body.get("id", "1")

        # Handle tools/call method
        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "bank_analytics":
                # Invoke the bank_analytics implementation directly
                result = await _bank_analytics_impl(
                    metric_or_query=arguments.get("metric_or_query", ""),
                    mode=arguments.get("mode", "dashboard")
                )

                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}]
                    }
                })
            else:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}
                }, status_code=404)

        # Handle tools/list method
        elif method == "tools/list":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "tools": [{
                        "name": "bank_analytics",
                        "description": "Consulta métricas bancarias (INVEX + Sistema Financiero Mexicano)",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "metric_or_query": {"type": "string", "description": "Metric name or natural language query"},
                                "mode": {"type": "string", "enum": ["dashboard", "timeline"], "default": "dashboard"}
                            },
                            "required": ["metric_or_query"]
                        }
                    }]
                }
            })

        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }, status_code=404)

    except json.JSONDecodeError:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error"}
        }, status_code=400)

    except Exception as e:
        logger.error("json_rpc.error", error=str(e), exc_info=True)
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id") if 'body' in dir() else None,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }, status_code=500)


# ============================================================================
# MOUNT MCP SERVER TO FASTAPI (for native MCP clients)
# ============================================================================
# Get the ASGI app from FastMCP and mount it
mcp_app = mcp.http_app(path="/mcp")
app.mount("/mcp", mcp_app)

# Also mount SSE endpoint for compatibility
sse_app = mcp.sse_app(path="/sse")
app.mount("/sse", sse_app)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8002"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info("bankadvisor.server_starting", host=host, port=port)

    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False  # Production mode
    )
