# Multi-stage Docker build for Aletheia Deep Research
# Stage 1: Base image with Python
FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 aletheia \
    && useradd --uid 1000 --gid aletheia --shell /bin/bash --create-home aletheia

# Set working directory
WORKDIR /app

# Stage 2: Dependencies
FROM base AS dependencies

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Development
FROM dependencies AS development

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest==7.4.3 \
    pytest-asyncio==0.21.1 \
    pytest-cov==4.1.0 \
    black==23.11.0 \
    ruff==0.1.6 \
    mypy==1.7.1

# Copy source code
COPY --chown=aletheia:aletheia . .

# Switch to non-root user
USER aletheia

# Expose port
EXPOSE 8000

# Default command for development
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Stage 4: Production
FROM dependencies AS production

# Copy only necessary files
COPY --chown=aletheia:aletheia domain/ ./domain/
COPY --chown=aletheia:aletheia adapters/ ./adapters/
COPY --chown=aletheia:aletheia apps/ ./apps/
COPY --chown=aletheia:aletheia ports/ ./ports/
COPY --chown=aletheia:aletheia pyproject.toml .

# Create necessary directories
RUN mkdir -p /app/runs /app/logs \
    && chown aletheia:aletheia /app/runs /app/logs

# Switch to non-root user
USER aletheia

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Production command
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# Default target is production
FROM production