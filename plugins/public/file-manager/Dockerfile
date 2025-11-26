# =============================================================================
# OctaviOS File Manager Plugin - Dockerfile (UV-OPTIMIZED)
# =============================================================================
# Public plugin for file upload, download, and text extraction (REST + MCP)
# Port: 8001
# Performance: Build time reduced from ~45s to ~3s (cached) via uv
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
COPY plugins/public/file-manager/requirements.txt .

# Install dependencies using uv with Docker mount cache
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install -r requirements.txt

# =============================================================================
# STAGE 2: Runtime
# =============================================================================
FROM python:3.11-slim-bookworm

# Metadata
LABEL maintainer="Saptiva Team <dev@saptiva.com>"
LABEL description="OctaviOS File Manager - Public Plugin for file operations"
LABEL version="1.0.0-uv"

WORKDIR /app

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Activate venv by modifying PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8001

# System dependencies for OCR/PDF processing
# tesseract: OCR engine for image text extraction
# poppler-utils: PDF to image conversion (pdftoppm)
# libmagic1: File type detection
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    poppler-utils \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy source code (last for cache optimization)
COPY plugins/public/file-manager/src/ ./src/

# Create non-root user for security (commented for development)
# Uncomment in production
# RUN useradd --create-home --shell /bin/bash --uid 1001 plugin_user && \
#     chown -R plugin_user:plugin_user /app
# USER plugin_user

EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Start server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
