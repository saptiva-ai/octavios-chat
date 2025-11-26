# =============================================================================
# Capital 414 Private Plugin - COPILOTO_414 Audit Service (UV-OPTIMIZED)
# =============================================================================
# MCP Server for document compliance validation
# Port: 8002
# Performance: Build time reduced from ~50s to ~3s (cached) via uv
# =============================================================================

# =============================================================================
# STAGE 1: UV Builder
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

# Copy uv binary from official image (zero latency)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# UV Configuration
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements first (Docker cache optimization)
COPY plugins/capital414-private/requirements.txt .

# Install dependencies using uv with Docker mount cache
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -r requirements.txt

# =============================================================================
# STAGE 2: Runtime
# =============================================================================
FROM python:3.11-slim-bookworm

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    # MCP Server settings
    MCP_SERVER_NAME=file-auditor \
    MCP_SERVER_PORT=8002 \
    # LanguageTool connection (external service)
    LANGUAGETOOL_URL=http://languagetool:8010/v2/check

WORKDIR /app

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Activate venv by modifying PATH
ENV PATH="/opt/venv/bin:$PATH"

# Install system dependencies
# OpenCV: libgl1, libglib2.0-0, libsm6, libxext6, libxrender1
# Tesseract OCR: tesseract-ocr + language packs
# PDF processing: poppler-utils
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV dependencies (libgl1 replaces deprecated libgl1-mesa-glx)
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    # Tesseract OCR
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    # PDF processing
    poppler-utils \
    # Health check
    curl \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy source code (last for cache optimization)
COPY plugins/capital414-private/src/ ./src/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose MCP SSE port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Run MCP server
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
