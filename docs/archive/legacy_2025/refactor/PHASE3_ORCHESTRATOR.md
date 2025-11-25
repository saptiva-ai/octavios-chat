# FASE 3: Orquestador de Chat Resiliente

**Duración**: 2 días
**Owner**: Backend team
**Dependencies**: Fase 1 + Fase 2 completadas

---

## 🎯 Objetivos

1. Refactorizar `streaming_handler.py` para usar nuevos MCP tools
2. Separar ingesta de archivos del flujo de respuesta
3. Implementar manejo de errores resiliente (cada turno independiente)
4. Emitir eventos SSE para estados de procesamiento
5. Garantizar que fallos en tools NO rompen la conversación

---

## 📋 Tareas (Día 1)

### 3.1 Refactorizar `streaming_handler.py`

**File**: `apps/api/src/routers/chat/handlers/streaming_handler.py`

**Cambios principales**:

```python
# ANTES (líneas 505-534):
if context.document_ids:
    try:
        doc_texts = await DocumentService.get_document_text_from_cache(...)
        # Procesamiento síncrono
    except Exception as doc_exc:
        doc_warnings.append(...)

# DESPUÉS:
# PASO 1: ¿Hay nuevos adjuntos? → Ingestar async
if context.new_file_refs:
    await self._handle_file_ingestion(context)

# PASO 2: Recuperar segmentos de docs ya listos
document_context = await self._get_document_context(context)
```

**Implementación completa**:

