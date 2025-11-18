# MCP Task Management Implementation

## Overview

Implemented complete 202 Accepted pattern for long-running MCP tool invocations with cancellation support, addressing **Priority #1** from user feedback.

## Implementation Summary

### 1. Core Task Management (`apps/api/src/mcp/tasks.py`)

**Features:**
- Task lifecycle: PENDING → RUNNING → COMPLETED | FAILED | CANCELLED
- Priority queue (LOW, NORMAL, HIGH)
- Progress tracking (0.0 to 1.0 with optional message)
- Cancellation tokens (cooperative cancellation)
- Automatic cleanup (TTL-based, default 24h)
- In-memory MVP (upgradeable to Redis/RQ/Celery)

**Key Classes:**
```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskManager:
    def create_task(tool, payload, user_id, priority) -> task_id
    def update_progress(task_id, progress, message)
    def request_cancellation(task_id) -> bool
    def mark_completed(task_id, result)
    def mark_failed(task_id, error)
    def list_tasks(user_id, tool, status) -> List[Task]
```

### 2. FastAPI Routes (`apps/api/src/mcp/fastapi_adapter.py`)

**New Endpoints:**

#### POST /api/mcp/tasks
- Submit long-running tool as background task
- Returns 202 Accepted with task_id
- Response includes poll_url, cancel_url, estimated_duration_ms

**Request:**
```json
{
  "tool": "excel_analyzer",
  "payload": {...},
  "priority": "normal"  // optional: low | normal | high
}
```

**Response (202):**
```json
{
  "task_id": "uuid",
  "status": "pending",
  "poll_url": "/api/mcp/tasks/{task_id}",
  "cancel_url": "/api/mcp/tasks/{task_id}",
  "estimated_duration_ms": 10000
}
```

#### GET /api/mcp/tasks/{task_id}
- Poll task status and retrieve result
- Returns progress, timestamps, result/error

**Response:**
```json
{
  "task_id": "uuid",
  "tool": "excel_analyzer",
  "status": "running",
  "progress": 0.5,
  "progress_message": "Processing rows...",
  "created_at": "2025-01-11T...",
  "started_at": "2025-01-11T...",
  "completed_at": null,
  "result": {...},  // only when status=completed
  "error": {...}   // only when status=failed
}
```

#### DELETE /api/mcp/tasks/{task_id}
- Request task cancellation (cooperative)
- Returns 202 Accepted
- Tool must check `task_manager.is_cancellation_requested(task_id)` at checkpoints

**Response (202):**
```json
{
  "task_id": "uuid",
  "status": "cancellation_requested",
  "message": "Cancellation requested. Task will stop at next checkpoint."
}
```

#### GET /api/mcp/tasks
- List user's tasks with filters
- Query params: `?status=completed&tool=excel_analyzer`
- Returns array of task summaries

### 3. Background Task Execution

**Adapter Method:**
```python
async def _execute_task(task_id, tool_name, payload, user):
    """
    Execute task in background with:
    - Progress tracking
    - Cancellation checks
    - Error handling (ValueError → VALIDATION_ERROR, etc.)
    - Result persistence
    """
```

**Error Code Mapping:**
- `ValueError` → `VALIDATION_ERROR`
- `PermissionError` → `PERMISSION_DENIED`
- `asyncio.CancelledError` → Task marked as CANCELLED
- `Exception` → `EXECUTION_ERROR`

### 4. Lifecycle Integration (`apps/api/src/main.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await task_manager.start()  # Starts cleanup loop

    yield

    # Shutdown
    await task_manager.stop()  # Graceful shutdown
```

### 5. Comprehensive Tests (`apps/api/tests/mcp/test_task_routes.py`)

**Test Coverage:**
- ✅ Create task (202 Accepted)
- ✅ Create task with priority
- ✅ Create task with missing/invalid tool
- ✅ Get task status (pending, running, completed, failed)
- ✅ Get task status with wrong user (403)
- ✅ Cancel task (pending, running, completed)
- ✅ Cancel task with wrong user (403)
- ✅ List tasks (empty, with filters by status/tool)
- ✅ Background task execution (success, validation error, cancellation)

## Usage Example

### Frontend (TypeScript SDK)

```typescript
// Submit long-running task
const { task_id, poll_url } = await mcpClient.submitTask({
  tool: "excel_analyzer",
  payload: {
    doc_id: "doc_123",
    operations: ["stats", "aggregate", "validate"]
  },
  priority: "high"
});

