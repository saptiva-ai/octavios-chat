# MCP Tool Versioning Guide

## Overview

Complete semantic versioning (semver) support for MCP tools with version constraints, deprecation tracking, and automatic resolution.

## Key Features

✅ **Semver Parsing**: MAJOR.MINOR.PATCH validation
✅ **Version Constraints**: ^, ~, >=, <=, >, <, exact
✅ **Versioned Registry**: Multiple versions per tool
✅ **Automatic Resolution**: Latest, caret, tilde constraints
✅ **Deprecation Warnings**: Track deprecated versions
✅ **Breaking Change Detection**: MAJOR version bumps

---

## Quick Start

### 1. Register Multiple Versions

```python
from src.mcp.server import mcp
from src.mcp.versioning import versioned_registry

# Version 1.0.0 - Original implementation
@mcp.tool()
async def audit_file_v1(doc_id: str, policy_id: str = "auto") -> dict:
    """Audit PDF documents (v1 - basic validation)."""
    # Original implementation
    return {"job_id": "...", "findings": [...]}

# Version 1.1.0 - Added enable_grammar flag
@mcp.tool()
async def audit_file_v1_1(
    doc_id: str,
    policy_id: str = "auto",
    enable_grammar: bool = False,  # NEW
) -> dict:
    """Audit PDF documents (v1.1 - added grammar check)."""
    # Enhanced implementation
    return {"job_id": "...", "findings": [...]}

# Version 2.0.0 - Breaking change (new response format)
@mcp.tool()
async def audit_file_v2(
    doc_id: str,
    policy_id: str = "auto",
    enable_grammar: bool = False,
    enable_logo: bool = True,  # NEW
) -> dict:
    """Audit PDF documents (v2 - new response format with scores)."""
    # Breaking change: response now includes compliance_score
    return {
        "job_id": "...",
        "compliance_score": 0.95,  # NEW FIELD
        "findings": [...],
        "recommendations": [...]  # NEW FIELD
    }

# Register all versions
versioned_registry.register("audit_file", "1.0.0", audit_file_v1)
versioned_registry.register("audit_file", "1.1.0", audit_file_v1_1)
versioned_registry.register("audit_file", "2.0.0", audit_file_v2)

# Mark old versions as deprecated
versioned_registry.deprecate_version("audit_file", "1.0.0", "1.1.0")
```

---

## Frontend Usage

### TypeScript SDK

```typescript
import { mcpClient } from '@/lib/mcp/client';

// 1. List all versions
const tools = await mcpClient.listTools();
const auditTool = tools.find(t => t.name === "audit_file");

console.log(auditTool.version);             // "2.0.0" (latest)
console.log(auditTool.available_versions);  // ["2.0.0", "1.1.0", "1.0.0"]

// 2. Invoke with exact version
const result = await mcpClient.invokeTool({
  tool: "audit_file",
  version: "1.1.0",  // Use specific version
  payload: {
    doc_id: "doc_123",
    policy_id: "414-std",
  }
});

// 3. Invoke with caret constraint (^1.0.0 = any 1.x.x >= 1.0.0)
const result = await mcpClient.invokeTool({
  tool: "audit_file",
  version: "^1.0.0",  // Resolves to 1.1.0 (highest 1.x.x)
  payload: { doc_id: "doc_123" }
});

// 4. Invoke with tilde constraint (~1.0.0 = any 1.0.x >= 1.0.0)
const result = await mcpClient.invokeTool({
  tool: "audit_file",
  version: "~1.0.0",  // Resolves to 1.0.0 (only patch updates)
  payload: { doc_id: "doc_123" }
});

// 5. Invoke latest (no version specified)
const result = await mcpClient.invokeTool({
  tool: "audit_file",
  // No version = latest (2.0.0)
  payload: { doc_id: "doc_123" }
});
```

---

## Version Constraint Syntax

### Exact Version
```
"1.2.3"  →  Exactly 1.2.3
```

### Caret (^) - Compatible Updates
```
"^1.2.3"  →  >=1.2.3 and <2.0.0
             Allows: 1.2.3, 1.2.4, 1.5.0, 1.9.9
             Blocks: 2.0.0, 0.9.0
```