```python
async def _stream_chat_response(
    self,
    context: ChatContext,
    chat_service: ChatService,
    chat_session,
    cache,
    user_message
) -> AsyncGenerator[dict, None]:
    """
    Stream chat response with resilient document handling.

    NEW FLOW:
    1. If new files attached → ingest async (emit SSE event)
    2. Retrieve segments from ready documents
    3. Build prompt with system + context + segments
    4. Stream LLM response
    5. Handle errors gracefully (no blocking)
    """

    try:
        # ==============================================================
        # STEP 1: FILE INGESTION (async, non-blocking)
        # ==============================================================
        if context.new_file_refs:
            try:
                ingestion_result = await self._handle_file_ingestion(
                    context=context,
                    chat_session=chat_session
                )

                # Emit system message to user
                yield {
                    "event": "system",
                    "data": json.dumps({
                        "type": "file_ingestion",
                        "message": ingestion_result["message"],
                        "documents": ingestion_result["documents"]
                    })
                }

                logger.info(
                    "Files ingested",
                    chat_id=context.chat_id,
                    count=len(context.new_file_refs)
                )

            except Exception as ingest_exc:
                # Ingestion failed - emit warning but DON'T block chat
                logger.error(
                    "File ingestion failed",
                    error=str(ingest_exc),
                    chat_id=context.chat_id,
                    exc_info=True
                )

                yield {
                    "event": "warning",
                    "data": json.dumps({
                        "message": f"⚠️ No pude procesar algunos archivos: {str(ingest_exc)[:100]}. "
                                   f"Continuaré sin ellos."
                    })
                }

        # ==============================================================
        # STEP 2: RETRIEVE DOCUMENT CONTEXT (from ready docs)
        # ==============================================================
        document_context = None
        doc_metadata = []

        try:
            retrieval_result = await self._get_document_context(
                context=context,
                question=context.message
            )

            if retrieval_result["segments"]:
                # Format segments for prompt
                document_context = self._format_segments_for_prompt(
                    retrieval_result["segments"]
                )

                doc_metadata = [
                    f"{seg['doc_name']} (segmento {seg['index']})"
                    for seg in retrieval_result["segments"][:3]
                ]

                logger.info(
                    "Document context retrieved",
                    chat_id=context.chat_id,
                    segments_count=len(retrieval_result["segments"]),
                    docs_count=retrieval_result["total_docs"]
                )

            elif retrieval_result["total_docs"] > 0:
                # Documents exist but not ready yet
                yield {
                    "event": "info",
                    "data": json.dumps({
                        "message": f"ℹ️ Tengo {retrieval_result['total_docs']} documento(s) "
                                   f"en procesamiento. Responderé sin ellos por ahora."
                    })
                }

        except Exception as retrieval_exc:
            # Retrieval failed - continue without context
            logger.error(
                "Document retrieval failed",
                error=str(retrieval_exc),
                chat_id=context.chat_id,
                exc_info=True
            )

            yield {
                "event": "warning",
                "data": json.dumps({
                    "message": "⚠️ No pude acceder a los documentos. Respondo sin contexto documental."
                })
            }

        # ==============================================================
        # STEP 3: BUILD PROMPT (system + context + segments)
        # ==============================================================
        from ....core.prompt_registry import get_prompt_registry
        prompt_registry = get_prompt_registry()

        # Get system prompt for this model
        system_prompt, model_params = prompt_registry.resolve(
            model=context.model,
            tools_markdown=None,
            channel="chat"
        )

        # Add document context to system prompt if available
        if document_context:
            system_prompt += f"\n\n## CONTEXTO DOCUMENTAL\n\n{document_context}"

        # Build messages for LLM
        messages = await self._build_messages(
            chat_service=chat_service,
            chat_session=chat_session,
            user_message=context.message,
            system_prompt=system_prompt
        )

        # ==============================================================
        # STEP 4: STREAM LLM RESPONSE
        # ==============================================================
        async for chunk in self._stream_from_llm(
            messages=messages,
            model=context.model,
            model_params=model_params
        ):
            yield chunk

        # ==============================================================
        # STEP 5: SAVE ASSISTANT MESSAGE
        # ==============================================================
        await chat_service.add_assistant_message(
            chat_session=chat_session,
            content=self._accumulated_content,  # From streaming
            model=context.model,
            metadata={
                "document_context": bool(document_context),
                "documents_used": doc_metadata
            }
        )

    except Exception as stream_exc:
        # GLOBAL ERROR HANDLER (already implemented in Capital 414 fixes)
        logger.error(
            "CRITICAL: Streaming chat failed",
            error=str(stream_exc),
            exc_type=type(stream_exc).__name__,
            model=context.model,
            user_id=context.user_id,
            exc_info=True
        )

        # Save error message
        try:
            await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=f"❌ Error: {str(stream_exc)[:200]}",
                model=context.model,
                metadata={"error": True}
            )
        except Exception as save_exc:
            logger.error("Failed to save error message", error=str(save_exc))

        # Yield error event
        yield {
            "event": "error",
            "data": json.dumps({
                "error": type(stream_exc).__name__,
                "message": str(stream_exc)
            })
        }


async def _handle_file_ingestion(
    self,
    context: ChatContext,
    chat_session
) -> Dict[str, Any]:
    """
    Handle async file ingestion using IngestFilesTool.

    Args:
        context: Chat context with new_file_refs
        chat_session: Chat session to update

    Returns:
        Ingestion result from tool
    """

    from src.mcp.tools.ingest_files import IngestFilesTool

    tool = IngestFilesTool()

    result = await tool.execute(
        conversation_id=chat_session.id,
        file_refs=context.new_file_refs
    )

    if not result.success:
        raise ValueError(result.error)

    return result.data


async def _get_document_context(
    self,
    context: ChatContext,
    question: str
) -> Dict[str, Any]:
    """
    Retrieve relevant document segments using GetRelevantSegmentsTool.

    Args:
        context: Chat context
        question: User's question

    Returns:
        Retrieval result with segments
    """

    from src.mcp.tools.get_segments import GetRelevantSegmentsTool

    tool = GetRelevantSegmentsTool()

    result = await tool.execute(
        conversation_id=context.chat_id,
        question=question,
        max_segments=5  # Configurable
    )

    if not result.success:
        raise ValueError(result.error)

    return result.data


def _format_segments_for_prompt(self, segments: List[Dict[str, Any]]) -> str:
    """
    Format retrieved segments for LLM prompt.

    Args:
        segments: List of segment dicts

    Returns:
        Formatted markdown string
    """

    if not segments:
        return ""

    lines = [
        "Los siguientes fragmentos de documentos pueden ser relevantes para tu respuesta:\n"
    ]

    for i, seg in enumerate(segments, 1):
        lines.append(
            f"**Documento {i}: {seg['doc_name']}** (segmento {seg['index']})\n"
            f"```\n{seg['text'][:500]}...\n```\n"
        )

    lines.append(
        "\nUsa esta información si es relevante, pero indica claramente "
        "cuando cites estos documentos."
    )

    return "\n".join(lines)
```

