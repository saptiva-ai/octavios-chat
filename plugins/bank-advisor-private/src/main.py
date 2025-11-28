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
from typing import Any, Dict, Optional
from datetime import datetime

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

# NL2SQL Phase 2-3 imports (optional - graceful fallback if not available)
try:
    from bankadvisor.services.query_spec_parser import QuerySpecParser
    from bankadvisor.services.nl2sql_context_service import Nl2SqlContextService
    from bankadvisor.services.sql_generation_service import SqlGenerationService
    from bankadvisor.services.sql_validator import SqlValidator
    NL2SQL_AVAILABLE = True
except ImportError as e:
    logger.warning("nl2sql.imports_failed", error=str(e), fallback="Using legacy intent-based logic")
    NL2SQL_AVAILABLE = False

# Global instances for NL2SQL services (initialized in lifespan if available)
_query_parser: Optional["QuerySpecParser"] = None
_context_service: Optional["Nl2SqlContextService"] = None
_sql_generator: Optional["SqlGenerationService"] = None


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
    global _query_parser, _context_service, _sql_generator

    logger.info("bankadvisor.starting", version="1.0.0")

    # Initialize database
    await init_db()
    logger.info("database.initialized")

    # Initialize NLP Intent Service
    IntentService.initialize()
    logger.info("nlp.initialized")

    # Initialize NL2SQL services (Phase 2-3) if available
    if NL2SQL_AVAILABLE:
        try:
            from bankadvisor.services.rag_bridge import get_rag_bridge

            # Attempt to inject RAG services from main backend
            rag_bridge = get_rag_bridge()
            rag_available = rag_bridge.inject_from_main_backend()

            # Initialize parser (always available)
            _query_parser = QuerySpecParser()

            # Initialize SQL generator with SAPTIVA LLM client
            from bankadvisor.services.llm_client import get_saptiva_llm_client
            llm_client = get_saptiva_llm_client(model="SAPTIVA_TURBO")
            _sql_generator = SqlGenerationService(
                validator=SqlValidator(),
                llm_client=llm_client
            )

            if llm_client:
                logger.info("nl2sql.llm_enabled", provider="SAPTIVA", model="SAPTIVA_TURBO")
            else:
                logger.warning("nl2sql.llm_disabled", message="SAPTIVA client not available, using templates only")

            # Initialize context service with or without RAG
            if rag_available:
                _context_service = Nl2SqlContextService(
                    qdrant_service=rag_bridge.get_qdrant_service(),
                    embedding_service=rag_bridge.get_embedding_service()
                )

                # Ensure RAG collections exist
                _context_service.ensure_collections()

                logger.info(
                    "nl2sql.initialized",
                    rag_enabled=True,
                    qdrant_collection=rag_bridge.get_qdrant_service().collection_name,
                    note="RAG fully enabled. Seed collections with scripts/seed_nl2sql_rag.py"
                )
            else:
                _context_service = Nl2SqlContextService()  # No RAG - will use fallback

                logger.info(
                    "nl2sql.initialized",
                    rag_enabled=False,
                    note="Running in template-only mode (no RAG). RAG services not available."
                )

        except Exception as e:
            logger.error("nl2sql.initialization_failed", error=str(e), exc_info=True)
            _query_parser = None
            _context_service = None
            _sql_generator = None
    else:
        logger.info("nl2sql.disabled", reason="NL2SQL services not available, using legacy intent logic")

    # Ensure data is populated
    await ensure_data_populated()

    port = int(os.getenv("PORT", "8002"))
    logger.info("bankadvisor.ready", port=port, nl2sql_enabled=NL2SQL_AVAILABLE)
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

    Phase 2-3 NL2SQL Pipeline:
        1. Parse NL → QuerySpec (if NL2SQL available)
        2. Retrieve RAG context (schema/metrics/examples)
        3. Generate SQL from templates or LLM
        4. Validate SQL security
        5. Execute and visualize

    Fallback to Legacy:
        If NL2SQL fails or unavailable → intent-based logic (backward compatible)

    Args:
        metric_or_query: Nombre de métrica o query natural.
                        Ejemplos: "cartera comercial", "IMOR de INVEX últimos 3 meses"
        mode: Modo de visualización ("dashboard" o "timeline")

    Returns:
        Dict con:
        - data: {months: [...], metadata: {...}}
        - plotly_config: Configuración de gráfico Plotly.js
        - title: Título del reporte
        - data_as_of: Fecha de corte de datos

    Examples:
        >>> await bank_analytics("cartera comercial")
        >>> await bank_analytics("IMOR de INVEX últimos 3 meses")
        >>> await bank_analytics("Compara IMOR INVEX vs Sistema 2024")

    Security:
        - Whitelist SAFE_METRIC_COLUMNS (15 métricas autorizadas)
        - SQL validation via SqlValidator (blacklist/whitelist)
        - LIMIT injection (max 1000 rows)
    """
    logger.info(
        "tool.bank_analytics.invoked",
        metric_or_query=metric_or_query,
        mode=mode,
        nl2sql_available=NL2SQL_AVAILABLE
    )

    # =========================================================================
    # PHASE 2-3: TRY NL2SQL PIPELINE FIRST
    # =========================================================================
    if NL2SQL_AVAILABLE and _query_parser and _context_service and _sql_generator:
        try:
            nl2sql_result = await _try_nl2sql_pipeline(metric_or_query, mode)
            if nl2sql_result and nl2sql_result.get("success"):
                logger.info(
                    "tool.bank_analytics.nl2sql_success",
                    query=metric_or_query,
                    pipeline="nl2sql"
                )
                return nl2sql_result

            # NL2SQL returned error or low confidence - try legacy fallback
            logger.warning(
                "tool.bank_analytics.nl2sql_fallback",
                query=metric_or_query,
                reason=nl2sql_result.get("error_code") if nl2sql_result else "unknown",
                fallback="Using legacy intent-based logic"
            )

        except Exception as e:
            logger.error(
                "tool.bank_analytics.nl2sql_error",
                query=metric_or_query,
                error=str(e),
                exc_info=True,
                fallback="Using legacy intent-based logic"
            )
            # Continue to legacy fallback

    # =========================================================================
    # LEGACY FALLBACK: INTENT-BASED LOGIC (BACKWARD COMPATIBLE)
    # =========================================================================
    try:
        # Disambiguate user query using NLP
        intent = IntentService.disambiguate(metric_or_query)

        if intent.is_ambiguous:
            logger.warning(
                "tool.bank_analytics.ambiguous",
                query=metric_or_query,
                options=intent.options[:3],
                pipeline="legacy"
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
            data_as_of=data_as_of,
            pipeline="legacy"
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


async def _try_nl2sql_pipeline(user_query: str, mode: str) -> Optional[Dict[str, Any]]:
    """
    Attempt NL2SQL pipeline for query processing.

    Pipeline:
        1. Parse NL → QuerySpec
        2. Retrieve RAG context
        3. Generate SQL
        4. Execute SQL
        5. Build visualization

    Args:
        user_query: Natural language query
        mode: Visualization mode

    Returns:
        Result dict or None if pipeline fails

    Raises:
        Exception: If any step fails (caught by caller)
    """
    logger.debug("nl2sql_pipeline.start", query=user_query)

    # Step 1: Parse to QuerySpec
    spec = await _query_parser.parse(
        user_query=user_query,
        intent_hint=None,  # Let parser auto-detect
        mode_hint=mode
    )

    if not spec.is_complete():
        logger.warning(
            "nl2sql_pipeline.incomplete_spec",
            query=user_query,
            confidence=spec.confidence_score,
            missing=spec.missing_fields
        )
        return {
            "success": False,
            "error_code": "incomplete_spec",
            "error": "ambiguous_query",
            "message": f"Query is incomplete. Missing: {', '.join(spec.missing_fields)}",
            "confidence": spec.confidence_score
        }

    # Step 2: Retrieve RAG context
    ctx = await _context_service.rag_context_for_spec(spec, original_query=user_query)

    # Step 3: Generate SQL
    sql_result = await _sql_generator.build_sql_from_spec(spec, ctx)

    if not sql_result.success:
        logger.warning(
            "nl2sql_pipeline.sql_generation_failed",
            query=user_query,
            error_code=sql_result.error_code,
            error_message=sql_result.error_message
        )
        return {
            "success": False,
            "error_code": sql_result.error_code,
            "error": sql_result.error_code,
            "message": sql_result.error_message,
            "metadata": sql_result.metadata
        }

    # Step 4: Execute SQL
    logger.info(
        "nl2sql_pipeline.executing_sql",
        query=user_query,
        sql_preview=sql_result.sql[:100] if sql_result.sql else None
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(text(sql_result.sql))
        rows = result.fetchall()

    # Step 5: Transform to visualization format
    # Convert SQL rows to legacy format expected by VisualizationService
    # Legacy format: [{"month_label": "Jan 2024", "data": [{"category": "INVEX", "value": 0.05}]}]

    from collections import defaultdict
    from datetime import datetime

    # Group by month (fecha column)
    data_by_month = defaultdict(dict)
    metric_col = spec.metric.lower()

    for row in rows:
        row_dict = dict(row._mapping)
        fecha = row_dict.get('fecha')
        banco = row_dict.get('banco_nombre', 'Sistema')
        value = row_dict.get(metric_col)

        if fecha:
            # Format month label (e.g., "Jan 2024")
            if isinstance(fecha, datetime):
                month_label = fecha.strftime("%b %Y")
            else:
                month_label = str(fecha)[:7]  # "2024-01"

            data_by_month[month_label][banco] = value

    # Convert to legacy format
    months_data = []
    for month_label, banco_values in sorted(data_by_month.items()):
        month_entry = {
            "month_label": month_label,
            "data": [
                {"category": banco, "value": val}
                for banco, val in banco_values.items()
            ]
        }
        months_data.append(month_entry)

    # Build Plotly config
    # Use spec to determine title and styling
    title = f"{spec.metric} - {' vs '.join(spec.bank_names) if spec.bank_names else 'Sistema'}"

    # Add section_config with mode based on template
    section_config = {
        "title": title,
        "field": spec.metric.lower(),
        "description": f"Query: {user_query}",
        "mode": "timeline_with_summary" if sql_result.metadata.get("template") == "metric_timeseries" else "dashboard_month_comparison",
        "type": "ratio" if spec.metric.upper() in ["IMOR", "ICOR", "ICAP", "TDA"] else "absolute"
    }

    plotly_config = VisualizationService.build_plotly_config(
        months_data,
        section_config
    )

    logger.info(
        "nl2sql_pipeline.success",
        query=user_query,
        rows_returned=len(months_data),
        template_used=sql_result.metadata.get("template")
    )

    return {
        "success": True,
        "data": {"months": months_data},
        "metadata": {
            "metric": spec.metric,
            "data_as_of": "2025-11-27",  # TODO: Extract from actual data
            "title": title,
            "pipeline": "nl2sql",
            "template_used": sql_result.metadata.get("template"),
            "sql_generated": sql_result.sql
        },
        "plotly_config": plotly_config,
        "title": title,
        "data_as_of": "2025-11-27"
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
                # Track execution time
                import time
                start_time = time.time()

                try:
                    # Invoke the bank_analytics implementation directly
                    result = await _bank_analytics_impl(
                        metric_or_query=arguments.get("metric_or_query", ""),
                        mode=arguments.get("mode", "dashboard")
                    )

                    execution_time_ms = int((time.time() - start_time) * 1000)

                    # MEJORA: Wrap result with enhanced metadata
                    enhanced_result = {
                        "success": True,
                        "data": result,
                        "metadata": {
                            "version": "1.0.0",
                            "pipeline": result.get("metadata", {}).get("pipeline", "nl2sql"),
                            "template_used": result.get("metadata", {}).get("template_used"),
                            "execution_time_ms": execution_time_ms,
                            "requires_clarification": False,  # For future P0-3
                            "clarification_options": None,
                            "timestamp": datetime.utcnow().isoformat() + "Z"
                        }
                    }

                    logger.info(
                        "rpc.tool_success",
                        tool=tool_name,
                        execution_time_ms=execution_time_ms,
                        metric=result.get("metadata", {}).get("metric")
                    )

                    return JSONResponse({
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(enhanced_result)}]
                        }
                    })

                except Exception as e:
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    logger.error(
                        "rpc.tool_execution_failed",
                        tool=tool_name,
                        error=str(e),
                        execution_time_ms=execution_time_ms,
                        exc_info=True
                    )
                    return JSONResponse({
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {
                            "code": -32603,
                            "message": "Tool execution failed",
                            "data": {
                                "tool": tool_name,
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "execution_time_ms": execution_time_ms
                            }
                        }
                    }, status_code=500)
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
