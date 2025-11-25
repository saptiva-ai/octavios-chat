# MCP Architecture Improvements - Implementation Guide

## Executive Summary

This document outlines critical improvements needed for the MCP (Model Context Protocol) architecture to properly integrate tool results into LLM context.

**Current State**: Tools execute successfully but results don't reach the LLM
**Target State**: Tool results automatically enrich LLM context

---

## Problem Analysis

### Issue 1: Context Injection Gap

**Current Flow** (BROKEN):
```
User Message
    ↓
SimpleChatStrategy
    ↓
DocumentService.get_document_text_from_cache()  ✅ Works
    ↓
format_for_rag()  ✅ Works
    ↓
process_with_saptiva(document_context=...)  ✅ Works
    ↓
LLM receives document context  ✅ Works

BUT...

MCP Tool Execution (audit_file, excel_analyzer, etc.)
    ↓
Tool returns result  ✅ Works
    ↓
❌ STOPS HERE - Result not injected into context
    ↓
❌ LLM never sees tool results
```

### Issue 2: Tool Results Storage

Tool results are returned via `/api/mcp/invoke` but:
- ❌ Not saved to chat history
- ❌ Not cached for reuse
- ❌ Not available for next LLM turn

---

## Solution Architecture

### Phase 1: Add ContextManager (COMPLETED)

✅ Created `/apps/api/src/services/context_manager.py`

**Features**:
- Aggregates document + tool contexts
- Applies size limits consistently
- Formats for LLM injection
- Tracks sources for debugging

### Phase 2: Integrate ContextManager into SimpleChatStrategy

**File to Modify**: `apps/api/src/domain/chat_strategy.py`

**Current Code** (lines 98-154):
```python
# Only handles document context
doc_texts = await DocumentService.get_document_text_from_cache(...)
document_context, _, _ = DocumentService.extract_content_for_rag_from_cache(...)

coordinated_response = await self.chat_service.process_with_saptiva(
    ...,
    document_context=document_context  # Only documents, no tool results
)
```

**Proposed Change**:
```python
from ..services.context_manager import ContextManager

async def process(self, context: ChatContext) -> ChatProcessingResult:
    # Initialize unified context manager
    context_mgr = ContextManager()

    # 1. Add document context (existing logic)
    if context.document_ids:
        doc_texts = await DocumentService.get_document_text_from_cache(...)
        for doc_id, text in doc_texts.items():
            context_mgr.add_document_context(
                doc_id=doc_id,
                text=text,
                filename=text.get("filename")
            )

    # 2. Add tool results (NEW LOGIC)
    if context.tool_results:
        for tool_name, result in context.tool_results.items():
            context_mgr.add_tool_result(
                tool_name=tool_name,
                result=result
            )

    # 3. Build unified context
    unified_context, metadata = context_mgr.build_context_string()

    # 4. Pass to LLM
    coordinated_response = await self.chat_service.process_with_saptiva(
        ...,
        document_context=unified_context  # Now includes tools!
    )

    return response
```

### Phase 3: Store Tool Results in ChatContext

**File to Modify**: `apps/api/src/domain/chat_context.py`

**Add field**:
```python
@dataclass
class ChatContext:
    # ... existing fields ...

    # NEW: Store tool results for context injection
    tool_results: Dict[str, Any] = field(default_factory=dict)
```

### Phase 4: Invoke Tools Before LLM Call

**File to Modify**: `apps/api/src/routers/chat/endpoints/message_endpoints.py`

**Current Code** (lines 90-145):
```python
# Build context
context = build_chat_context(request, user_id, settings)

# Execute strategy (SimpleChatStrategy)
strategy = SimpleChatStrategy(...)
result = await strategy.process(context)
```

**Proposed Change**:
```python
# Build context
context = build_chat_context(request, user_id, settings)

# NEW: Check if tools should be invoked
if request.tools_enabled:
    tool_results = await invoke_relevant_tools(
        context=context,
        tools_enabled=request.tools_enabled
    )
    context.tool_results = tool_results

# Execute strategy (now with tool results in context)
strategy = SimpleChatStrategy(...)
result = await strategy.process(context)  # Will include tool context
```

**New helper function**:
```python
async def invoke_relevant_tools(
    context: ChatContext,
    tools_enabled: Dict[str, bool]
) -> Dict[str, Any]:
    """
    Invoke relevant MCP tools based on context and return results.

    Args:
        context: ChatContext with message, files, etc.
        tools_enabled: Dict of tool_name -> enabled

    Returns:
        Dict of tool_name -> result
    """
    results = {}

    # Check if audit tool should run
    if tools_enabled.get("audit_file") and context.document_ids:
        for doc_id in context.document_ids:
            try:
                audit_result = await mcp_client.invoke_tool(
                    tool_name="audit_file",
                    payload={"doc_id": doc_id}
                )
                results[f"audit_file_{doc_id}"] = audit_result
            except Exception as e:
                logger.warning("Audit tool failed", doc_id=doc_id, error=str(e))

    # Check if excel analyzer should run
    if tools_enabled.get("excel_analyzer") and _has_excel_files(context.document_ids):
        for doc_id in _get_excel_files(context.document_ids):
            try:
                excel_result = await mcp_client.invoke_tool(
                    tool_name="excel_analyzer",
                    payload={
                        "doc_id": doc_id,
                        "operations": ["stats", "preview"]
                    }
                )
                results[f"excel_analyzer_{doc_id}"] = excel_result
            except Exception as e:
                logger.warning("Excel analyzer failed", doc_id=doc_id, error=str(e))

    return results
```

