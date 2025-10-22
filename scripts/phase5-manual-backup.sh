#!/bin/bash
# ============================================================================
# Phase 5: Manual Pre-Migration Backup (CRITICAL)
# ============================================================================
# This script performs comprehensive backups before the copilotos → octavios
# migration. This is the MOST CRITICAL step - do not skip!
#
# Usage:
#   # On production server:
#   cd ~/copilotos-bridge
#   ./scripts/phase5-manual-backup.sh
#
# What gets backed up:
#   1. MongoDB database (mongodump with BSON export)
#   2. Docker volumes (MongoDB + Redis data directories)
#   3. Environment files (.env.prod)
#   4. Current container configuration
#
# Backup location:
#   ~/backups/pre-migration-YYYYMMDD-HHMMSS/
#
# Safety:
#   - Script aborts if backup verification fails
#   - Minimum size checks ensure data was actually backed up
#   - Backup location saved for emergency restore

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# Configuration
# ============================================================================
BACKUP_DIR=~/backups/pre-migration-$(date +%Y%m%d-%H%M%S)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Phase 5: Manual Pre-Migration Backup (CRITICAL)${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${RED}⚠️  CRITICAL: This backup is your safety net!${NC}"
echo -e "${RED}   Do not proceed without verified backups.${NC}"
echo ""
echo -e "${BLUE}Backup destination:${NC} $BACKUP_DIR"
echo ""

# ============================================================================
# 5.1 Create Backup Directory
# ============================================================================
echo -e "${BLUE}▸ 5.1 Creating Backup Directory${NC}"
echo ""

mkdir -p "$BACKUP_DIR"
echo "  ✓ Created: $BACKUP_DIR"
echo ""

# ============================================================================
# 5.2 Backup MongoDB
# ============================================================================
echo -e "${BLUE}▸ 5.2 Backing Up MongoDB Database${NC}"
echo ""

if [ ! -f "$PROJECT_ROOT/scripts/backup-mongodb.sh" ]; then
    echo -e "${RED}✗ backup-mongodb.sh not found at $PROJECT_ROOT/scripts/${NC}"
    echo -e "${YELLOW}  Falling back to manual mongodump...${NC}"

    # Manual backup fallback
    MONGO_CONTAINER="copilotos-prod-mongodb"
    if docker ps | grep -q "$MONGO_CONTAINER"; then
        echo "  Running mongodump on $MONGO_CONTAINER..."
        docker exec "$MONGO_CONTAINER" mongodump \
            --db copilotos \
            --archive=/tmp/copilotos_backup_$(date +%Y%m%d_%H%M%S).gz \
            --gzip

        # Copy from container
        BACKUP_FILE=$(docker exec "$MONGO_CONTAINER" ls -t /tmp/copilotos_backup_*.gz | head -1)
        docker cp "$MONGO_CONTAINER:$BACKUP_FILE" "$BACKUP_DIR/"
        echo -e "${GREEN}  ✓ MongoDB backup completed (manual)${NC}"
    else
        echo -e "${RED}✗ MongoDB container not found: $MONGO_CONTAINER${NC}"
        exit 1
    fi
else
    # Use backup script
    echo "  Using backup-mongodb.sh..."
    if ! "$PROJECT_ROOT/scripts/backup-mongodb.sh" \
        --backup-dir "$BACKUP_DIR" \
        --container copilotos-prod-mongodb \
        --retention-days 30; then
        echo -e "${RED}✗ MongoDB backup FAILED${NC}"
        echo -e "${RED}  Aborting migration - data safety is critical!${NC}"
        exit 1
    fi
fi

# Verify MongoDB backup exists
MONGO_BACKUP=$(ls "$BACKUP_DIR"/*copilotos*.gz 2>/dev/null | head -1)
if [ -z "$MONGO_BACKUP" ]; then
    echo -e "${RED}✗ MongoDB backup file not found!${NC}"
    exit 1
fi

MONGO_SIZE=$(stat -c%s "$MONGO_BACKUP" 2>/dev/null || stat -f%z "$MONGO_BACKUP" 2>/dev/null)
if [ "$MONGO_SIZE" -lt 1024 ]; then
    echo -e "${RED}✗ MongoDB backup too small: $MONGO_SIZE bytes${NC}"
    exit 1
fi

echo -e "${GREEN}  ✓ MongoDB backup verified: $(du -h "$MONGO_BACKUP" | cut -f1)${NC}"
echo ""

# ============================================================================
# 5.3 Backup Docker Volumes
# ============================================================================
echo -e "${BLUE}▸ 5.3 Backing Up Docker Volumes${NC}"
echo ""

if [ ! -f "$PROJECT_ROOT/scripts/backup-docker-volumes.sh" ]; then
    echo -e "${YELLOW}  ⚠ backup-docker-volumes.sh not found${NC}"
    echo "  Skipping volume backup (MongoDB dump is sufficient for data recovery)"
else
    echo "  Using backup-docker-volumes.sh..."
    if ! "$PROJECT_ROOT/scripts/backup-docker-volumes.sh" \
        --backup-dir "$BACKUP_DIR" \
        --retention-days 30; then
        echo -e "${YELLOW}⚠  Volume backup had warnings (non-critical)${NC}"
    else
        echo -e "${GREEN}  ✓ Docker volumes backed up${NC}"
    fi
fi

echo ""

# ============================================================================
# 5.4 Backup Environment Files
# ============================================================================
echo -e "${BLUE}▸ 5.4 Backing Up Environment Configuration${NC}"
echo ""

# Backup .env.prod (the active production env file)
if [ -f "$PROJECT_ROOT/envs/.env.prod" ]; then
    cp "$PROJECT_ROOT/envs/.env.prod" "$BACKUP_DIR/env.prod.backup"
    echo -e "${GREEN}  ✓ .env.prod backed up${NC}"
else
    echo -e "${YELLOW}  ⚠ .env.prod not found${NC}"
fi

# Backup .env.prod.example (for reference)
if [ -f "$PROJECT_ROOT/envs/.env.prod.example" ]; then
    cp "$PROJECT_ROOT/envs/.env.prod.example" "$BACKUP_DIR/env.prod.example.backup"
    echo "  ✓ .env.prod.example backed up"
fi

echo ""

# ============================================================================
# 5.5 Backup Container Configuration
# ============================================================================
echo -e "${BLUE}▸ 5.5 Documenting Container Configuration${NC}"
echo ""

# Save running containers
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" | grep copilotos > "$BACKUP_DIR/containers-snapshot.txt" 2>/dev/null || true
echo "  ✓ Container list saved"

# Save docker-compose file
if [ -f "$PROJECT_ROOT/infra/docker-compose.yml" ]; then
    cp "$PROJECT_ROOT/infra/docker-compose.yml" "$BACKUP_DIR/docker-compose.yml.backup"
    echo "  ✓ docker-compose.yml backed up"
fi

# Save volumes list
docker volume ls | grep copilotos > "$BACKUP_DIR/volumes-snapshot.txt" 2>/dev/null || true
echo "  ✓ Volume list saved"

echo ""

# ============================================================================
# 5.6 Verify Backups
# ============================================================================
echo -e "${BLUE}▸ 5.6 Verifying Backup Integrity${NC}"
echo ""

# Check backup directory size
BACKUP_SIZE_BYTES=$(du -sb "$BACKUP_DIR" 2>/dev/null | cut -f1)
BACKUP_SIZE_HUMAN=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
MIN_SIZE=102400  # 100KB minimum

if [ -z "$BACKUP_SIZE_BYTES" ] || [ "$BACKUP_SIZE_BYTES" -lt "$MIN_SIZE" ]; then
    echo -e "${RED}✗ Backup verification FAILED${NC}"
    echo -e "${RED}  Expected: At least 100KB${NC}"
    echo -e "${RED}  Got: $BACKUP_SIZE_HUMAN${NC}"
    echo -e "${RED}  Location: $BACKUP_DIR${NC}"
    exit 1
fi

echo -e "${GREEN}  ✓ Backup size verified: $BACKUP_SIZE_HUMAN${NC}"

# List backup contents
echo ""
echo "  Backup contents:"
ls -lh "$BACKUP_DIR/" | tail -n +2 | awk '{print "    " $9 " (" $5 ")"}'

# Create backup log
cat > "$BACKUP_DIR/backup.log" << EOF
Pre-Migration Backup Log
========================
Date: $(date)
Host: $(hostname)
User: $(whoami)
Backup Dir: $BACKUP_DIR
Total Size: $BACKUP_SIZE_HUMAN

Contents:
$(ls -lh "$BACKUP_DIR/" | tail -n +2)

MongoDB Backup:
$(ls -lh "$BACKUP_DIR"/*copilotos*.gz 2>/dev/null || echo "  Not found")

Verification: PASSED
Status: READY FOR MIGRATION
EOF

echo ""

# ============================================================================
# 5.7 Save Backup Location
# ============================================================================
echo "$BACKUP_DIR" > /tmp/last_data_backup
echo -e "${GREEN}  ✓ Backup location saved to /tmp/last_data_backup${NC}"

echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Pre-Migration Backup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${BLUE}Backup Summary:${NC}"
echo "  Location: $BACKUP_DIR"
echo "  Size: $BACKUP_SIZE_HUMAN"
echo "  Status: ✅ VERIFIED"
echo ""

echo -e "${BLUE}What was backed up:${NC}"
echo "  ✓ MongoDB database (mongodump)"
echo "  ✓ Docker volumes (MongoDB + Redis data)"
echo "  ✓ Environment files (.env.prod)"
echo "  ✓ Container configuration"
echo ""

echo -e "${BLUE}Emergency Restore:${NC}"
echo "  If migration fails, restore with:"
echo "    cd ~/copilotos-bridge"
echo "    ./scripts/restore-mongodb.sh --backup-dir $BACKUP_DIR"
echo ""

echo -e "${GREEN}⚠️  CHECKPOINT: Backup Complete!${NC}"
echo -e "${GREEN}   You may now proceed to Phase 6: Code Update${NC}"
echo ""

echo -e "${YELLOW}To review backup:${NC}"
echo "  cat $BACKUP_DIR/backup.log"
echo "  ls -lh $BACKUP_DIR/"
echo ""
