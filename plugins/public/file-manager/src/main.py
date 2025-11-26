"""
OctaviOS File Manager Plugin - Main Application

Microservicio híbrido REST + MCP para gestión de archivos.
Proporciona upload, download, extracción de texto y metadatos.

Port: 8003
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import download, health, metadata, upload
from .services.minio_client import init_minio_client, close_minio_client
from .services.redis_client import init_redis_client, close_redis_client

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    logger.info(
        "Starting File Manager plugin",
        service=settings.service_name,
        port=settings.port,
        minio_endpoint=settings.minio_endpoint,
    )

    # Initialize clients
    await init_minio_client()
    await init_redis_client()

    yield

    # Cleanup
    logger.info("Shutting down File Manager plugin")
    await close_minio_client()
    await close_redis_client()


# Create FastAPI application
app = FastAPI(
    title="OctaviOS File Manager",
    description="Public plugin for file upload, download, and text extraction (REST + MCP)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(upload.router, tags=["Upload"])
app.include_router(download.router, tags=["Download"])
app.include_router(metadata.router, tags=["Metadata"])


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "rest": "/docs",
            "health": "/health",
            "upload": "/upload",
            "download": "/download/{file_id}",
            "metadata": "/metadata/{file_id}",
        },
    }
