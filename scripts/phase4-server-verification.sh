#!/bin/bash
# ============================================================================
# Phase 4: Production Server Preparation - Automated Verification
# ============================================================================
# This script verifies the current state of the production server before
# migration from copilotos to octavios.
#
# Usage:
#   # On production server:
#   cd ~/copilotos-bridge
#   ./scripts/phase4-server-verification.sh
#
# What it does:
#   1. Verifies connection and user context
#   2. Checks current container status
#   3. Analyzes disk space availability
#   4. Documents current configuration
#   5. Generates a pre-migration report
#
# Output:
#   - Console report with all verification results
#   - Files saved to /tmp/pre-migration-verification/

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# Configuration
# ============================================================================
VERIFICATION_DIR="/tmp/pre-migration-verification-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$VERIFICATION_DIR"

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Phase 4: Production Server Verification${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}Verification output:${NC} $VERIFICATION_DIR"
echo ""

# ============================================================================
# 4.1 Connect to Server (Context Verification)
# ============================================================================
echo -e "${BLUE}▸ 4.1 Server Context Verification${NC}"
echo ""

CURRENT_USER=$(whoami)
CURRENT_DIR=$(pwd)
HOSTNAME=$(hostname)

echo "  User:     $CURRENT_USER"
echo "  Hostname: $HOSTNAME"
echo "  Directory: $CURRENT_DIR"

if [ "$CURRENT_USER" != "jf" ]; then
    echo -e "${YELLOW}⚠  Warning: Expected user 'jf', got '$CURRENT_USER'${NC}"
fi

if [[ ! "$CURRENT_DIR" =~ copilotos-bridge ]]; then
    echo -e "${YELLOW}⚠  Warning: Not in copilotos-bridge directory${NC}"
    echo -e "${YELLOW}   Expected: ~/copilotos-bridge${NC}"
    echo -e "${YELLOW}   Current:  $CURRENT_DIR${NC}"
fi

echo ""

# ============================================================================
# 4.2 Verify Current State
# ============================================================================
echo -e "${BLUE}▸ 4.2 Current Container State${NC}"
echo ""

# Count containers
COPILOTOS_CONTAINERS=$(docker ps | grep copilotos-prod | wc -l)
echo "  Copilotos containers running: $COPILOTOS_CONTAINERS"

if [ "$COPILOTOS_CONTAINERS" -eq 0 ]; then
    echo -e "${RED}✗ No copilotos-prod containers found!${NC}"
    echo -e "${YELLOW}  This might be expected if migration already happened${NC}"
else
    echo -e "${GREEN}✓ Found $COPILOTOS_CONTAINERS copilotos-prod containers${NC}"

    # Save container details
    echo "  Saving container details..."
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" | grep copilotos-prod > "$VERIFICATION_DIR/containers-before-migration.txt" 2>/dev/null || true

    # Check each expected container
    echo ""
    echo "  Container health check:"
    for container in copilotos-prod-web copilotos-prod-api copilotos-prod-mongodb copilotos-prod-redis; do
        if docker ps | grep -q "$container"; then
            STATUS=$(docker ps --format "{{.Status}}" --filter "name=$container")
            echo -e "    ${GREEN}✓${NC} $container: $STATUS"
        else
            echo -e "    ${RED}✗${NC} $container: NOT RUNNING"
        fi
    done
fi

echo ""

