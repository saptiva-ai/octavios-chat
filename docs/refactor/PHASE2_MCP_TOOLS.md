# FASE 2: MCP Tools Separados (Ingesta vs. Retrieval)

**Duración**: 3 días
**Owner**: Backend team + MCP specialist
**Dependencies**: Fase 1 completada (DocumentState model)

---

## 🎯 Objetivos

1. Separar ingesta de archivos (asíncrona) de recuperación de contexto (síncrona)
2. Crear tool `ingest_files` que retorna respuesta inmediata
3. Crear tool `get_relevant_segments` para RAG estructurado
4. Implementar workers async para procesamiento en background
5. Eliminar procesamiento síncrono de PDFs en request de chat

---

## 📋 Tareas (Día 1)

### 2.1 Tool: `ingest_files`

**Objetivo**: Recibir archivos, crear `DocumentState`, disparar procesamiento async.

**File**: `apps/api/src/mcp/tools/ingest_files.py`

```python
"""
MCP Tool: Asynchronous file ingestion for chat sessions.

Replaces synchronous document processing in chat requests.
"""

import structlog
from typing import List, Dict, Any
from datetime import datetime

from src.mcp.tools.base import BaseTool, ToolInput, ToolResult
from src.models.chat import ChatSession
from src.models.document import Document
from src.models.document_state import DocumentState, ProcessingStatus
from src.services.document_tasks import process_document_task

logger = structlog.get_logger()


class IngestFilesInput(ToolInput):
    """Input schema for ingest_files tool"""
    conversation_id: str
    file_refs: List[str]  # List of document IDs or storage refs


class IngestFilesTool(BaseTool):
    """
    Asynchronously ingest files into a conversation.

    Flow:
    1. Create DocumentState records in UPLOADING status
    2. Dispatch async workers for processing
    3. Return immediate response (don't block chat)

    Example usage in orchestrator:
        result = await IngestFilesTool().execute(
            conversation_id="chat-123",
            file_refs=["doc-abc", "doc-def"]
        )
        # Returns: {"status": "processing", "documents": [...]}
    """

    name = "ingest_files"
    description = "Ingest files into conversation for RAG processing"

    async def execute(self, conversation_id: str, file_refs: List[str]) -> ToolResult:
        """
        Ingest files asynchronously.

        Args:
            conversation_id: Chat session ID
            file_refs: List of document IDs to ingest

        Returns:
            Immediate response with processing status
        """

        logger.info(
            "Ingesting files",
            conversation_id=conversation_id,
            file_count=len(file_refs)
        )

        # 1. Fetch chat session
        session = await ChatSession.get(conversation_id)
        if not session:
            return ToolResult(
                success=False,
                error=f"Conversation {conversation_id} not found"
            )

        ingested_docs = []
        failed_docs = []

        # 2. Create DocumentState for each file
        for file_ref in file_refs:
            try:
                # Check if already ingested
                existing = session.get_document(file_ref)
                if existing:
                    logger.warning(
                        "Document already in conversation",
                        doc_id=file_ref,
                        status=existing.status.value
                    )
                    ingested_docs.append(existing)
                    continue

                # Fetch document metadata
                doc = await Document.get(file_ref)
                if not doc:
                    logger.error("Document not found", doc_id=file_ref)
                    failed_docs.append({
                        "doc_id": file_ref,
                        "error": "Document not found in storage"
                    })
                    continue

                # Create DocumentState
                doc_state = session.add_document(
                    doc_id=file_ref,
                    name=doc.filename,
                    pages=doc.metadata.get("pages") if doc.metadata else None,
                    size_bytes=doc.size_bytes,
                    mimetype=doc.content_type,
                    status=ProcessingStatus.UPLOADING
                )

                ingested_docs.append(doc_state)

                # 3. Dispatch async processing task
                process_document_task.delay(
                    conversation_id=conversation_id,
                    doc_id=file_ref
                )

                logger.info(
                    "Dispatched processing task",
                    doc_id=file_ref,
                    filename=doc.filename
                )

            except Exception as e:
                logger.error(
                    "Failed to ingest document",
                    doc_id=file_ref,
                    error=str(e),
                    exc_info=True
                )
                failed_docs.append({
                    "doc_id": file_ref,
                    "error": str(e)
                })

        # 4. Save session with new DocumentStates
        await session.save()

        # 5. Build immediate response
        response_message = self._build_response_message(ingested_docs, failed_docs)

        return ToolResult(
            success=True,
            data={
                "status": "processing",
                "message": response_message,
                "documents": [
                    {
                        "doc_id": d.doc_id,
                        "name": d.name,
                        "status": d.status.value,
                        "pages": d.pages
                    }
                    for d in ingested_docs
                ],
                "failed": failed_docs,
                "total": len(file_refs),
                "ingested": len(ingested_docs),
                "failed_count": len(failed_docs)
            }
        )

    def _build_response_message(
        self,
        ingested: List[DocumentState],
        failed: List[Dict[str, Any]]
    ) -> str:
        """Build user-friendly response message"""

        if not ingested and not failed:
            return "No se recibieron documentos."

        parts = []

        if ingested:
            doc_list = ", ".join([
                f"**{d.name}**" + (f" ({d.pages} págs)" if d.pages else "")
                for d in ingested
            ])
            parts.append(f"📄 Recibí: {doc_list}")
            parts.append("Estoy procesando los documentos...")

        if failed:
            parts.append(f"⚠️ No pude procesar {len(failed)} documento(s):")
            for fail in failed[:3]:  # Show first 3
                parts.append(f"  - {fail['doc_id'][:12]}...: {fail['error'][:50]}")

        return "\n".join(parts)


# Register tool
def register():
    """Register tool in MCP registry"""
    from src.mcp.registry import tool_registry
    tool_registry.register(IngestFilesTool())
```

