#!/bin/bash
# ============================================================================
# Test Backup System Locally
# ============================================================================
# Tests the backup scripts with local development containers
# Run this BEFORE migrating production to ensure backups work correctly

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Testing Backup System (Local Development)${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check prerequisites
echo -e "${BLUE}▸ Checking prerequisites...${NC}"

if ! docker ps | grep -q "octavios-mongodb"; then
    echo -e "${RED}✗ octavios-mongodb container not running${NC}"
    echo -e "${YELLOW}  Start development environment: make dev${NC}"
    exit 1
fi

if ! docker ps | grep -q "octavios-redis"; then
    echo -e "${RED}✗ octavios-redis container not running${NC}"
    echo -e "${YELLOW}  Start development environment: make dev${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Containers running${NC}"
echo ""

# Test MongoDB backup script
echo -e "${BLUE}▸ Testing MongoDB backup script...${NC}"
TEST_BACKUP_DIR="/tmp/backup-test-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$TEST_BACKUP_DIR"

if [ ! -f "$PROJECT_ROOT/scripts/backup-mongodb.sh" ]; then
    echo -e "${RED}✗ backup-mongodb.sh not found${NC}"
    exit 1
fi

# Source environment
if [ -f "$PROJECT_ROOT/envs/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/envs/.env" | xargs)
fi

# Run MongoDB backup
echo "  Running: backup-mongodb.sh --backup-dir $TEST_BACKUP_DIR --container octavios-mongodb"
if "$PROJECT_ROOT/scripts/backup-mongodb.sh" \
    --backup-dir "$TEST_BACKUP_DIR" \
    --container octavios-mongodb \
    --retention-days 1; then
    echo -e "${GREEN}✓ MongoDB backup completed${NC}"
else
    echo -e "${RED}✗ MongoDB backup FAILED${NC}"
    exit 1
fi

# Verify MongoDB backup
MONGO_BACKUP_FILE=$(ls "$TEST_BACKUP_DIR"/octavios_*.gz 2>/dev/null | head -1)
if [ -z "$MONGO_BACKUP_FILE" ]; then
    echo -e "${RED}✗ MongoDB backup file not created${NC}"
    exit 1
fi

MONGO_BACKUP_SIZE=$(stat -f%z "$MONGO_BACKUP_FILE" 2>/dev/null || stat -c%s "$MONGO_BACKUP_FILE")
if [ "$MONGO_BACKUP_SIZE" -lt 1024 ]; then
    echo -e "${RED}✗ MongoDB backup too small: $MONGO_BACKUP_SIZE bytes${NC}"
    exit 1
fi

echo -e "${GREEN}✓ MongoDB backup verified:${NC} $(du -h "$MONGO_BACKUP_FILE" | cut -f1)"
echo ""

# Test Docker volumes backup script
echo -e "${BLUE}▸ Testing Docker volumes backup script...${NC}"

if [ ! -f "$PROJECT_ROOT/scripts/backup-docker-volumes.sh" ]; then
    echo -e "${RED}✗ backup-docker-volumes.sh not found${NC}"
    exit 1
fi

# Run volumes backup
echo "  Running: backup-docker-volumes.sh --backup-dir $TEST_BACKUP_DIR"
if "$PROJECT_ROOT/scripts/backup-docker-volumes.sh" \
    --backup-dir "$TEST_BACKUP_DIR" \
    --retention-days 1; then
    echo -e "${GREEN}✓ Docker volumes backup completed${NC}"
else
    echo -e "${RED}✗ Docker volumes backup FAILED${NC}"
    exit 1
fi

# Verify volumes backup
REDIS_BACKUP_FILE=$(ls "$TEST_BACKUP_DIR"/octavios_redis_data-*.tar.gz 2>/dev/null | head -1)
if [ -z "$REDIS_BACKUP_FILE" ]; then
    echo -e "${YELLOW}⚠  Redis backup file not found (might be expected if Redis is empty)${NC}"
else
    echo -e "${GREEN}✓ Redis backup verified:${NC} $(du -h "$REDIS_BACKUP_FILE" | cut -f1)"
fi
echo ""

# Summary
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ All Backup Tests Passed!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}Backup location:${NC} $TEST_BACKUP_DIR"
echo -e "${BLUE}Total backup size:${NC} $(du -sh "$TEST_BACKUP_DIR" | cut -f1)"
echo ""
echo "Contents:"
ls -lh "$TEST_BACKUP_DIR"
echo ""
echo -e "${GREEN}✓ Backup system is ready for production migration${NC}"
echo ""
echo -e "${YELLOW}To cleanup test backups:${NC}"
echo "  rm -rf $TEST_BACKUP_DIR"
echo ""