**Use case**: "I want bug fixes and new features, but no breaking changes"

### Tilde (~) - Patch Updates Only
```
"~1.2.3"  →  >=1.2.3 and <1.3.0
             Allows: 1.2.3, 1.2.4, 1.2.10
             Blocks: 1.3.0, 2.0.0
```

**Use case**: "I only want bug fixes, no new features"

### Comparison Operators
```
">=1.2.3"  →  1.2.3 or higher
"<=1.2.3"  →  1.2.3 or lower
">1.2.3"   →  Higher than 1.2.3
"<1.2.3"   →  Lower than 1.2.3
```

---

## Semantic Versioning Rules

### MAJOR.MINOR.PATCH

- **MAJOR**: Incompatible API changes (breaking)
  - Change response structure
  - Remove required fields
  - Change parameter types
  - Example: `1.5.0 → 2.0.0`

- **MINOR**: Backwards-compatible additions
  - Add optional parameters
  - Add new fields to response
  - Add new capabilities
  - Example: `1.5.0 → 1.6.0`

- **PATCH**: Backwards-compatible bug fixes
  - Fix bugs
  - Performance improvements
  - Documentation updates
  - Example: `1.5.0 → 1.5.1`

---

## Backend API Examples

### POST /api/mcp/invoke

**Request with version constraint:**
```json
{
  "tool": "audit_file",
  "version": "^1.0.0",
  "payload": {
    "doc_id": "doc_123",
    "policy_id": "auto"
  }
}
```

**Response:**
```json
{
  "success": true,
  "tool": "audit_file",
  "version": "1.1.0",  ← Resolved version
  "result": {...},
  "metadata": {
    "user_id": "user_123",
    "version_constraint": "^1.0.0"  ← Original request
  },
  "invocation_id": "inv_456",
  "duration_ms": 1234.5
}
```

### GET /api/mcp/tools

**Response with versions:**
```json
[
  {
    "name": "audit_file",
    "version": "2.0.0",
    "available_versions": ["2.0.0", "1.1.0", "1.0.0"],
    "display_name": "Audit File",
    "description": "Validate PDF documents...",
    "category": "compliance",
    ...
  }
]
```

---

## Migration Guide

### Scenario: Breaking Change in audit_file

**Before (v1.x.x):**
```json
{
  "job_id": "job_123",
  "findings": [...]
}
```

**After (v2.0.0):**
```json
{
  "job_id": "job_123",
  "compliance_score": 0.95,
  "findings": [...],
  "recommendations": [...]
}
```

### Step 1: Deploy v2.0.0 alongside v1.x.x

```python
# Both versions coexist
versioned_registry.register("audit_file", "1.1.0", audit_file_v1_1)
versioned_registry.register("audit_file", "2.0.0", audit_file_v2)
```

### Step 2: Deprecate old version

```python
versioned_registry.deprecate_version("audit_file", "1.1.0", "2.0.0")
```

- Logs warning when v1.1.0 is used
- Clients see deprecation notice

### Step 3: Migrate clients gradually

```typescript
// Old clients (pin to v1.x.x)
invokeTool({ tool: "audit_file", version: "^1.0.0", ... })

// New clients (use v2)
invokeTool({ tool: "audit_file", version: "^2.0.0", ... })
// or
invokeTool({ tool: "audit_file", ... })  // Latest
```

### Step 4: Remove v1.x.x after migration window

```python
# After 3 months, remove v1.x.x
# Only v2.0.0 remains
```

---

## Best Practices

### 1. Always Register New Versions

```python
# ❌ DON'T: Overwrite existing tool
@mcp.tool()
async def audit_file(...):
    pass

# ✅ DO: Register with version
versioned_registry.register("audit_file", "1.2.0", audit_file_v1_2)
```

### 2. Use Caret (^) for Client Dependencies

```typescript
// ✅ GOOD: Allows bug fixes and features
{ version: "^1.0.0" }

// ⚠️ RISKY: Pinned to exact version (no bug fixes)
{ version: "1.0.0" }

// ❌ BAD: Allows breaking changes
{ version: ">=1.0.0" }
```

### 3. Deprecate Before Removing