**Tests**: `apps/api/tests/integration/test_ingest_files_tool.py`

```python
import pytest
from unittest.mock import patch, AsyncMock

from src.mcp.tools.ingest_files import IngestFilesTool
from src.models.chat import ChatSession
from src.models.document import Document
from src.models.document_state import ProcessingStatus


@pytest.mark.asyncio
async def test_ingest_files_creates_document_states(db_session, sample_chat_session, sample_document):
    """Test that ingest_files creates DocumentState records"""

    tool = IngestFilesTool()

    with patch("src.mcp.tools.ingest_files.process_document_task") as mock_task:
        result = await tool.execute(
            conversation_id=sample_chat_session.id,
            file_refs=[sample_document.id]
        )

    assert result.success is True
    assert result.data["ingested"] == 1
    assert result.data["failed_count"] == 0

    # Verify DocumentState was created
    session = await ChatSession.get(sample_chat_session.id)
    assert len(session.documents) == 1

    doc_state = session.documents[0]
    assert doc_state.doc_id == sample_document.id
    assert doc_state.name == sample_document.filename
    assert doc_state.status == ProcessingStatus.UPLOADING

    # Verify async task was dispatched
    mock_task.delay.assert_called_once_with(
        conversation_id=sample_chat_session.id,
        doc_id=sample_document.id
    )


@pytest.mark.asyncio
async def test_ingest_files_handles_missing_document(db_session, sample_chat_session):
    """Test error handling for non-existent documents"""

    tool = IngestFilesTool()

    result = await tool.execute(
        conversation_id=sample_chat_session.id,
        file_refs=["non-existent-doc-id"]
    )

    assert result.success is True  # Tool succeeds but reports failure
    assert result.data["ingested"] == 0
    assert result.data["failed_count"] == 1
    assert "not found" in result.data["failed"][0]["error"]


@pytest.mark.asyncio
async def test_ingest_files_skips_duplicates(db_session, sample_chat_session, sample_document):
    """Test that duplicate ingestion is handled gracefully"""

    tool = IngestFilesTool()

    # First ingestion
    await tool.execute(
        conversation_id=sample_chat_session.id,
        file_refs=[sample_document.id]
    )

    # Second ingestion (duplicate)
    with patch("src.mcp.tools.ingest_files.process_document_task") as mock_task:
        result = await tool.execute(
            conversation_id=sample_chat_session.id,
            file_refs=[sample_document.id]
        )

    # Should not dispatch duplicate task
    mock_task.delay.assert_not_called()

    # Session should still have only 1 document
    session = await ChatSession.get(sample_chat_session.id)
    assert len(session.documents) == 1
```

---

## 📋 Tareas (Día 2)

### 2.2 Background Worker: `process_document_task`

**File**: `apps/api/src/services/document_tasks.py`