# Check API health
echo "  API Health Check:"
if curl -sf --max-time 5 http://localhost:8001/api/health > /dev/null 2>&1; then
    HEALTH_STATUS=$(curl -sf http://localhost:8001/api/health | jq -r '.status' 2>/dev/null || echo "unknown")
    echo -e "    ${GREEN}✓${NC} API responding: $HEALTH_STATUS"
    curl -s http://localhost:8001/api/health > "$VERIFICATION_DIR/api-health-before-migration.json" 2>/dev/null || true
else
    echo -e "    ${RED}✗${NC} API not responding on localhost:8001"
fi

# Check Web frontend
echo "  Web Frontend Check:"
if curl -sf --max-time 5 -I http://localhost:3000 > /dev/null 2>&1; then
    WEB_STATUS=$(curl -sf -I http://localhost:3000 | head -1 | cut -d' ' -f2)
    echo -e "    ${GREEN}✓${NC} Web responding: HTTP $WEB_STATUS"
else
    echo -e "    ${RED}✗${NC} Web not responding on localhost:3000"
fi

echo ""

# ============================================================================
# 4.3 Check Disk Space
# ============================================================================
echo -e "${BLUE}▸ 4.3 Disk Space Analysis${NC}"
echo ""

# Root partition
ROOT_SPACE=$(df -h / | tail -1 | awk '{print $4}')
ROOT_PERCENT=$(df -h / | tail -1 | awk '{print $5}')
echo "  / (root):     $ROOT_SPACE available ($ROOT_PERCENT used)"

# Home partition
HOME_SPACE=$(df -h /home | tail -1 | awk '{print $4}')
HOME_PERCENT=$(df -h /home | tail -1 | awk '{print $5}')
echo "  /home:        $HOME_SPACE available ($HOME_PERCENT used)"

# Project directory size
if [ -d ~/copilotos-bridge ]; then
    PROJECT_SIZE=$(du -sh ~/copilotos-bridge 2>/dev/null | cut -f1)
    echo "  Project dir:  $PROJECT_SIZE (~/copilotos-bridge)"
fi

# Docker volumes size
VOLUMES_SIZE=$(du -sh /var/lib/docker/volumes 2>/dev/null | cut -f1 || echo "N/A")
echo "  Docker vols:  $VOLUMES_SIZE (/var/lib/docker/volumes)"

# Check if we have enough space (at least 10GB on /)
ROOT_GB=$(df -BG / | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$ROOT_GB" -lt 10 ]; then
    echo -e "${RED}✗ Warning: Less than 10GB free on root partition${NC}"
    echo -e "${YELLOW}  Consider cleaning up before migration${NC}"
else
    echo -e "${GREEN}✓ Sufficient disk space available${NC}"
fi

# Save disk space report
df -h > "$VERIFICATION_DIR/disk-space-before-migration.txt"
du -sh ~/copilotos-bridge 2>/dev/null >> "$VERIFICATION_DIR/disk-space-before-migration.txt" || true
du -sh /var/lib/docker/volumes 2>/dev/null >> "$VERIFICATION_DIR/disk-space-before-migration.txt" || true

echo ""

# ============================================================================
# 4.4 Document Current Setup
# ============================================================================
echo -e "${BLUE}▸ 4.4 Documenting Current Configuration${NC}"
echo ""

# Docker volumes
echo "  Saving Docker volumes list..."
docker volume ls > "$VERIFICATION_DIR/volumes-before-migration.txt" 2>/dev/null || true
VOLUME_COUNT=$(docker volume ls | grep -c copilotos || echo "0")
echo "    Found $VOLUME_COUNT copilotos volumes"

# Docker images
echo "  Saving Docker images list..."
docker images | grep copilotos > "$VERIFICATION_DIR/images-before-migration.txt" 2>/dev/null || true
IMAGE_COUNT=$(docker images | grep -c copilotos || echo "0")
echo "    Found $IMAGE_COUNT copilotos images"

# Environment variables (safe - no passwords in output)
echo "  Checking environment configuration..."
if [ -f ~/copilotos-bridge/envs/.env.prod ]; then
    echo "    ✓ .env.prod exists"
    # Extract non-sensitive config
    grep -E "^COMPOSE_PROJECT_NAME=|^MONGODB_USER=|^MONGODB_DATABASE=|^OTEL_SERVICE_NAME=" ~/copilotos-bridge/envs/.env.prod > "$VERIFICATION_DIR/env-config-before-migration.txt" 2>/dev/null || true
else
    echo -e "    ${YELLOW}⚠${NC} .env.prod not found"
fi

# Git status
echo "  Checking git repository status..."
cd ~/copilotos-bridge 2>/dev/null || true
if [ -d .git ]; then
    git log -1 --format="%h - %s (%ar)" > "$VERIFICATION_DIR/git-status-before-migration.txt" 2>/dev/null || true
    git branch --show-current >> "$VERIFICATION_DIR/git-status-before-migration.txt" 2>/dev/null || true
    CURRENT_BRANCH=$(git branch --show-current)
    CURRENT_COMMIT=$(git log -1 --format="%h - %s")
    echo "    Branch: $CURRENT_BRANCH"
    echo "    Commit: $CURRENT_COMMIT"
else
    echo -e "    ${YELLOW}⚠${NC} Not a git repository"
fi

echo ""

# ============================================================================
# Summary Report
# ============================================================================
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Verification Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Generate summary
cat > "$VERIFICATION_DIR/SUMMARY.txt" << EOF
Production Server Verification Summary
Generated: $(date)

Server Context:
- User: $CURRENT_USER
- Hostname: $HOSTNAME
- Directory: $CURRENT_DIR

Current State:
- Copilotos containers: $COPILOTOS_CONTAINERS running
- Docker volumes: $VOLUME_COUNT
- Docker images: $IMAGE_COUNT

Disk Space:
- Root partition: $ROOT_SPACE available
- Home partition: $HOME_SPACE available
- Project size: ${PROJECT_SIZE:-N/A}
- Docker volumes: $VOLUMES_SIZE

Configuration Files:
EOF

# List all generated files
echo "  Generated files:"
ls -lh "$VERIFICATION_DIR/" | tail -n +2 | awk '{print "    " $9 " (" $5 ")"}'

echo ""
echo -e "${BLUE}Verification report saved to:${NC}"
echo "  $VERIFICATION_DIR"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Review the verification report above"
echo "  2. Ensure all containers are healthy"
echo "  3. Verify sufficient disk space (>=10GB on /)"
echo "  4. Proceed to Phase 5: Manual Pre-Migration Backup"
echo ""
echo -e "${YELLOW}To view the full report:${NC}"
echo "  cat $VERIFICATION_DIR/SUMMARY.txt"
echo "  ls -lh $VERIFICATION_DIR/"
echo ""
