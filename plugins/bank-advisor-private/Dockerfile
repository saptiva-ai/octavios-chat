# BankAdvisor MCP Server Dockerfile
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# Context is project root, so use full path to plugin
COPY plugins/bank-advisor-private/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code from plugin directory
COPY plugins/bank-advisor-private/src/ ./src/
COPY plugins/bank-advisor-private/data/ ./data/

# Set PYTHONPATH to include src directory
ENV PYTHONPATH=/app/src

# Create non-root user
RUN useradd --create-home --shell /bin/bash --uid 1001 bankadvisor && \
    chown -R bankadvisor:bankadvisor /app

USER bankadvisor

# Expose MCP Server port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Start the MCP server via uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