```python
"""
Background tasks for document processing.

Uses Celery for async execution.
"""

import structlog
from celery import shared_task

from src.models.chat import ChatSession
from src.models.document import Document
from src.models.document_state import ProcessingStatus
from src.services.document_extraction import DocumentExtractionService
from src.core.cache import get_cache

logger = structlog.get_logger()


@shared_task(bind=True, max_retries=3)
def process_document_task(self, conversation_id: str, doc_id: str):
    """
    Process a document: extract text, segment, optionally index.

    Args:
        conversation_id: Chat session ID
        doc_id: Document ID to process

    Flow:
        1. Update status to PROCESSING
        2. Extract text (pypdf / OCR)
        3. Segment into chunks
        4. Cache segments
        5. Update status to READY
    """

    logger.info(
        "Processing document",
        conversation_id=conversation_id,
        doc_id=doc_id,
        task_id=self.request.id
    )

    try:
        # Async wrapper
        import asyncio
        asyncio.run(_process_document_async(conversation_id, doc_id))

    except Exception as exc:
        logger.error(
            "Document processing failed",
            conversation_id=conversation_id,
            doc_id=doc_id,
            error=str(exc),
            exc_info=True
        )

        # Retry or mark as failed
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)  # Retry in 1 min
        else:
            # Max retries reached - mark as failed
            asyncio.run(_mark_document_failed(conversation_id, doc_id, str(exc)))


async def _process_document_async(conversation_id: str, doc_id: str):
    """Async processing logic"""

    # 1. Update status to PROCESSING
    session = await ChatSession.get(conversation_id)
    doc_state = session.get_document(doc_id)

    if not doc_state:
        raise ValueError(f"Document {doc_id} not found in session {conversation_id}")

    doc_state.mark_processing()
    await session.save()

    # 2. Fetch document
    document = await Document.get(doc_id)
    if not document:
        raise ValueError(f"Document {doc_id} not found in storage")

    # 3. Extract text
    extraction_service = DocumentExtractionService()

    extracted_text = await extraction_service.extract_text(
        file_path=document.file_path,
        filename=document.filename
    )

    if not extracted_text:
        raise ValueError("Text extraction returned empty result")

    # 4. Segment text (simple splitting for now, can be enhanced)
    segments = _segment_text(extracted_text, chunk_size=1000)

    logger.info(
        "Text extracted and segmented",
        doc_id=doc_id,
        segments_count=len(segments),
        text_length=len(extracted_text)
    )

    # 5. Cache segments
    cache = get_cache()
    cache_key = f"doc_segments:{doc_id}"

    await cache.set(
        cache_key,
        segments,
        ttl=3600  # 1 hour
    )

    # 6. Update status to READY
    doc_state.mark_ready(segments_count=len(segments))
    await session.save()

    logger.info(
        "Document processing complete",
        doc_id=doc_id,
        status=ProcessingStatus.READY.value
    )


async def _mark_document_failed(conversation_id: str, doc_id: str, error: str):
    """Mark document as FAILED"""
    session = await ChatSession.get(conversation_id)
    doc_state = session.get_document(doc_id)

    if doc_state:
        doc_state.mark_failed(error)
        await session.save()


def _segment_text(text: str, chunk_size: int = 1000) -> List[Dict[str, Any]]:
    """
    Segment text into chunks.

    Simple implementation - can be enhanced with:
    - Sentence boundary detection
    - Overlapping windows
    - Section/paragraph awareness
    """

    segments = []
    words = text.split()

    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size])
        segments.append({
            "index": len(segments),
            "text": chunk,
            "word_count": len(chunk.split())
        })

    return segments
```

---

### 2.3 Tool: `get_relevant_segments`

**File**: `apps/api/src/mcp/tools/get_segments.py`

