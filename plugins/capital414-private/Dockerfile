# Capital 414 Private Plugin - COPILOTO_414 Audit Service
# MCP Server for document compliance validation

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    # MCP Server settings
    MCP_SERVER_NAME=file-auditor \
    MCP_SERVER_PORT=8002 \
    # LanguageTool connection (external service)
    LANGUAGETOOL_URL=http://languagetool:8010/v2/check

# Install system dependencies
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
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for Docker cache optimization)
COPY plugins/capital414-private/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY plugins/capital414-private/src/ ./src/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose MCP SSE port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8002/health')" || exit 1

# Run MCP server
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
