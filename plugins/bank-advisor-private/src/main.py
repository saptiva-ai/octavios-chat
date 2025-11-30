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
from bankadvisor.services.intent_service import IntentService, NlpIntentService, Intent
from bankadvisor.services.visualization_service import VisualizationService

# HU3: NLP Query Interpretation imports
from bankadvisor.config_service import get_config
from bankadvisor.entity_service import EntityService

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
# HU3: NLP QUERY INTERPRETATION PIPELINE
# ============================================================================

# Confidence threshold for automatic execution
CONFIDENCE_THRESHOLD = 0.7


async def _try_hu3_nlp_pipeline(
    user_query: str,
    mode: str = "dashboard"
) -> Optional[Dict[str, Any]]:
    """
    HU3 NLP Query Interpretation Pipeline.

    Pipeline:
        1. Extract entities (banks, dates, metrics)
        2. Classify intent (evolution, comparison, ranking, point_value)
        3. If confidence < threshold, return clarification
        4. Execute query with filters

    Args:
        user_query: Natural language query
        mode: Visualization mode

    Returns:
        Result dict or None if pipeline should fallback
    """
    logger.info("hu3_nlp.pipeline_start", query=user_query)

    async with AsyncSessionLocal() as session:
        try:
            # Step 1: Extract entities
            entities = await EntityService.extract(user_query, session)
            config = get_config()

            # Step 1.5: Check for ambiguous terms BEFORE metric resolution
            # This catches cases like "cartera de INVEX" where "cartera" is ambiguous
            ambiguity = config.check_ambiguous_term(user_query)
            if ambiguity:
                logger.info(
                    "hu3_nlp.ambiguous_term_detected",
                    query=user_query,
                    term=ambiguity["term"],
                    action="clarification"
                )
                return {
                    "type": "clarification",
                    "message": ambiguity["message"],
                    "options": ambiguity["options"],
                    "context": {
                        "ambiguous_term": ambiguity["term"],
                        "banks": entities.banks,
                        "date_start": str(entities.date_start) if entities.date_start else None,
                        "date_end": str(entities.date_end) if entities.date_end else None,
                        "original_query": user_query
                    }
                }

            # =========================================================================
            # HU3.4: ADDITIONAL CLARIFICATION CHECKS
            # =========================================================================

            # HU3.4-A: Multi-metric clarification
            # Check if user is asking for multiple metrics (e.g., "IMOR y ICOR")
            # IMPORTANT: Skip this check if we already have a single specific metric detected
            # (e.g., "cartera comercial sin gobierno" is ONE metric, not two)
            multiple_metrics = await EntityService.extract_multiple_metrics(user_query, session)
            if len(multiple_metrics) > 1 and not entities.metric_id:
                metrics_names = ", ".join([m[1] for m in multiple_metrics])
                logger.info(
                    "hu3_nlp.multi_metric_detected",
                    query=user_query,
                    metrics=multiple_metrics,
                    action="clarification"
                )
                return {
                    "type": "clarification",
                    "message": f"Detecté varias métricas: {metrics_names}. ¿Cómo quieres visualizarlas?",
                    "options": [
                        {"id": "combined", "label": "Gráfica combinada", "description": "Todas las métricas en un solo gráfico"},
                        {"id": "separate", "label": "Gráficas separadas", "description": "Un gráfico por cada métrica"},
                        {"id": "table", "label": "Tabla comparativa", "description": "Resumen en formato tabla"},
                        {"id": "first_only", "label": f"Solo {multiple_metrics[0][1]}", "description": "Mostrar solo la primera métrica"}
                    ],
                    "context": {
                        "metrics": [m[0] for m in multiple_metrics],
                        "metrics_display": [m[1] for m in multiple_metrics],
                        "banks": entities.banks,
                        "original_query": user_query
                    }
                }

            # HU3.4-B: Comparison clarification
            # Check if user wants to compare but targets are unclear
            is_comparison = EntityService.is_comparison_query(user_query)
            if is_comparison and entities.has_metric():
                # Check if comparison targets are specified
                has_multiple_banks = len(entities.banks) > 1
                has_vs_pattern = " vs " in user_query.lower() or " versus " in user_query.lower()

                if not has_multiple_banks and not has_vs_pattern:
                    logger.info(
                        "hu3_nlp.comparison_unclear",
                        query=user_query,
                        metric=entities.metric_id,
                        action="clarification"
                    )
                    return {
                        "type": "clarification",
                        "message": f"¿Qué tipo de comparación de {entities.metric_display} te interesa?",
                        "options": [
                            {"id": "invex_vs_sistema", "label": "INVEX vs Sistema", "description": "Comparar INVEX contra el promedio del sistema"},
                            {"id": "time_periods", "label": "Diferentes períodos", "description": "Comparar año actual vs anterior"},
                            {"id": "vs_other_metric", "label": "Contra otra métrica", "description": "Comparar con otro indicador"}
                        ],
                        "context": {
                            "metric": entities.metric_id,
                            "metric_display": entities.metric_display,
                            "banks": entities.banks,
                            "original_query": user_query
                        }
                    }

            # HU3.4-C: Time period clarification
            # Check for vague time references without explicit date range
            vague_time = EntityService.has_vague_time_reference(user_query)
            has_explicit_date = EntityService.has_explicit_date_range(user_query)

            if vague_time and not has_explicit_date and entities.has_metric():
                logger.info(
                    "hu3_nlp.vague_time_detected",
                    query=user_query,
                    vague_term=vague_time,
                    action="clarification"
                )
                return {
                    "type": "clarification",
                    "message": f"¿Qué período de tiempo te interesa para {entities.metric_display}?",
                    "options": [
                        {"id": "3m", "label": "Últimos 3 meses", "description": "Datos más recientes"},
                        {"id": "6m", "label": "Últimos 6 meses", "description": "Medio año"},
                        {"id": "12m", "label": "Último año", "description": "12 meses completos"},
                        {"id": "ytd", "label": "Este año (YTD)", "description": "Desde enero 2025"},
                        {"id": "all", "label": "Histórico completo", "description": "Todos los datos desde 2017"}
                    ],
                    "context": {
                        "vague_term": vague_time,
                        "metric": entities.metric_id,
                        "metric_display": entities.metric_display,
                        "banks": entities.banks,
                        "original_query": user_query
                    }
                }

            # HU3.4-D: Bank clarification
            # If metric found but no bank specified, ask which bank
            if entities.has_metric() and not entities.has_banks():
                # Only ask if query seems to want specific bank data
                # Skip if it's a general system-wide query
                general_terms = ["sistema", "promedio", "todos", "general", "total"]
                is_general_query = any(term in user_query.lower() for term in general_terms)

                if not is_general_query:
                    logger.info(
                        "hu3_nlp.bank_not_specified",
                        query=user_query,
                        metric=entities.metric_id,
                        action="clarification"
                    )
                    return {
                        "type": "clarification",
                        "message": f"¿De qué entidad quieres ver {entities.metric_display}?",
                        "options": [
                            {"id": "INVEX", "label": "INVEX", "description": "Solo datos de INVEX"},
                            {"id": "Sistema", "label": "Sistema Bancario", "description": "Promedio del sistema financiero"},
                            {"id": "ambos", "label": "Ambos (comparar)", "description": "Comparar INVEX vs Sistema"}
                        ],
                        "context": {
                            "metric": entities.metric_id,
                            "metric_display": entities.metric_display,
                            "date_start": str(entities.date_start) if entities.date_start else None,
                            "date_end": str(entities.date_end) if entities.date_end else None,
                            "original_query": user_query
                        }
                    }

            # =========================================================================
            # END HU3.4 CLARIFICATION CHECKS
            # =========================================================================

            # Step 2: If no metric found, ask for clarification
            if not entities.has_metric():
                logger.info(
                    "hu3_nlp.metric_not_found",
                    query=user_query,
                    action="clarification"
                )
                return {
                    "type": "clarification",
                    "message": "No pude identificar la métrica. ¿A cuál te refieres?",
                    "options": config.get_all_metric_options()[:6],
                    "context": {
                        "banks": entities.banks,
                        "date_start": str(entities.date_start) if entities.date_start else None,
                        "date_end": str(entities.date_end) if entities.date_end else None,
                        "original_query": user_query
                    }
                }

            # Step 3: Classify intent
            intent_result = await NlpIntentService.classify(user_query, entities)

            logger.info(
                "hu3_nlp.intent_classified",
                query=user_query,
                intent=intent_result.intent.value,
                confidence=intent_result.confidence,
                explanation=intent_result.explanation
            )

            # Step 4: If low confidence, ask for clarification
            if intent_result.confidence < CONFIDENCE_THRESHOLD or intent_result.intent == Intent.UNKNOWN:
                return {
                    "type": "clarification",
                    "message": f"Encontré {entities.metric_display}. ¿Qué te gustaría ver?",
                    "options": [
                        {"id": "point_value", "label": "Valor actual"},
                        {"id": "evolution", "label": "Evolución en el tiempo"},
                        {"id": "comparison", "label": "Comparación entre bancos"},
                        {"id": "ranking", "label": "Ranking de bancos"}
                    ],
                    "context": {
                        "metric": entities.metric_id,
                        "metric_display": entities.metric_display,
                        "banks": entities.banks,
                        "date_start": str(entities.date_start) if entities.date_start else None,
                        "date_end": str(entities.date_end) if entities.date_end else None,
                        "detected_intent": intent_result.intent.value,
                        "confidence": intent_result.confidence
                    }
                }

            # Step 5: Execute query with high confidence
            data = await AnalyticsService.get_filtered_data(
                session,
                metric_id=entities.metric_id,
                banks=entities.banks if entities.banks else None,
                date_start=entities.date_start,
                date_end=entities.date_end,
                intent=intent_result.intent.value
            )

            # Check for errors from analytics service
            if data.get("type") == "error":
                logger.warning(
                    "hu3_nlp.analytics_error",
                    query=user_query,
                    error=data.get("message")
                )
                return data

            # Generate Plotly visualization if data is available
            # SOLID Principle: Delegate to specialized PlotlyGenerator service
            if data.get("type") == "data" and "values" in data:
                from bankadvisor.services.plotly_generator import PlotlyGenerator

                plotly_config = PlotlyGenerator.generate(
                    metric_id=entities.metric_id,
                    data=data,
                    intent=intent_result.intent.value,
                    metric_display=entities.metric_display
                )

                if plotly_config:
                    data["plotly_config"] = plotly_config

            # Add metadata
            data["query_info"] = {
                "original_query": user_query,
                "detected_metric": entities.metric_display,
                "detected_banks": entities.banks,
                "detected_intent": intent_result.intent.value,
                "confidence": intent_result.confidence,
                "pipeline": "hu3_nlp"
            }

            logger.info(
                "hu3_nlp.success",
                query=user_query,
                metric=entities.metric_id,
                intent=intent_result.intent.value,
                banks_count=len(entities.banks) if entities.banks else 0
            )

            return data

        except Exception as e:
            logger.error(
                "hu3_nlp.error",
                query=user_query,
                error=str(e),
                exc_info=True
            )
            # Return None to trigger fallback to legacy pipeline
            return None


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
    # =========================================================================
    # PERFORMANCE TRACKING: Start timer
    # =========================================================================
    start_time = datetime.utcnow()

    logger.info(
        "tool.bank_analytics.invoked",
        metric_or_query=metric_or_query,
        mode=mode,
        nl2sql_available=NL2SQL_AVAILABLE
    )

    # =========================================================================
    # HU3: TRY NLP QUERY INTERPRETATION PIPELINE FIRST
    # =========================================================================
    try:
        hu3_result = await _try_hu3_nlp_pipeline(metric_or_query, mode)
        if hu3_result is not None:
            # HU3 pipeline succeeded or returned clarification
            if hu3_result.get("type") in ["data", "clarification", "error", "empty"]:
                # Performance tracking
                end_time = datetime.utcnow()
                duration_ms = (end_time - start_time).total_seconds() * 1000

                logger.info(
                    "tool.bank_analytics.hu3_success",
                    query=metric_or_query,
                    result_type=hu3_result.get("type"),
                    pipeline="hu3_nlp",
                    duration_ms=round(duration_ms, 2)
                )

                logger.info(
                    "bank_analytics.performance",
                    query=metric_or_query,
                    total_ms=round(duration_ms, 2),
                    pipeline="hu3_nlp",
                    result_type=hu3_result.get("type")
                )

                return hu3_result
    except Exception as e:
        logger.warning(
            "tool.bank_analytics.hu3_failed",
            query=metric_or_query,
            error=str(e),
            fallback="nl2sql_or_legacy"
        )
        # Continue to NL2SQL or legacy fallback

    # =========================================================================
    # PHASE 2-3: TRY NL2SQL PIPELINE SECOND
    # =========================================================================
    if NL2SQL_AVAILABLE and _query_parser and _context_service and _sql_generator:
        try:
            nl2sql_result = await _try_nl2sql_pipeline(metric_or_query, mode)
            if nl2sql_result and nl2sql_result.get("success"):
                # Performance tracking
                end_time = datetime.utcnow()
                duration_ms = (end_time - start_time).total_seconds() * 1000

                logger.info(
                    "tool.bank_analytics.nl2sql_success",
                    query=metric_or_query,
                    pipeline="nl2sql",
                    duration_ms=round(duration_ms, 2)
                )

                logger.info(
                    "bank_analytics.performance",
                    query=metric_or_query,
                    total_ms=round(duration_ms, 2),
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

        # =====================================================================
        # PERFORMANCE TRACKING: Calculate duration
        # =====================================================================
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        n_rows = len(payload["data"]["months"])

        logger.info(
            "tool.bank_analytics.success",
            metric=config["field"],
            months_returned=n_rows,
            data_as_of=data_as_of,
            pipeline="legacy",
            duration_ms=round(duration_ms, 2)
        )

        # Log performance metrics separately for easier querying
        logger.info(
            "bank_analytics.performance",
            query=metric_or_query,
            metric_id=config["field"],
            intent=mode,
            total_ms=round(duration_ms, 2),
            n_rows=n_rows,
            pipeline="legacy"
        )

        return {
            "data": payload["data"],
            "metadata": {
                "metric": config["field"],
                "data_as_of": data_as_of,
                "title": payload.get("title", config.get("title", "Análisis Bancario")),
                "performance": {
                    "duration_ms": round(duration_ms, 2),
                    "rows_returned": n_rows
                }
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
        banco = row_dict.get('banco_norm', 'Sistema')
        value = row_dict.get(metric_col)

        if fecha:
            # Format month label (e.g., "Jan 2024")
            if isinstance(fecha, datetime):
                month_label = fecha.strftime("%b %Y")
            else:
                month_label = str(fecha)[:7]  # "2024-01"

            data_by_month[month_label][banco] = value

    # Convert to legacy format
    # Sort months chronologically, not alphabetically (BA-P0-004)
    from datetime import datetime

    def parse_month_label(label: str):
        """Parse month label like 'Jan 2024' to datetime for sorting"""
        try:
            return datetime.strptime(label, "%b %Y")
        except:
            # Fallback: try ISO format "2024-01"
            try:
                return datetime.strptime(label, "%Y-%m")
            except:
                # If parsing fails, return label as-is (will sort alphabetically)
                return label

    months_data = []
    for month_label, banco_values in sorted(data_by_month.items(), key=lambda x: parse_month_label(x[0])):
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
    """
    Health check endpoint for Docker healthcheck.

    Returns service status plus last ETL run information.
    """
    try:
        # Check database connectivity
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))

            # Get last ETL run info
            last_etl = await session.execute(text("""
                SELECT
                    id,
                    started_at,
                    completed_at,
                    status,
                    duration_seconds,
                    rows_processed_base
                FROM etl_runs
                ORDER BY started_at DESC
                LIMIT 1
            """))
            etl_row = last_etl.fetchone()

        response = {
            "status": "healthy",
            "service": "bank-advisor-mcp",
            "version": "1.0.0"
        }

        # Add ETL info if available
        if etl_row:
            response["etl"] = {
                "last_run_id": etl_row[0],
                "last_run_started": etl_row[1].isoformat() if etl_row[1] else None,
                "last_run_completed": etl_row[2].isoformat() if etl_row[2] else None,
                "last_run_status": etl_row[3],
                "last_run_duration_seconds": etl_row[4],
                "last_run_rows": etl_row[5]
            }
        else:
            response["etl"] = {
                "last_run_status": "never_run",
                "message": "ETL has not been executed yet. Run: python -m bankadvisor.etl_runner"
            }

        return response
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