```python
"""
MCP Tool: Retrieve relevant document segments for RAG.

Replaces direct document text injection with structured retrieval.
"""

import structlog
from typing import List, Optional, Dict, Any

from src.mcp.tools.base import BaseTool, ToolInput, ToolResult
from src.models.chat import ChatSession
from src.models.document_state import ProcessingStatus
from src.core.cache import get_cache

logger = structlog.get_logger()


class GetSegmentsInput(ToolInput):
    """Input schema for get_relevant_segments tool"""
    conversation_id: str
    question: str
    target_docs: Optional[List[str]] = None  # Filter by doc names
    max_segments: int = 5  # Max segments to return


class GetRelevantSegmentsTool(BaseTool):
    """
    Retrieve relevant document segments for a question.

    Flow:
    1. Find documents with status=READY in conversation
    2. Load segments from cache
    3. Score/rank segments by relevance (simple keyword for now)
    4. Return top N segments

    Future enhancements:
    - Vector embeddings for semantic search
    - Re-ranking with cross-encoder
    - Fusion retrieval (keyword + semantic)
    """

    name = "get_relevant_segments"
    description = "Retrieve relevant document segments for RAG"

    async def execute(
        self,
        conversation_id: str,
        question: str,
        target_docs: Optional[List[str]] = None,
        max_segments: int = 5
    ) -> ToolResult:
        """
        Retrieve segments relevant to question.

        Args:
            conversation_id: Chat session ID
            question: User's question
            target_docs: Optional filter by document names
            max_segments: Max segments to return

        Returns:
            List of relevant segments with metadata
        """

        logger.info(
            "Retrieving segments",
            conversation_id=conversation_id,
            question=question[:100],
            target_docs=target_docs
        )

        # 1. Fetch session
        session = await ChatSession.get(conversation_id)
        if not session:
            return ToolResult(
                success=False,
                error=f"Conversation {conversation_id} not found"
            )

        # 2. Filter ready documents
        ready_docs = session.get_ready_documents()

        if target_docs:
            ready_docs = [
                d for d in ready_docs
                if d.name in target_docs or d.doc_id in target_docs
            ]

        if not ready_docs:
            logger.warning(
                "No ready documents found",
                conversation_id=conversation_id,
                total_docs=len(session.documents)
            )
            return ToolResult(
                success=True,
                data={
                    "segments": [],
                    "message": "No hay documentos procesados disponibles.",
                    "total_docs": len(session.documents),
                    "ready_docs": 0
                }
            )

        # 3. Load and score segments
        all_segments = []
        cache = get_cache()

        for doc in ready_docs:
            cache_key = f"doc_segments:{doc.doc_id}"
            segments = await cache.get(cache_key)

            if not segments:
                logger.warning(
                    "Segments not in cache",
                    doc_id=doc.doc_id
                )
                continue

            # Score each segment (simple keyword matching for now)
            for seg in segments:
                score = self._score_segment(seg["text"], question)
                all_segments.append({
                    "doc_id": doc.doc_id,
                    "doc_name": doc.name,
                    "index": seg["index"],
                    "text": seg["text"],
                    "score": score
                })

        # 4. Rank and return top N
        all_segments.sort(key=lambda x: x["score"], reverse=True)
        top_segments = all_segments[:max_segments]

        logger.info(
            "Segments retrieved",
            total_segments=len(all_segments),
            returned=len(top_segments)
        )

        return ToolResult(
            success=True,
            data={
                "segments": top_segments,
                "total_docs": len(ready_docs),
                "total_segments": len(all_segments),
                "returned_segments": len(top_segments)
            }
        )

    def _score_segment(self, text: str, question: str) -> float:
        """
        Simple keyword-based scoring.

        Future: Replace with semantic similarity (embeddings).
        """

        text_lower = text.lower()
        question_lower = question.lower()

        # Extract keywords from question (remove stop words)
        stop_words = {"el", "la", "de", "en", "y", "a", "que", "es", "por", "para"}
        keywords = [
            w for w in question_lower.split()
            if w not in stop_words and len(w) > 2
        ]

        # Count keyword matches
        score = sum(1 for kw in keywords if kw in text_lower)

        return score / max(len(keywords), 1)  # Normalize


# Register tool
def register():
    from src.mcp.registry import tool_registry
    tool_registry.register(GetRelevantSegmentsTool())
```

---

## 📋 Tareas (Día 3)

### 2.4 Integration Tests

**File**: `apps/api/tests/integration/test_document_workflow.py`

```python
"""
Integration test: Complete document workflow.

Tests:
1. Ingest files
2. Wait for processing
3. Retrieve segments
4. Use in chat
"""

import pytest
import asyncio
from unittest.mock import patch

from src.mcp.tools.ingest_files import IngestFilesTool
from src.mcp.tools.get_segments import GetRelevantSegmentsTool
from src.models.document_state import ProcessingStatus


@pytest.mark.asyncio
async def test_complete_document_workflow(
    db_session,
    sample_chat_session,
    sample_document
):
    """Test full workflow: ingest → process → retrieve"""

    # 1. Ingest files
    ingest_tool = IngestFilesTool()

    with patch("src.mcp.tools.ingest_files.process_document_task"):
        ingest_result = await ingest_tool.execute(
            conversation_id=sample_chat_session.id,
            file_refs=[sample_document.id]
        )

    assert ingest_result.success
    assert ingest_result.data["ingested"] == 1

    # 2. Simulate processing completion
    from src.services.document_tasks import _process_document_async

    await _process_document_async(
        conversation_id=sample_chat_session.id,
        doc_id=sample_document.id
    )

    # 3. Retrieve segments
    retrieval_tool = GetRelevantSegmentsTool()

    segments_result = await retrieval_tool.execute(
        conversation_id=sample_chat_session.id,
        question="What is the report about?",
        max_segments=3
    )

    assert segments_result.success
    assert len(segments_result.data["segments"]) > 0

    # Verify segment structure
    segment = segments_result.data["segments"][0]
    assert "doc_id" in segment
    assert "doc_name" in segment
    assert "text" in segment
    assert "score" in segment
```

---

## ✅ Acceptance Criteria

1. [ ] `IngestFilesTool` returns immediate response (< 500ms)
2. [ ] `process_document_task` completes successfully for PDFs
3. [ ] `GetRelevantSegmentsTool` retrieves correct segments
4. [ ] Integration tests pass (end-to-end workflow)
5. [ ] No blocking operations in chat request path
6. [ ] Documentation updated (tool usage in orchestrator)

---

## 🔗 Next Phase

Once Phase 2 is complete:
→ **Phase 3**: Update `streaming_handler.py` to use new tools
