#!/usr/bin/env bash
# ============================================================================
# RAG Ingestion Test Wrapper
# ============================================================================
# Manages Python virtual environment and runs RAG ingestion tests
# Usage: ./scripts/test-rag-wrapper.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_SCRIPT="$SCRIPT_DIR/test-rag-ingestion.py"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}🔧 RAG Ingestion Test Setup${NC}"
echo ""

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}📦 Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate venv
echo -e "${YELLOW}🔌 Activating virtual environment...${NC}"
source "$VENV_DIR/bin/activate"

# Install/upgrade dependencies
echo -e "${YELLOW}📥 Installing dependencies...${NC}"
pip install --quiet --upgrade pip
pip install --quiet requests pathlib

echo -e "${GREEN}✅ Dependencies ready${NC}"
echo ""

# Run the test
echo -e "${YELLOW}🚀 Running RAG ingestion test...${NC}"
echo ""
python "$PYTHON_SCRIPT"

# Deactivate venv
deactivate
