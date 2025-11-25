#!/bin/bash
################################################################################
# Octavius 2.0 - Server Cleanup & Maintenance Script
#
# Purpose: Automated cleanup of Docker resources, old backups, and logs
#
# Usage:
#   ./scripts/maintenance/cleanup-server.sh [--dry-run] [--aggressive]
#
# Options:
#   --dry-run      Show what would be deleted without actually deleting
#   --aggressive   Also remove stopped containers and networks (use carefully!)
#
# Safety:
#   - Preserves running containers
#   - Keeps last 7 days of logs
#   - Preserves current docker-compose.yml
#
################################################################################

set -e

# Colors
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DRY_RUN=false
AGGRESSIVE=false
LOG_RETENTION_DAYS=7
BACKUP_RETENTION_DAYS=30

# Parse arguments
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --aggressive)
            AGGRESSIVE=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $arg${NC}"
            echo "Usage: $0 [--dry-run] [--aggressive]"
            exit 1
            ;;
    esac
done

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}🔍 DRY RUN MODE - No changes will be made${NC}"
fi

echo -e "${BLUE}🧹 Octavius 2.0 Server Cleanup${NC}"
echo "================================"

# =============================================================================
# FUNCTION: Execute or dry-run command
# =============================================================================
run_command() {
    local description=$1
    shift
    local command="$@"

    echo -e "${BLUE}→ ${description}${NC}"

    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}  [DRY RUN] Would execute: ${command}${NC}"
    else
        echo "  Executing: ${command}"
        eval "$command"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}  ✓ Success${NC}"
        else
            echo -e "${RED}  ✗ Failed (continuing...)${NC}"
        fi
    fi
    echo ""
}

# =============================================================================
# SECTION 1: Docker Cleanup
# =============================================================================
echo -e "${BLUE}📦 Docker Cleanup${NC}"
echo "----------------"

# Remove unused images
run_command "Remove dangling Docker images" \
    "docker image prune -f"

# Remove build cache
run_command "Remove Docker build cache" \
    "docker builder prune -f"

# Remove unused volumes (SAFE: only removes volumes not attached to containers)
run_command "Remove unused Docker volumes" \
    "docker volume prune -f"

if [ "$AGGRESSIVE" = true ]; then
    echo -e "${YELLOW}⚠️  Aggressive mode enabled${NC}"

    # Remove stopped containers
    run_command "Remove all stopped containers" \
        "docker container prune -f"

    # Remove unused networks
    run_command "Remove unused Docker networks" \
        "docker network prune -f"
fi

# Show disk space saved
echo -e "${GREEN}Docker system summary:${NC}"
if [ "$DRY_RUN" = false ]; then
    docker system df
fi
echo ""

# =============================================================================
# SECTION 2: Backup Cleanup
# =============================================================================
echo -e "${BLUE}🗄️  Backup Cleanup${NC}"
echo "----------------"

# Remove old docker-compose.yml backups
if [ -d "infra" ]; then
    run_command "Remove docker-compose.yml backups" \
        "find infra -name 'docker-compose.yml.backup-*' -type f -delete"
fi

# Remove old deployment backups
if [ -d "backups" ]; then
    run_command "Remove deployment backups older than ${BACKUP_RETENTION_DAYS} days" \
        "find backups -name '*.tar.gz' -type f -mtime +${BACKUP_RETENTION_DAYS} -delete 2>/dev/null || true"
fi

echo ""

# =============================================================================
# SECTION 3: Log Cleanup
# =============================================================================
echo -e "${BLUE}📝 Log Cleanup${NC}"
echo "-------------"

# Clean application logs
if [ -d "apps/api/logs" ]; then
    run_command "Remove API logs older than ${LOG_RETENTION_DAYS} days" \
        "find apps/api/logs -name '*.log' -type f -mtime +${LOG_RETENTION_DAYS} -delete 2>/dev/null || true"
fi

# Clean pytest cache
if [ -d "apps/api/.pytest_cache" ]; then
    run_command "Remove pytest cache" \
        "rm -rf apps/api/.pytest_cache"
fi

# Clean Python cache
if [ -d "apps/api/__pycache__" ]; then
    run_command "Remove Python cache directories" \
        "find apps/api -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true"
fi

# Clean coverage reports
if [ -d "apps/api/htmlcov" ]; then
    run_command "Remove coverage HTML reports" \
        "rm -rf apps/api/htmlcov"
fi

echo ""

# =============================================================================
# SECTION 4: Next.js Cleanup
# =============================================================================
echo -e "${BLUE}⚛️  Next.js Cleanup${NC}"
echo "----------------"

if [ -d "apps/web/.next" ]; then
    run_command "Remove Next.js build cache" \
        "rm -rf apps/web/.next/cache"
fi

echo ""

# =============================================================================
# SECTION 5: Temporary Files
# =============================================================================
echo -e "${BLUE}🗑️  Temporary Files${NC}"
echo "-----------------"

run_command "Remove temporary files" \
    "find . -name '*.tmp' -o -name '*.temp' -o -name '.DS_Store' -type f -delete 2>/dev/null || true"

echo ""

# =============================================================================
# SECTION 6: Final Report
# =============================================================================
echo -e "${GREEN}✓ Cleanup Complete${NC}"
echo "==================="

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}This was a dry run. Run without --dry-run to actually clean up.${NC}"
else
    echo -e "${GREEN}Server cleanup completed successfully!${NC}"
    echo ""
    echo "Disk usage after cleanup:"
    df -h / | tail -1
fi

echo ""
echo "Next steps:"
echo "  1. Review Docker logs: docker compose -f infra/docker-compose.yml logs --tail=100"
echo "  2. Check service health: make verify"
echo "  3. Monitor disk space: df -h"

# Optional: Show largest directories
echo ""
echo -e "${BLUE}Top 10 largest directories in project:${NC}"
if command -v du &> /dev/null; then
    du -sh * 2>/dev/null | sort -rh | head -10 || echo "Unable to calculate directory sizes"
fi
