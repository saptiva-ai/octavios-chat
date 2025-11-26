#!/bin/bash
# ==============================================================================
# Cleanup Script: Remove COPILOTO_414 Audit Files from Core
# ==============================================================================
# This script removes audit-related files from the Core (apps/api) after
# they have been migrated to plugins/capital414-private/
#
# Usage:
#   ./scripts/cleanup_audit_from_core.sh [--dry-run]
#
# Options:
#   --dry-run    Show what would be deleted without actually deleting
# ==============================================================================

set -e

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "DRY RUN MODE - No files will be deleted"
fi

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "COPILOTO_414 Core Cleanup Script"
echo "=============================================="

# Files to delete from Core
AUDIT_FILES=(
    # Domain handlers
    "apps/api/src/domain/audit_handler.py"

    # MCP Tools
    "apps/api/src/mcp/tools/audit_file.py"
    "apps/api/src/services/tools/audit_file_tool.py"

    # Validation Coordinator
    "apps/api/src/services/validation_coordinator.py"

    # 8 Auditors
    "apps/api/src/services/compliance_auditor.py"
    "apps/api/src/services/format_auditor.py"
    "apps/api/src/services/typography_auditor.py"
    "apps/api/src/services/grammar_auditor.py"
    "apps/api/src/services/logo_auditor.py"
    "apps/api/src/services/color_auditor.py"
    "apps/api/src/services/color_palette_auditor.py"
    "apps/api/src/services/entity_consistency_auditor.py"
    "apps/api/src/services/semantic_consistency_auditor.py"

    # Support services
    "apps/api/src/services/policy_manager.py"
    "apps/api/src/services/report_generator.py"
    "apps/api/src/services/summary_formatter.py"
    "apps/api/src/services/audit_utils.py"

    # Schemas
    "apps/api/src/schemas/audit.py"
    "apps/api/src/schemas/audit_message.py"

    # Config (move to plugin, don't delete - they may be referenced)
    # "apps/api/src/config/compliance.yaml"
    # "apps/api/src/config/policies.yaml"

    # Assets
    # "apps/api/assets/logo_template.png"  # Keep for backward compatibility
)

# Models to modify (don't delete, just note they need updating)
MODELS_TO_UPDATE=(
    "apps/api/src/models/validation_report.py"
)

echo ""
echo -e "${YELLOW}Files to be DELETED:${NC}"
echo "----------------------------------------"

for file in "${AUDIT_FILES[@]}"; do
    if [[ -f "$file" ]]; then
        echo -e "${RED}  - $file${NC}"
        if [[ "$DRY_RUN" == false ]]; then
            rm "$file"
        fi
    else
        echo -e "  - $file (not found, skipping)"
    fi
done

echo ""
echo -e "${YELLOW}Files to UPDATE (remove imports):${NC}"
echo "----------------------------------------"
for file in "${MODELS_TO_UPDATE[@]}"; do
    echo -e "${GREEN}  - $file${NC}"
done

echo ""
echo "=============================================="
if [[ "$DRY_RUN" == true ]]; then
    echo -e "${YELLOW}DRY RUN COMPLETE - No files were deleted${NC}"
    echo "Run without --dry-run to actually delete files"
else
    echo -e "${GREEN}CLEANUP COMPLETE${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Update apps/api/src/models/__init__.py to remove ValidationReport if needed"
    echo "2. Update any routers that import audit functions"
    echo "3. Run 'make test-api' to verify no broken imports"
    echo "4. Commit changes with message: 'refactor: extract COPILOTO_414 to plugins/capital414-private'"
fi
echo "=============================================="
