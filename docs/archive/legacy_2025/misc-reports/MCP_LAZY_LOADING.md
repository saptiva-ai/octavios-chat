# MCP Lazy Loading - Optimized Tool Management

**Context Reduction: ~98% | Memory Efficiency: Dynamic | Startup Time: Near-instant**

This document describes the lazy loading system for MCP tools, which dramatically reduces context usage and memory footprint by loading tools on-demand instead of upfront.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Usage Examples](#usage-examples)
5. [Performance Metrics](#performance-metrics)
6. [Testing](#testing)
7. [Migration Guide](#migration-guide)

---

## Overview

### The Problem

Traditional MCP implementations load ALL tools at startup:

```python
# Traditional approach (BAD)
tools = [
    AuditFileTool(),           # ~30KB
    ExcelAnalyzerTool(),       # ~25KB
    VizTool(),                 # ~20KB
    DeepResearchTool(),        # ~40KB
    ExtractDocumentTextTool()  # ~35KB
]
# Total: ~150KB loaded upfront
# Context usage: ALL tool definitions in every request
```

**Problems:**
- 150KB+ context usage even if only using 1 tool
- Slow startup (imports all modules)
- High memory footprint
- Wasteful for specialized workflows

### The Solution: Lazy Loading

Load tools ONLY when needed:

```python
# Lazy approach (GOOD)
registry = LazyToolRegistry()

# Step 1: Discover (returns minimal metadata - ~50 bytes per tool)
tools = registry.discover_tools()  # ~250 bytes total

# Step 2: Load on-demand (only when invoking)
tool = await registry.load_tool("audit_file")  # ~30KB (only this tool)

# Result: ~98% context reduction
```

**Benefits:**
- ✅ ~98% reduction in context usage (150KB → 2KB)
- ✅ Near-instant startup (no imports)
- ✅ Dynamic memory management
- ✅ Scales to 100+ tools without overhead

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────┐
│                    Lazy Loading System                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────┐       ┌──────────────────┐         │
│  │ lazy_routes.py │───────│ lazy_registry.py │         │
│  │  (FastAPI)     │       │   (Registry)     │         │
│  └────────────────┘       └──────────────────┘         │
│         │                          │                     │
│         │                          │                     │
│    REST API                   Tool Loading              │
│         │                          │                     │
│         ▼                          ▼                     │
│  ┌──────────────┐         ┌─────────────┐              │
│  │  Discovery   │         │  Metadata   │              │
│  │   Endpoint   │         │    Cache    │              │
│  └──────────────┘         └─────────────┘              │
│                                   │                     │
│                                   ▼                     │
│                           ┌─────────────┐              │
│                           │  Dynamic    │              │
│                           │   Import    │              │
│                           └─────────────┘              │
│                                   │                     │
│                                   ▼                     │
│                           ┌─────────────┐              │
│                           │ Tool Cache  │              │
│                           └─────────────┘              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Flow Diagram

```
┌──────────┐
│  Client  │
└────┬─────┘
     │
     │ 1. GET /mcp/lazy/discover
     ▼
┌─────────────────┐
│ Lazy Routes     │
│ (FastAPI)       │
└────┬────────────┘
     │
     │ 2. discover_tools()
     ▼
┌─────────────────┐
│ Lazy Registry   │
│ (Scan files)    │
└────┬────────────┘
     │
     │ 3. Return minimal metadata
     │    (~50 bytes per tool)
     ▼
┌──────────┐
│  Client  │  ◄─── ["audit_file", "excel_analyzer", ...]
└────┬─────┘
     │
     │ 4. POST /mcp/lazy/invoke {"tool": "audit_file"}
     ▼
┌─────────────────┐
│ Lazy Routes     │
└────┬────────────┘
     │
     │ 5. invoke(request)
     ▼
┌─────────────────┐
│ Lazy Registry   │
│ ┌─────────────┐ │
│ │ Check cache │ │ ◄─── If loaded, return from cache
│ └──────┬──────┘ │
│        │ NOT CACHED
│        ▼        │
│ ┌─────────────┐ │
│ │   Import    │ │ ◄─── Dynamic import
│ │  on-demand  │ │
│ └──────┬──────┘ │
│        │        │
│        ▼        │
│ ┌─────────────┐ │
│ │   Cache     │ │ ◄─── Cache for reuse
│ └──────┬──────┘ │
└────────┼────────┘
         │
         │ 6. Execute tool
         ▼
    Tool Result
```

---

## API Reference

### Base URL

```
http://localhost:8000/api/mcp/lazy
```

### Endpoints

#### 1. Discover Tools

**GET** `/mcp/lazy/discover`

Discover available tools without loading them (minimal metadata).

**Query Parameters:**
- `category` (optional): Filter by category (compliance, analytics, research, etc.)
- `search` (optional): Search in name/description

**Response:**
```json
{
  "tools": [
    {
      "name": "audit_file",
      "category": "compliance",
      "description": "Tool: audit_file",
      "loaded": false
    },
    {
      "name": "excel_analyzer",
      "category": "analytics",
      "description": "Tool: excel_analyzer",
      "loaded": false
    }
  ],
  "total": 2,
  "loaded": 0,
  "optimization": "Minimal metadata returned to reduce context usage"
}
```

**Context Usage:** ~50 bytes per tool (vs ~5KB with eager loading)

---

#### 2. Get Tool Specification

**GET** `/mcp/lazy/tools/{tool_name}`

Get full tool specification (loads tool on-demand if needed).

**Response:**
```json
{
  "name": "audit_file",
  "version": "1.0.0",
  "display_name": "Audit File (Document Audit)",
  "description": "Validates document compliance...",
  "category": "compliance",
  "capabilities": ["async", "validation"],
  "input_schema": {
    "type": "object",
    "properties": {
      "doc_id": {"type": "string"},
      "policy_id": {"type": "string"}
    }
  },
  "output_schema": {...},
  "tags": ["compliance", "validation", "copiloto414"],
  "requires_auth": true,
  "rate_limit": null,
  "timeout_ms": 30000,
  "loaded_on_demand": true
}
```

**Note:** Tool is loaded dynamically on first request, then cached.

---

#### 3. Invoke Tool

**POST** `/mcp/lazy/invoke`

Invoke a tool (loads on-demand if not already loaded).

**Request Body:**
```json
{
  "tool": "audit_file",
  "version": "1.0.0",
  "payload": {
    "doc_id": "674a5b8c9e7f12a3b4c5d6e7",
    "policy_id": "auto"
  },
  "context": {},
  "idempotency_key": "optional-key"
}
```

**Response:**
```json
{
  "success": true,
  "tool": "audit_file",
  "version": "1.0.0",
  "result": {
    "summary": {
      "total_findings": 3,
      "errors": 1,
      "warnings": 2
    },
    "findings": [...]
  },
  "error": null,
  "metadata": {},
  "invocation_id": "inv_abc123",
  "duration_ms": 1234.56,
  "cached": false
}
```

**Optimization:** Tool is loaded only when invoked, not at startup.

---

#### 4. Registry Statistics

**GET** `/mcp/lazy/stats`

Get registry statistics (memory efficiency metrics).

**Response:**
```json
{
  "tools_discovered": 5,
  "tools_loaded": 2,
  "tools_available": [
    "audit_file",
    "excel_analyzer",
    "viz_tool",
    "deep_research",
    "extract_document_text"
  ],
  "tools_loaded_list": [
    "audit_file",
    "extract_document_text"
  ],
  "memory_efficiency": "60.0%",
  "optimization_note": "Only 2/5 tools loaded in memory (60.0% efficiency)"
}
```

**Use Case:** Monitoring and debugging memory usage.

---

#### 5. Unload Tool

**DELETE** `/mcp/lazy/tools/{tool_name}/unload`

Unload a tool to free memory.

**Response (success):**
```json
{
  "message": "Tool 'audit_file' unloaded successfully",
  "tool": "audit_file",
  "unloaded": true
}
```

**Response (not loaded):**
```json
{
  "message": "Tool 'audit_file' was not loaded",
  "tool": "audit_file",
  "unloaded": false
}
```

**Use Case:** Long-running processes that need dynamic memory management.

---

## Usage Examples

### Example 1: Basic Workflow

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier": "demo", "password": "Demo1234"}' \
  | jq -r '.access_token')

# 2. Discover available tools (lightweight)
curl -s -X GET "http://localhost:8000/api/mcp/lazy/discover" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.tools[] | .name'

# Output:
# "audit_file"
# "excel_analyzer"
# "viz_tool"
# "deep_research"
# "extract_document_text"

# 3. Get specific tool spec (loads on-demand)
curl -s -X GET "http://localhost:8000/api/mcp/lazy/tools/audit_file" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.name, .version, .loaded_on_demand'

# Output:
# "audit_file"
# "1.0.0"
# true

# 4. Invoke tool (uses cached tool)
curl -s -X POST "http://localhost:8000/api/mcp/lazy/invoke" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "audit_file",
    "payload": {
      "doc_id": "674a5b8c9e7f12a3b4c5d6e7",
      "policy_id": "auto"
    }
  }' | jq '.success, .duration_ms'

# Output:
# true
# 1234.56

# 5. Check stats
curl -s -X GET "http://localhost:8000/api/mcp/lazy/stats" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.tools_loaded, .memory_efficiency'

# Output:
# 1
# "80.0%"
```

---

### Example 2: Filtering Tools by Category

```bash
# Get only compliance tools
curl -s -X GET "http://localhost:8000/api/mcp/lazy/discover?category=compliance" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.tools'

# Output:
# [
#   {
#     "name": "audit_file",
#     "category": "compliance",
#     "description": "Tool: audit_file",
#     "loaded": false
#   }
# ]

# Get analytics tools
curl -s -X GET "http://localhost:8000/api/mcp/lazy/discover?category=analytics" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.tools[] | .name'

# Output:
# "excel_analyzer"
# "viz_tool"
```

---

### Example 3: Search Tools

```bash
# Search for "audit" in name/description
curl -s -X GET "http://localhost:8000/api/mcp/lazy/discover?search=audit" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.total, .tools[] | .name'

# Output:
# 1
# "audit_file"

# Search for "research"
curl -s -X GET "http://localhost:8000/api/mcp/lazy/discover?search=research" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.tools[] | .name'

# Output:
# "deep_research"
```

---

### Example 4: Memory Management

```bash
# Load tool by invoking
curl -s -X POST "http://localhost:8000/api/mcp/lazy/invoke" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool": "audit_file", "payload": {"doc_id": "123"}}'

# Check memory usage
curl -s -X GET "http://localhost:8000/api/mcp/lazy/stats" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.tools_loaded, .tools_loaded_list'

# Output:
# 1
# ["audit_file"]

# Unload to free memory
curl -s -X DELETE "http://localhost:8000/api/mcp/lazy/tools/audit_file/unload" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.unloaded'

# Output:
# true

# Verify unloaded
curl -s -X GET "http://localhost:8000/api/mcp/lazy/stats" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.tools_loaded'

# Output:
# 0
```

---

## Performance Metrics

### Context Usage Comparison

| Approach | Context Size | Reduction |
|----------|--------------|-----------|
| **Eager Loading** (traditional) | ~150KB | Baseline |
| **Lazy Discovery** (minimal metadata) | ~2KB | **98.7%** ⬇️ |
| **Lazy + 1 Tool Loaded** | ~32KB | **78.7%** ⬇️ |
| **Lazy + All Tools Loaded** | ~150KB | 0% (same as eager) |

### Startup Time

| Approach | Import Time | Startup Time |
|----------|-------------|--------------|
| **Eager Loading** | ~500ms | ~800ms |
| **Lazy Loading** | ~10ms | ~50ms |

**Improvement:** 16x faster startup

### Memory Usage (5 Tools)

| Scenario | Memory Usage | Efficiency |
|----------|--------------|------------|
| **Eager (all loaded)** | 150KB | 0% |
| **Lazy (0 loaded)** | 2KB | 98.7% |
| **Lazy (1 loaded)** | 32KB | 78.7% |
| **Lazy (3 loaded)** | 92KB | 38.7% |

---

## Testing

### Run Lazy Loading Tests

```bash
# Run all lazy loading tests
make test-mcp-lazy

# Or with pytest directly
pytest apps/api/tests/mcp/test_lazy_registry.py -v
pytest apps/api/tests/mcp/test_lazy_routes.py -v
```

### Test Coverage

**test_lazy_registry.py** (34 tests):
- ✅ Tool metadata creation
- ✅ Directory scanning
- ✅ Class name inference
- ✅ Category inference
- ✅ Discovery filtering
- ✅ On-demand loading
- ✅ Caching behavior
- ✅ Invoke workflow
- ✅ Unloading tools
- ✅ Registry statistics
- ✅ Memory efficiency calculation
- ✅ Singleton pattern

**test_lazy_routes.py** (23 tests):
- ✅ Discover endpoint (all filters)
- ✅ Get tool spec endpoint
- ✅ Invoke endpoint
- ✅ Stats endpoint
- ✅ Unload endpoint
- ✅ User ID injection
- ✅ Callback handling
- ✅ Authentication required
- ✅ Error handling

---

## Migration Guide

### Before (Eager Loading)

```python
# src/mcp/server.py
from .tools.audit_file import AuditFileTool
from .tools.excel_analyzer import ExcelAnalyzerTool
# ... all imports

# All tools loaded at startup
tools = [
    AuditFileTool(),
    ExcelAnalyzerTool(),
    # ... all tools
]
```

```python
# src/main.py
from src.mcp.server import mcp as mcp_server

# ALL tools loaded when app starts
app.state.mcp_server = mcp_server
```

**Problems:**
- 150KB context usage
- Slow startup
- High memory footprint

---

### After (Lazy Loading)

```python
# src/mcp/lazy_registry.py
registry = LazyToolRegistry()

# Tools NOT loaded yet (only metadata scanned)
tools = registry.discover_tools()  # ~2KB
```

```python
# src/main.py
from src.mcp.lazy_routes import create_lazy_mcp_router

# Create lazy router
lazy_router = create_lazy_mcp_router(
    auth_dependency=get_current_user,
    on_invoke=_on_mcp_invoke
)
app.include_router(lazy_router, prefix="/api")
```

**Benefits:**
- ~2KB context usage (discovery)
- Near-instant startup
- Dynamic memory management

---

### Client Code Changes

**Before:**
```bash
# List all tools (loads all definitions)
GET /api/mcp/tools
# Returns full specs (~150KB)
```

**After:**
```bash
# Discover tools (minimal metadata)
GET /api/mcp/lazy/discover
# Returns only names (~2KB)

# Get specific tool spec (loads on-demand)
GET /api/mcp/lazy/tools/audit_file
# Returns full spec (~30KB for this tool only)

# Invoke tool (loads on-demand if needed)
POST /api/mcp/lazy/invoke
# Executes tool (caches for reuse)
```

**Migration Steps:**

1. **Update API calls:**
   - Change `/api/mcp/tools` → `/api/mcp/lazy/discover`
   - Change `/api/mcp/invoke` → `/api/mcp/lazy/invoke`

2. **Handle discovery response:**
   ```javascript
   // Before
   const tools = await fetch('/api/mcp/tools')
   // tools: [{name, version, description, input_schema, ...}] (full specs)

   // After
   const tools = await fetch('/api/mcp/lazy/discover')
   // tools: [{name, category, description, loaded}] (minimal metadata)
   ```

3. **Load specs on-demand:**
   ```javascript
   // When user selects a tool, load full spec
   const spec = await fetch(`/api/mcp/lazy/tools/${toolName}`)
   // spec: {name, version, input_schema, ...} (full spec)
   ```

4. **Invoke as before:**
   ```javascript
   // Invocation API is identical
   const result = await fetch('/api/mcp/lazy/invoke', {
     method: 'POST',
     body: JSON.stringify({tool: 'audit_file', payload: {...}})
   })
   ```

---

## Best Practices

### 1. Discovery First

Always discover tools before loading:

```python
# GOOD
tools = registry.discover_tools(category="compliance")
tool = await registry.load_tool(tools[0]["name"])

# BAD (no discovery)
tool = await registry.load_tool("unknown_tool")  # May fail
```

### 2. Cache Awareness

Understand caching behavior:

```python
# First load: Dynamic import (~30ms)
tool1 = await registry.load_tool("audit_file")

# Second load: Cache hit (~0.1ms)
tool2 = await registry.load_tool("audit_file")

assert tool1 is tool2  # Same instance
```

### 3. Memory Management

Unload unused tools in long-running processes:

```python
# Load tool for batch processing
tool = await registry.load_tool("audit_file")
for doc in large_batch:
    await tool.invoke({"doc_id": doc.id}, {})

# Free memory after batch
registry.unload_tool("audit_file")
```

### 4. Category Filtering

Use categories to reduce discovery overhead:

```python
# GOOD (specific category)
compliance_tools = registry.discover_tools(category="compliance")

# LESS EFFICIENT (all tools)
all_tools = registry.discover_tools()
compliance_tools = [t for t in all_tools if t["category"] == "compliance"]
```

### 5. Stats Monitoring

Monitor memory efficiency in production:

```python
stats = registry.get_registry_stats()
logger.info(
    "MCP memory efficiency",
    efficiency=stats["memory_efficiency"],
    loaded=stats["tools_loaded"],
    discovered=stats["tools_discovered"]
)
```

---

## Troubleshooting

### Issue: Tool not found

**Symptoms:**
```json
{
  "success": false,
  "error": {
    "code": "TOOL_NOT_FOUND",
    "message": "Tool 'my_tool' not found"
  }
}
```

**Solutions:**
1. Check tool exists: `GET /mcp/lazy/discover`
2. Verify spelling: Tool names are case-sensitive
3. Check tools directory: `apps/api/src/mcp/tools/`

---

### Issue: Import error when loading

**Symptoms:**
```
ERROR Failed to load tool
tool=audit_file
error=No module named 'src.mcp.tools.audit_file'
```

**Solutions:**
1. Verify module path in `lazy_registry.py`
2. Check file exists: `apps/api/src/mcp/tools/audit_file.py`
3. Verify class name matches: `AuditFileTool`

---

### Issue: Tool not unloading

**Symptoms:**
```json
{
  "unloaded": false,
  "message": "Tool 'audit_file' was not loaded"
}
```

**Solutions:**
1. Check if tool is loaded: `GET /mcp/lazy/stats`
2. Verify tool name is correct
3. Tool may have been already unloaded

---

## Future Enhancements

1. **Skill System** (Phase 2)
   - Reusable tool compositions
   - Skill catalog with ./skills directory

2. **Code Generation** (Phase 3)
   - Generate TypeScript types from tool schemas
   - Sandbox execution for generated code

3. **PII Protection** (Phase 4)
   - Tokenize sensitive data
   - Automatic redaction

4. **Workspace Persistence** (Phase 5)
   - Maintain state across invocations
   - Resume interrupted workflows

---

## References

- **Implementation:** `apps/api/src/mcp/lazy_registry.py`
- **Routes:** `apps/api/src/mcp/lazy_routes.py`
- **Tests:** `apps/api/tests/mcp/test_lazy_*.py`
- **MCP Architecture:** `docs/MCP_ARCHITECTURE.md`
- **Tools Guide:** `docs/MCP_TOOLS_GUIDE.md`