// Poll for completion
const pollInterval = setInterval(async () => {
  const status = await mcpClient.getTaskStatus(task_id);

  console.log(`Progress: ${status.progress * 100}% - ${status.progress_message}`);

  if (status.status === "completed") {
    clearInterval(pollInterval);
    console.log("Result:", status.result);
  } else if (status.status === "failed") {
    clearInterval(pollInterval);
    console.error("Error:", status.error);
  }
}, 1000);

// Cancel if needed
await mcpClient.cancelTask(task_id);
```

### Backend (Tool Implementation)

```python
@mcp.tool()
async def excel_analyzer(
    doc_id: str,
    operations: List[str],
    ctx: Context = None,
) -> dict:
    """Analyze Excel files with cancellation support."""

    # Get task_id from context (if running as task)
    task_id = ctx.get("task_id") if ctx else None

    # Checkpoint 1: Load file
    if task_id and task_manager.is_cancellation_requested(task_id):
        raise asyncio.CancelledError()

    df = load_excel(doc_id)
    task_manager.update_progress(task_id, 0.25, "File loaded")

    # Checkpoint 2: Process operations
    for i, op in enumerate(operations):
        if task_id and task_manager.is_cancellation_requested(task_id):
            raise asyncio.CancelledError()

        result[op] = process_operation(df, op)
        progress = 0.25 + (0.75 * (i + 1) / len(operations))
        task_manager.update_progress(task_id, progress, f"Processing {op}")

    return result
```

## Architecture Decisions

### Why In-Memory Queue (MVP)?
- **Simplicity**: No external dependencies
- **Low latency**: Sub-ms task creation
- **Sufficient for MVP**: Single-instance deployment
- **Upgradeable**: Interface supports Redis/RQ/Celery migration

### Why Cooperative Cancellation?
- **Safety**: Tool controls cleanup (close files, rollback DB, etc.)
- **Predictability**: No abrupt termination mid-operation
- **Explicit**: Tool must opt-in with checkpoints

### Why 202 Accepted Pattern?
- **HTTP Best Practice**: Correct status code for async operations
- **Client Control**: Client decides polling frequency
- **No Timeouts**: Tools can run for minutes/hours
- **Backpressure**: Client can see queue depth

## Migration Notes

### Phase 1: MVP (Current)
- In-memory TaskManager
- Manual polling from frontend
- No persistence (tasks lost on restart)

### Phase 2: Production
- **Redis Backend**: Replace in-memory dict with Redis
- **Task Persistence**: Survive restarts
- **Distributed**: Multiple API instances share queue
- **WebSocket Updates**: Push progress to frontend
- **Task Priority Queue**: Redis sorted sets

### Phase 3: Scale
- **RQ/Celery**: Dedicated worker processes
- **Task Routing**: Tool-specific workers
- **Result Backend**: Store large results in S3
- **Task Chaining**: Workflow orchestration

## Dependencies Added

### `apps/api/requirements.txt`
```txt
# MCP (Model Context Protocol) - Official SDK
fastmcp>=2.0.0
```

## Testing

```bash
# Run task management tests
pytest apps/api/tests/mcp/test_task_routes.py -v

# Test coverage
pytest apps/api/tests/mcp/ --cov=src.mcp --cov-report=term-missing
```

## Related Files

- `apps/api/src/mcp/tasks.py` - Task manager core
- `apps/api/src/mcp/fastapi_adapter.py` - REST endpoints
- `apps/api/src/mcp/protocol.py` - Error taxonomy (ErrorCode enum)
- `apps/api/src/main.py` - Lifecycle integration
- `apps/api/tests/mcp/test_task_routes.py` - Comprehensive tests

## Next Steps

1. **Frontend Integration**: Update TypeScript SDK with task management methods
2. **Tool Migration**: Add cancellation checkpoints to existing tools
3. **Monitoring**: Add Prometheus metrics (task_duration, task_cancellations, etc.)
4. **Documentation**: Update API docs with task management flows
5. **Production Hardening**: Consider Redis backend for Phase 2

## Completion Status

✅ **Priority #1: Cancellation and long-running tasks - COMPLETED**
- 202 Accepted pattern implemented
- Task polling endpoints working
- Cancellation tokens functional
- Comprehensive test coverage
- Lifecycle integration complete

**User Feedback Addressed:**
> "Si un tool se tarda (Excel pesado, Viz con JOINs grandes), el usuario cancela y el worker sigue quemando CPU."

**Solution:**
- Cooperative cancellation via `task_manager.request_cancellation(task_id)`
- Tools check `is_cancellation_requested()` at checkpoints
- Graceful shutdown with cleanup
- Client can monitor progress and cancel anytime
