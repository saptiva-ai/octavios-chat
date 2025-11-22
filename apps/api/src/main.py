"""
FastAPI application for Copilot OS API.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import get_settings
from .core.database import Database
from .core.exceptions import (
    APIError,
    api_exception_handler,
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from .core.logging import setup_logging
from .core.telemetry import (
    setup_telemetry,
    instrument_fastapi,
    shutdown_telemetry,
    increment_tool_invocation,
)
from .middleware.auth import AuthMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.telemetry import TelemetryMiddleware
from .middleware.cache_control import CacheControlMiddleware
from .routers import auth, chat, deep_research, health, history, reports, stream, metrics, conversations, intent, models, documents, review, features, files, mcp_admin, resources, artifacts
from .routers import settings as settings_router
from .services.storage import storage
from .core.auth import get_current_user

# MCP (Model Context Protocol) integration - Using FastMCP (official SDK)
try:
    from .mcp.server import mcp as mcp_server
    from .mcp.fastapi_adapter import MCPFastAPIAdapter
    from .mcp.tasks import task_manager
    from .mcp.lazy_routes import create_lazy_mcp_router
    _mcp_enabled = True
except ModuleNotFoundError as mcp_import_err:  # pragma: no cover - defensive guard for missing SDK deps
    # If fastmcp dependency chain is broken (e.g., mcp.types missing), downgrade gracefully
    structlog.get_logger(__name__).warning(
        "MCP disabled - dependency missing",
        error=str(mcp_import_err),
    )
    mcp_server = None
    MCPFastAPIAdapter = None  # type: ignore
    task_manager = None  # type: ignore
    create_lazy_mcp_router = None  # type: ignore
    _mcp_enabled = False

# Resource lifecycle management
from .workers.resource_cleanup_worker import get_cleanup_worker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    app_settings = get_settings()
    logger = structlog.get_logger()
    
    # Setup logging and telemetry
    setup_logging(app_settings.log_level)
    setup_telemetry(app_settings)
    
    # Connect to MongoDB
    await Database.connect_to_mongo()
    await storage.start_reaper()

    # Start MCP task manager (only if MCP is enabled)
    if _mcp_enabled and task_manager:
        await task_manager.start()

    # Start resource cleanup worker
    cleanup_worker = get_cleanup_worker()
    await cleanup_worker.start()

    logger.info("Starting Copilot OS API", version=app.version)

    yield

    # Shutdown telemetry
    shutdown_telemetry()

    # Stop resource cleanup worker
    await cleanup_worker.stop()

    # Stop MCP task manager
    if _mcp_enabled and task_manager:
        await task_manager.stop()

    # Close database connection
    await Database.close_mongo_connection()
    await storage.stop_reaper()
    logger.info("Shutting down Copilot OS API")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="OctaviOS Chat API",
        description="Conversational AI API with document review capabilities powered by SAPTIVA models",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Security middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.parsed_allowed_hosts,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Custom middleware
    app.add_middleware(TelemetryMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CacheControlMiddleware)  # ISSUE-023: Prevent caching of API responses
    
    # Exception handlers
    app.add_exception_handler(APIError, api_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    # Include routers
    app.include_router(auth.router, prefix="/api", tags=["auth"])
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(chat.router, prefix="/api", tags=["chat"])
    app.include_router(intent.router, prefix="/api", tags=["intent"])
    app.include_router(deep_research.router, prefix="/api", tags=["research"])
    app.include_router(stream.router, prefix="/api", tags=["streaming"])
    app.include_router(history.router, prefix="/api", tags=["history"])
    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(reports.router, prefix="/api", tags=["reports"])
    app.include_router(metrics.router, prefix="/api", tags=["monitoring"])
    app.include_router(settings_router.router, prefix="/api", tags=["settings"])
    app.include_router(models.router, prefix="/api", tags=["models"])
    app.include_router(features.router, prefix="/api", tags=["features"])
    app.include_router(files.router, prefix="/api", tags=["files"])
    app.include_router(documents.router, prefix="/api", tags=["documents"])
    app.include_router(review.router, prefix="/api", tags=["review"])
    app.include_router(resources.router, prefix="/api", tags=["resources"])
    app.include_router(artifacts.router, prefix="/api", tags=["artifacts"])
    # app.include_router(files.router, prefix="/api", tags=["files"])  # Temporarily disabled - Phase 3

    # MCP integration - Using FastMCP (official SDK) with FastAPI adapter
    # Tools defined in src/mcp/server.py: audit_file, excel_analyzer, viz_tool
    app.state.mcp_server = mcp_server if _mcp_enabled else None

    def _on_mcp_invoke(response):
        """Telemetry callback for tool invocations"""
        try:
            increment_tool_invocation(response["tool"])
        except Exception:  # pragma: no cover - telemetry best-effort
            pass

    # Create adapter to expose FastMCP tools via FastAPI REST endpoints
    mcp_adapter = None
    if _mcp_enabled and MCPFastAPIAdapter:
        mcp_adapter = MCPFastAPIAdapter(
            mcp_server=mcp_server,
            auth_dependency=get_current_user,
            on_invoke=_on_mcp_invoke,
        )

    # Store adapter in app.state for internal tool invocation (Phase 2 MCP integration)
    app.state.mcp_adapter = mcp_adapter

    # Mount MCP routes: GET /api/mcp/tools, POST /api/mcp/invoke, GET /api/mcp/health
    if _mcp_enabled and mcp_adapter:
        app.include_router(
            mcp_adapter.create_router(prefix="/mcp", tags=["mcp"]),
            prefix="/api",
        )

    # Mount MCP lazy loading routes (optimized - 98% context reduction)
    # GET /api/mcp/lazy/discover, GET /api/mcp/lazy/tools/{name}, POST /api/mcp/lazy/invoke
    if _mcp_enabled and create_lazy_mcp_router:
        lazy_mcp_router = create_lazy_mcp_router(
            auth_dependency=get_current_user,
            on_invoke=_on_mcp_invoke,
        )
        app.include_router(lazy_mcp_router, prefix="/api")

    # Mount MCP admin routes for cache management
    # DELETE /api/mcp/cache/*, GET /api/mcp/cache/stats, POST /api/mcp/cache/warmup
    if _mcp_enabled:
        app.include_router(mcp_admin.router, prefix="/api/mcp", tags=["mcp-admin"])

    # Instrument FastAPI for telemetry
    instrument_fastapi(app)

    return app


app = create_app()


if __name__ == "__main__":
    app_settings = get_settings()
    uvicorn.run(
        "main:app",
        host=app_settings.host,
        port=app_settings.port,
        reload=app_settings.debug,
        log_level=app_settings.log_level.lower(),
    )