---

### 3.2 Actualizar `ChatContext` DTO

**File**: `apps/api/src/domain/chat_context.py`

**Agregar campo `new_file_refs`**:

```python
@dataclass
class ChatContext:
    """Chat context DTO"""

    # ... existing fields ...

    # NEW: Distinguish between existing docs and new uploads
    document_ids: List[str] = field(default_factory=list)  # All docs in session
    new_file_refs: List[str] = field(default_factory=list)  # Just uploaded in this turn

    # DEPRECATED (for migration):
    file_ids: Optional[List[str]] = None
```

**Construcción en endpoint**:

```python
# apps/api/src/routers/chat/endpoints/message_endpoints.py

# Determine new files vs. existing
existing_doc_ids = [d.doc_id for d in chat_session.documents]
new_file_refs = [
    fid for fid in request.file_ids
    if fid not in existing_doc_ids
]

context = ChatContext(
    chat_id=chat_session.id,
    message=request.message,
    model=request.model,
    user_id=current_user.id,
    document_ids=existing_doc_ids,  # All docs in session
    new_file_refs=new_file_refs      # Just uploaded
)
```

---

## 📋 Tareas (Día 2)

### 3.3 SSE Event Specifications

**New event types**:

```typescript
// Frontend types
type SSEEvent =
  | { event: "chunk", data: { content: string } }
  | { event: "done", data: null }
  | { event: "error", data: { error: string, message: string } }
  | { event: "system", data: { type: string, message: string, documents?: Array<...> } }
  | { event: "warning", data: { message: string } }
  | { event: "info", data: { message: string } }
  | { event: "document_ready", data: { doc_id: string, doc_name: string } }
```

**Backend emission**:

```python
# System event (file ingestion)
yield {
    "event": "system",
    "data": json.dumps({
        "type": "file_ingestion",
        "message": "📄 Recibí: report.pdf (32 págs). Procesando...",
        "documents": [
            {"doc_id": "...", "name": "report.pdf", "status": "processing"}
        ]
    })
}

# Warning event (non-blocking error)
yield {
    "event": "warning",
    "data": json.dumps({
        "message": "⚠️ No pude procesar archivo.pdf. Continuaré sin él."
    })
}

# Info event (context availability)
yield {
    "event": "info",
    "data": json.dumps({
        "message": "ℹ️ Tengo 2 documentos en procesamiento. Responderé sin ellos por ahora."
    })
}
```

---

### 3.4 Error Recovery Tests

**File**: `apps/api/tests/integration/test_error_recovery.py`

