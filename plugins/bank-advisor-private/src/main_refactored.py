"""
BankAdvisor MCP Server - SOLID Refactored Version

Esta versión implementa:
- SRP: Responsabilidades separadas en clases dedicadas
- OCP: Extensible via Strategy Pattern
- LSP: N/A (no hay jerarquías)
- ISP: Interfaces segregadas (protocols)
- DIP: Depende de abstracciones, no de implementaciones concretas

Patrones implementados:
- Dependency Injection
- Orchestrator Pattern
- Strategy Pattern
- Factory Pattern
- Adapter Pattern
"""
import os
from contextlib import asynccontextmanager
from typing import Dict, Any

import structlog
from fastapi import FastAPI
from mcp.server.fastapi import FastMCP
from sqlalchemy import text

# Import protocols and core components
from bankadvisor.core.protocols import MetricQuery
from bankadvisor.core.orchestrator import BankAnalyticsOrchestrator
from bankadvisor.core.adapters import (
    IntentServiceAdapter,
    MetricsRepositoryAdapter,
    VisualizationFactory,
    QueryValidator,
    ResponseFormatter
)

# Import existing services (for adaptation)
from bankadvisor.db import AsyncSessionLocal, init_db
from bankadvisor.services.intent_service import IntentService

logger = structlog.get_logger(__name__)


# ============================================================================
# DEPENDENCY INJECTION CONTAINER
# ============================================================================

class DIContainer:
    """
    Dependency Injection Container (Service Locator Pattern).

    Manages creation and lifecycle of all dependencies.
    Implements Singleton pattern for services.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Initialize services (lazy initialization)
        self._intent_service = None
        self._orchestrator = None
        self._initialized = True

    def get_intent_service(self) -> IntentServiceAdapter:
        """Get or create IntentService (Singleton)"""
        if self._intent_service is None:
            concrete_service = IntentService
            self._intent_service = IntentServiceAdapter(concrete_service)
        return self._intent_service

    def get_metrics_repository(self) -> MetricsRepositoryAdapter:
        """Get or create MetricsRepository"""
        return MetricsRepositoryAdapter(session_factory=AsyncSessionLocal)

    def get_visualization_factory(self) -> VisualizationFactory:
        """Get or create VisualizationFactory"""
        return VisualizationFactory()

    def get_query_validator(self) -> QueryValidator:
        """Get or create QueryValidator"""
        return QueryValidator(allowed_modes=["dashboard", "timeline"])

    def get_response_formatter(self) -> ResponseFormatter:
        """Get or create ResponseFormatter"""
        return ResponseFormatter()

    def get_orchestrator(self) -> BankAnalyticsOrchestrator:
        """
        Get or create Orchestrator with all dependencies injected.

        This is the main composition root (Dependency Injection pattern).
        """
        if self._orchestrator is None:
            self._orchestrator = BankAnalyticsOrchestrator(
                intent_service=self.get_intent_service(),
                metrics_repository=self.get_metrics_repository(),
                visualization_factory=self.get_visualization_factory(),
                query_validator=self.get_query_validator(),
                response_formatter=self.get_response_formatter()
            )
        return self._orchestrator


# Initialize DI container
container = DIContainer()


# ============================================================================
# STARTUP LOGIC
# ============================================================================

async def ensure_data_populated():
    """
    Verifica si la base de datos tiene datos. Si está vacía, ejecuta el ETL.

    Nota: Esta función NO cambió en el refactor. Se mantiene porque
    es responsabilidad de startup, no de analytics.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM monthly_kpis WHERE fecha > '2025-01-01'")
            )
            row_count = result.scalar()

            if row_count == 0:
                logger.info("database.empty", message="No data found, running ETL")
                from bankadvisor.etl_loader import main as etl_main
                etl_main()
                logger.info("etl.completed", message="ETL executed successfully")
            else:
                logger.info(
                    "database.ready",
                    message=f"Data already present ({row_count} records)"
                )

    except Exception as e:
        logger.error("startup.etl_check_failed", error=str(e))
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic"""
    logger.info("bankadvisor.starting", version="2.0.0-refactored")

    # Initialize database
    await init_db()
    logger.info("database.initialized")

    # Initialize NLP Intent Service (singleton initialization)
    IntentService.initialize()
    logger.info("nlp.initialized")

    # Ensure data is populated
    await ensure_data_populated()

    logger.info("bankadvisor.ready", port=8000, architecture="SOLID")
    yield

    logger.info("bankadvisor.shutdown")


# ============================================================================
# MCP SERVER INITIALIZATION
# ============================================================================

mcp = FastMCP("BankAdvisor Enterprise SOLID", lifespan=lifespan)


# ============================================================================
# MCP TOOL: bank_analytics (REFACTORED)
# ============================================================================

@mcp.tool()
async def bank_analytics(
    metric_or_query: str,
    mode: str = "dashboard"
) -> Dict[str, Any]:
    """
    Consulta métricas bancarias (INVEX + Sistema Financiero Mexicano).

    CAMBIOS EN REFACTOR:
    - Ahora delega TODO el trabajo al Orchestrator
    - No tiene lógica de negocio (solo coordinación)
    - Sigue SRP: Solo traduce request MCP → Domain Query

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

    Architecture:
        - Uses Orchestrator Pattern for workflow coordination
        - Dependency Injection for all services
        - Strategy Pattern for visualizations
    """
    # Create domain query object (Value Object pattern)
    query = MetricQuery(raw_query=metric_or_query, mode=mode)

    # Get orchestrator from DI container
    orchestrator = container.get_orchestrator()

    # Delegate ALL work to orchestrator (SRP)
    # Orchestrator coordinates: validation → NLP → DB → viz → format
    return await orchestrator.execute(query)


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@mcp.get("/health")
async def health_check():
    """Health check endpoint for Docker healthcheck"""
    try:
        # Check database connectivity
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "service": "bank-advisor-mcp",
            "version": "2.0.0-refactored",
            "architecture": "SOLID"
        }
    except Exception as e:
        logger.error("health_check.failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info("bankadvisor.server_starting", host=host, port=port)

    uvicorn.run(
        "src.main_refactored:mcp",
        host=host,
        port=port,
        log_level="info",
        reload=False
    )