---

## Implementation Checklist

### Phase 1: Foundation ✅
- [x] Create ContextManager service
- [x] Add summarizers for each tool type
- [x] Implement size limit logic

### Phase 2: Integration (TODO)
- [ ] Add `tool_results` field to ChatContext
- [ ] Create `invoke_relevant_tools()` helper
- [ ] Modify SimpleChatStrategy to use ContextManager
- [ ] Update message_endpoints.py to invoke tools

### Phase 3: Testing (TODO)
- [ ] Test audit_file results in LLM context
- [ ] Test excel_analyzer results in LLM context
- [ ] Test combined document + tool context
- [ ] Verify size limits work correctly

### Phase 4: Deep Research Integration (TODO)
- [ ] Add research trigger logic in SimpleChatStrategy
- [ ] Store research results in tool_results
- [ ] Add research context to ContextManager

---

## Expected Outcomes

### Before (Current State)
```
User: "Audita este PDF"
→ audit_file runs
→ Returns ValidationReport
→ ❌ LLM doesn't see findings
→ LLM responds: "El PDF ha sido procesado" (generic)
```

### After (Target State)
```
User: "Audita este PDF"
→ audit_file runs
→ Returns ValidationReport
→ ✅ ContextManager formats findings
→ ✅ Findings injected into LLM prompt
→ LLM responds: "He encontrado 3 problemas:
   1. Falta disclaimer en página 5
   2. Logo incorrecto en página 2
   3. Error ortográfico: 'recivir' debe ser 'recibir'"
```

---

## Performance Considerations

### Tool Execution Timing
- Tools can be slow (OCR = 5-10s, Research = 30-60s)
- Run tools in parallel where possible
- Cache results to avoid re-execution

### Context Size Management
- Document context: 16KB limit
- Tool context: 8KB limit
- Total: 24KB limit
- Truncate intelligently (keep most relevant)

### Caching Strategy
```python
# Cache key format
cache_key = f"mcp:tool:{tool_name}:{doc_id}:{policy_id}"

# TTL varies by tool
CACHE_TTL = {
    "audit_file": 3600,      # 1 hour (findings don't change)
    "excel_analyzer": 1800,  # 30 min (data might update)
    "extract_document_text": 3600,  # 1 hour (text stable)
    "deep_research": 86400,  # 24 hours (research expensive)
}
```

---

## Migration Path

### Step 1: Add ContextManager (Non-breaking)
- ✅ COMPLETED
- No changes to existing behavior

### Step 2: Update ChatContext (Non-breaking)
- Add `tool_results` field with default empty dict
- Existing code continues to work

### Step 3: Implement Tool Invocation (Feature Flag)
```python
# Feature flag for gradual rollout
ENABLE_TOOL_CONTEXT_INJECTION = os.getenv("ENABLE_TOOL_CONTEXT_INJECTION", "false") == "true"

if ENABLE_TOOL_CONTEXT_INJECTION and request.tools_enabled:
    # New logic
    tool_results = await invoke_relevant_tools(...)
else:
    # Old logic (fallback)
    tool_results = {}
```

### Step 4: Enable in Production
- Test with subset of users
- Monitor context size and latency
- Gradually increase rollout percentage

---

## Code Locations Reference

| Component | File Path | Action |
|-----------|-----------|--------|
| ContextManager | `src/services/context_manager.py` | ✅ Created |
| ChatContext | `src/domain/chat_context.py` | ⏳ Add tool_results field |
| SimpleChatStrategy | `src/domain/chat_strategy.py:67-210` | ⏳ Integrate ContextManager |
| Message Endpoints | `src/routers/chat/endpoints/message_endpoints.py` | ⏳ Add tool invocation |
| MCP Server | `src/mcp/server.py` | ✅ No changes needed |
| FastAPI Adapter | `src/mcp/fastapi_adapter.py` | ✅ No changes needed |

---

## Questions & Answers

### Q1: Will this slow down chat responses?
**A**: Tools run in parallel with document loading. For fast tools (audit_file cached, excel_analyzer on small files), overhead is <500ms. For slow tools (OCR, research), we can:
- Show loading indicator to user
- Stream tool progress via SSE
- Return partial response while tools complete

### Q2: What if a tool fails?
**A**: Graceful degradation:
```python
try:
    tool_result = await invoke_tool(...)
    context_mgr.add_tool_result(...)
except Exception as e:
    logger.warning("Tool failed, continuing without it", tool=tool_name, error=str(e))
    # LLM still gets document context, just not tool result
```

### Q3: How to handle large tool outputs?
**A**: ContextManager applies size limits:
- Summarizes tool results (audit: top 5 findings, excel: key stats)
- Truncates if still too large
- Stores full result in metadata for API response

### Q4: Can users disable tool context injection?
**A**: Yes, via tools_enabled flag:
```python
{
    "message": "Analiza este PDF",
    "file_ids": ["doc_123"],
    "tools_enabled": {
        "audit_file": false  # Disable audit context injection
    }
}
```

---

## Next Steps

1. **Review this proposal** with team
2. **Implement Phase 2** (ChatContext + invoke_relevant_tools)
3. **Test with sample documents** (PDF with compliance issues)
4. **Measure performance impact** (latency, token usage)
5. **Roll out gradually** with feature flag

---

## Success Metrics

- ✅ Tool results appear in LLM responses
- ✅ Context size stays within limits (<24KB)
- ✅ Response quality improves (user feedback)
- ✅ Tool execution time <2s for 80% of requests
- ✅ Cache hit rate >60% for repeated operations