```python
"""
Test error recovery in chat orchestrator.

Scenarios:
1. File ingestion fails → chat continues without docs
2. Retrieval fails → chat continues without context
3. LLM fails → error message shown, next turn works
"""

import pytest
from unittest.mock import patch, AsyncMock

from src.routers.chat.handlers.streaming_handler import StreamingHandler
from src.domain.chat_context import ChatContext


@pytest.mark.asyncio
async def test_chat_continues_after_ingestion_failure(
    db_session,
    sample_chat_session,
    sample_user
):
    """Test that chat continues even if file ingestion fails"""

    handler = StreamingHandler()

    context = ChatContext(
        chat_id=sample_chat_session.id,
        message="Hello",
        model="Saptiva Cortex",
        user_id=sample_user.id,
        new_file_refs=["invalid-file-id"]  # Will fail
    )

    # Patch IngestFilesTool to raise exception
    with patch("src.mcp.tools.ingest_files.IngestFilesTool.execute") as mock_ingest:
        mock_ingest.side_effect = ValueError("File not found")

        events = []
        async for event in handler._stream_chat_response(...):
            events.append(event)

    # Should emit warning but continue
    warning_events = [e for e in events if e["event"] == "warning"]
    assert len(warning_events) == 1
    assert "No pude procesar" in warning_events[0]["data"]

    # Should still emit chat response
    chunk_events = [e for e in events if e["event"] == "chunk"]
    assert len(chunk_events) > 0


@pytest.mark.asyncio
async def test_chat_continues_after_retrieval_failure(
    db_session,
    sample_chat_session,
    sample_user
):
    """Test that chat continues if document retrieval fails"""

    handler = StreamingHandler()

    context = ChatContext(
        chat_id=sample_chat_session.id,
        message="What does the report say?",
        model="Saptiva Cortex",
        user_id=sample_user.id,
        document_ids=["doc-123"]  # Exists but retrieval will fail
    )

    # Patch GetRelevantSegmentsTool to raise exception
    with patch("src.mcp.tools.get_segments.GetRelevantSegmentsTool.execute") as mock_retrieval:
        mock_retrieval.side_effect = ValueError("Cache miss")

        events = []
        async for event in handler._stream_chat_response(...):
            events.append(event)

    # Should emit warning
    warning_events = [e for e in events if e["event"] == "warning"]
    assert len(warning_events) == 1

    # Should respond without document context
    chunk_events = [e for e in events if e["event"] == "chunk"]
    assert len(chunk_events) > 0


@pytest.mark.asyncio
async def test_next_turn_works_after_error(
    db_session,
    sample_chat_session,
    sample_user
):
    """Test that conversation continues in next turn after error"""

    handler = StreamingHandler()

    # TURN 1: Fails
    context_1 = ChatContext(
        chat_id=sample_chat_session.id,
        message="First message",
        model="Saptiva Cortex",
        user_id=sample_user.id
    )

    with patch("src.routers.chat.handlers.streaming_handler.StreamingHandler._stream_from_llm") as mock_llm:
        mock_llm.side_effect = ValueError("LLM timeout")

        events_1 = []
        async for event in handler._stream_chat_response(...):
            events_1.append(event)

    # Should emit error
    error_events = [e for e in events_1 if e["event"] == "error"]
    assert len(error_events) == 1

    # TURN 2: Should work
    context_2 = ChatContext(
        chat_id=sample_chat_session.id,
        message="Second message",
        model="Saptiva Cortex",
        user_id=sample_user.id
    )

    # Don't mock LLM this time - should work normally
    events_2 = []
    async for event in handler._stream_chat_response(...):
        events_2.append(event)

    # Should succeed
    chunk_events = [e for e in events_2 if e["event"] == "chunk"]
    assert len(chunk_events) > 0

    error_events = [e for e in events_2 if e["event"] == "error"]
    assert len(error_events) == 0
```

---

## 📋 Checklist de Validación

### Functional Tests

- [ ] Chat with new files → ingestion SSE event emitted
- [ ] Chat with existing docs → segments retrieved correctly
- [ ] Ingestion failure → warning shown, chat continues
- [ ] Retrieval failure → warning shown, chat continues
- [ ] LLM failure → error shown, next turn works
- [ ] No documents → chat works normally without context

### Performance Tests

- [ ] File ingestion returns < 500ms (async dispatch)
- [ ] Segment retrieval < 200ms (from cache)
- [ ] Overall chat response time unchanged
- [ ] No memory leaks from failed operations

### Edge Cases

- [ ] Empty file list → no ingestion call
- [ ] Duplicate file upload → idempotent handling
- [ ] Document deleted mid-conversation → graceful degradation
- [ ] Very large files (>50MB) → timeout handled correctly

---

## ✅ Acceptance Criteria

1. [ ] `streaming_handler.py` uses new MCP tools
2. [ ] Each turn is independent (no state pollution)
3. [ ] All error scenarios tested
4. [ ] SSE events documented and typed
5. [ ] Zero regressions in existing chat functionality
6. [ ] Performance benchmarks maintained

---

## 📊 Metrics

**Before (Capital 414 fixes)**:
- Error handling: Basic try-catch
- Document processing: Synchronous in request
- Recovery: Conversation could get stuck

**After (Orchestrator refactor)**:
- Error handling: Multi-layer with SSE events
- Document processing: Async with status tracking
- Recovery: Each turn fully independent

---

## 🔗 Next Phase

Once Phase 3 is complete:
→ **Phase 4**: Frontend UI for document lifecycle visualization
