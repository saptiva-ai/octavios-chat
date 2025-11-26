# =============================================================================
# OctaviOS File Manager Plugin - Dockerfile
# =============================================================================
# Public plugin for file upload, download, and text extraction (REST + MCP)
# Port: 8003
# =============================================================================

FROM python:3.11-slim

# Metadata
LABEL maintainer="Saptiva Team <dev@saptiva.com>"
LABEL description="OctaviOS File Manager - Public Plugin for file operations"
LABEL version="1.0.0"

# System dependencies for OCR/PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    poppler-utils \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8003

# Create non-root user
RUN useradd --create-home --shell /bin/bash --uid 1001 plugin_user \
    && chown -R plugin_user:plugin_user /app

USER plugin_user

EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Start server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8003"]