```python
# Month 1: Deploy v2, deprecate v1
versioned_registry.deprecate_version("audit_file", "1.0.0", "2.0.0")

# Month 2-3: Migration window (warnings logged)

# Month 4: Remove v1
# (Don't register v1)
```

### 4. Document Breaking Changes

```python
@mcp.tool()
async def audit_file_v2(...) -> dict:
    """
    Audit PDF documents (v2).

    Breaking changes from v1:
    - Response now includes `compliance_score` (float)
    - Added `recommendations` array
    - `findings` structure changed (added `confidence` field)

    Migration guide: https://docs.octavios.com/audit-file-v2
    """
```

---

## Error Handling

### Version Not Found

```json
{
  "success": false,
  "tool": "audit_file",
  "version": "^3.0.0",
  "error": {
    "code": "TOOL_NOT_FOUND",
    "message": "No version of 'audit_file' matches constraint '^3.0.0'",
    "details": {
      "available_versions": ["2.0.0", "1.1.0", "1.0.0"]
    }
  }
}
```

### Deprecation Warning (Logs Only)

```
[WARNING] Using deprecated tool version
  tool=audit_file
  version=1.0.0
  replacement=1.1.0
```

---

## Testing

```python
import pytest
from src.mcp.versioning import versioned_registry

def test_version_resolution():
    """Test version constraint resolution."""

    # Register versions
    versioned_registry.register("test_tool", "1.0.0", tool_v1)
    versioned_registry.register("test_tool", "1.5.0", tool_v1_5)
    versioned_registry.register("test_tool", "2.0.0", tool_v2)

    # Resolve caret
    version, tool_func = versioned_registry.resolve("test_tool", "^1.0.0")
    assert version == "1.5.0"  # Highest 1.x.x

    # Resolve tilde
    version, tool_func = versioned_registry.resolve("test_tool", "~1.0.0")
    assert version == "1.0.0"  # Only 1.0.x

    # Resolve latest
    version, tool_func = versioned_registry.resolve("test_tool")
    assert version == "2.0.0"
```

---

## Integration with FastAPI

```python
from src.mcp.fastapi_adapter import MCPFastAPIAdapter

# Adapter automatically integrates with versioned_registry
adapter = MCPFastAPIAdapter(
    mcp_server=mcp_server,
    auth_dependency=get_current_user,
)

# POST /api/mcp/invoke now supports version field
# GET /api/mcp/tools now includes available_versions
```

---

## Monitoring

### Prometheus Metrics

```python
# Track version usage
mcp_tool_version_invocations_total{tool="audit_file",version="1.1.0"} 234
mcp_tool_version_invocations_total{tool="audit_file",version="2.0.0"} 1567

# Track deprecated version usage
mcp_deprecated_version_invocations_total{tool="audit_file",version="1.0.0"} 12
```

### Structured Logs

```json
{
  "event": "tool_version_resolved",
  "tool": "audit_file",
  "constraint": "^1.0.0",
  "resolved": "1.1.0",
  "user_id": "user_123",
  "timestamp": "2025-01-11T..."
}
```

---

## Related Files

- `apps/api/src/mcp/versioning.py` - Core versioning logic
- `apps/api/src/mcp/fastapi_adapter.py` - REST API integration
- `apps/api/tests/mcp/test_versioning.py` - Comprehensive tests
- `apps/api/src/mcp/protocol.py` - Type definitions

---

## FAQ

**Q: Can I have multiple major versions simultaneously?**
A: Yes! Register v1.x.x and v2.x.x side-by-side.

**Q: What happens if I don't specify a version?**
A: The latest version is used automatically.

**Q: How do I test new versions without affecting production?**
A: Use exact versions during testing (`"2.0.0"`), then switch to caret (`"^2.0.0"`) for production.

**Q: Can I rollback a version?**
A: Yes, just invoke with the older version constraint (`"^1.0.0"`).

**Q: How long should I maintain old versions?**
A: Minimum 3 months after deprecation notice for gradual migration.

---

## Completion Status

✅ **Priority #3: Tool Versioning - COMPLETED**
- Semantic version parsing and validation
- Version constraint matching (^, ~, >=, etc.)
- Versioned tool registry
- Automatic version resolution
- Deprecation tracking
- FastAPI integration
- Comprehensive test coverage
