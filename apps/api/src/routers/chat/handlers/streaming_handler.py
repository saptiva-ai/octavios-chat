"""
Streaming Handler - SSE (Server-Sent Events) chat response handler.

This module handles streaming responses for chat messages,
following Single Responsibility Principle.

Responsibilities:
    - Stream chat responses via SSE
    - Handle document context for streaming
    - Manage streaming-specific errors
    - Save streamed responses to database
"""

import os
import json
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional
from datetime import datetime
from asyncio import Queue, create_task, CancelledError

import structlog
from fastapi import BackgroundTasks

from ....core.config import Settings
from ....core.redis_cache import get_redis_cache
from ....schemas.chat import ChatRequest
from ....services.chat_service import ChatService
from ....services.chat_helpers import build_chat_context
from ....services.session_context_manager import SessionContextManager
from ....services.document_service import DocumentService
from ....services.saptiva_client import get_saptiva_client
from ....services.validation_coordinator import validate_document_streaming
from ....services.policy_manager import resolve_policy
from ....services.minio_storage import get_minio_storage
from ....models.document import Document
from ....domain import ChatContext
from ....mcp.tools.ingest_files import IngestFilesTool
from ....mcp.tools.get_segments import GetRelevantSegmentsTool

logger = structlog.get_logger(__name__)


def calculate_dynamic_max_tokens(
    messages: list[dict],
    model_limit: int = 8192,
    min_tokens: int = 500,
    max_tokens: int = 3000,
    safety_margin: int = 100
) -> int:
    """
    Calculate optimal max_tokens based on actual prompt size.

    This prevents context length errors by dynamically adjusting the response
    budget based on how much space the prompt (system + RAG context + user message) takes.

    Args:
        messages: List of message dicts with 'content' key
        model_limit: Total token limit for the model (default: 8192 for Saptiva Turbo)
        min_tokens: Minimum tokens to allow for response (default: 500)
        max_tokens: Maximum tokens to allow for response (default: 3000)
        safety_margin: Extra buffer to prevent edge cases (default: 100)

    Returns:
        Optimal max_tokens value that fits within model limits

    Example:
        messages = [
            {"role": "system", "content": "You are a helpful assistant..."},
            {"role": "user", "content": "What is AI?"}
        ]
        max_tokens = calculate_dynamic_max_tokens(messages)
        # Returns ~7500 if prompt is small, or ~1000 if prompt has large RAG context
    """
    # Estimate tokens from character count
    # GPT-style tokenization: ~1 token per 4 characters (conservative estimate)
    total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
    estimated_prompt_tokens = total_chars // 4

    # Calculate available space for response
    available_tokens = model_limit - estimated_prompt_tokens - safety_margin

    # Clamp to reasonable bounds
    optimal_tokens = max(min_tokens, min(available_tokens, max_tokens))

    logger.debug(
        "Calculated dynamic max_tokens",
        prompt_chars=total_chars,
        estimated_prompt_tokens=estimated_prompt_tokens,
        available_tokens=available_tokens,
        optimal_max_tokens=optimal_tokens,
        model_limit=model_limit
    )

    return optimal_tokens


class StreamingHandler:
    """
    Handles streaming SSE responses for chat messages.

    This class encapsulates all streaming-specific logic,
    following Single Responsibility Principle.
    """

    def __init__(self, settings: Settings):
        """
        Initialize streaming handler.

        Args:
            settings: Application settings
        """
        self.settings = settings

    @staticmethod
    def _build_tools_markdown(has_documents: bool) -> Optional[str]:
        """
        Build a minimal markdown section describing available tools.

        Today we only expose get_relevant_segments when there are documents
        so the LLM knows it can retrieve context for RAG.
        """
        if not has_documents:
            return None

        return (
            "* **get_relevant_segments** — Retrieve relevant document segments for RAG\n"
            "  - Parameters: conversation_id (string), question (string), max_segments (int)\n"
            "  - Use when: User asks about uploaded documents\n"
            "  - conversation_id: use the active chat/session id\n"
            "  - question: user question as-is\n"
            "  - max_segments: default 2"
        )

    async def handle_stream(
        self,
        request: ChatRequest,
        user_id: str,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> AsyncGenerator[dict, None]:
        """
        Handle streaming SSE response for chat request.

        Yields Server-Sent Events with incremental chunks from Saptiva API.

        Args:
            request: ChatRequest from endpoint
            user_id: Authenticated user ID

        Yields:
            dict: SSE events with format {"event": str, "data": str}

        Note:
            Audit commands are NOT supported in streaming mode.
            An error event is yielded if audit is requested.
        """
        try:
            # Build context
            context = build_chat_context(request, user_id, self.settings)

            logger.info(
                "Processing streaming chat request",
                request_id=context.request_id,
                user_id=context.user_id,
                model=context.model
            )

            # Initialize services
            chat_service = ChatService(self.settings)
            cache = await get_redis_cache()

            # Get or create session
            chat_session = await chat_service.get_or_create_session(
                chat_id=context.chat_id,
                user_id=context.user_id,
                first_message=context.message,
                tools_enabled=context.tools_enabled
            )

            context = context.with_session(chat_session.id)

            # Prepare session context (files)
            request_file_ids = list(
                (request.file_ids or []) + (request.document_ids or [])
            )

            # DEBUG: Log session attached_file_ids for RAG troubleshooting
            logger.info(
                "🔍 [RAG DEBUG] Session file context",
                session_id=chat_session.id,
                session_attached_file_ids=getattr(chat_session, 'attached_file_ids', []),
                request_file_ids=request_file_ids,
                timestamp=context.timestamp
            )

            current_file_ids = await SessionContextManager.prepare_session_context(
                chat_session=chat_session,
                request_file_ids=request_file_ids,
                user_id=user_id,
                redis_cache=cache,
                request_id=context.request_id
            )

            # DEBUG: Log resolved file IDs
            logger.info(
                "✅ [RAG DEBUG] Resolved file IDs",
                session_id=chat_session.id,
                current_file_ids=current_file_ids,
                will_use_rag=bool(current_file_ids)
            )

            # Update context with resolved file IDs
            if current_file_ids:
                context = ChatContext(
                    user_id=context.user_id,
                    request_id=context.request_id,
                    timestamp=context.timestamp,
                    chat_id=context.chat_id,
                    session_id=context.session_id,
                    message=context.message,
                    context=context.context,
                    document_ids=current_file_ids,
                    model=context.model,
                    tools_enabled=context.tools_enabled,
                    stream=context.stream,
                    temperature=context.temperature,
                    max_tokens=context.max_tokens,
                    kill_switch_active=context.kill_switch_active
                )

                # NEW: Ingest files using IngestFilesTool (async processing)
                if background_tasks and current_file_ids:
                    try:
                        ingest_tool = IngestFilesTool()
                        result = await ingest_tool.execute(
                            payload={
                                "conversation_id": chat_session.id,
                                "file_refs": current_file_ids
                            },
                            context={"background_tasks": background_tasks}
                        )

                        logger.info(
                            "Document ingestion dispatched",
                            session_id=chat_session.id,
                            file_count=len(current_file_ids),
                            ingested=result.get("ingested", 0),
                            status=result.get("status")
                        )

                        # CRITICAL FIX: Add delay to allow MongoDB write to propagate
                        # The subsequent GetRelevantSegmentsTool call (in streaming logic)
                        # will refetch the session. This delay ensures the write is visible.
                        # 100ms is sufficient for MongoDB consistency (tested with 50ms, being conservative)
                        await asyncio.sleep(0.1)

                        logger.info(
                            "🕐 [RAG DEBUG] Waited for MongoDB write propagation",
                            session_id=chat_session.id,
                            delay_ms=100,
                            timestamp=datetime.utcnow().isoformat()
                        )

                        # ANTI-HALLUCINATION FIX: Wait for documents to be READY
                        # Poll until all documents are processed (max 30 seconds)
                        from ....models.document import Document, DocumentStatus

                        max_wait_seconds = 30
                        poll_interval = 0.5  # 500ms between checks
                        elapsed = 0

                        while elapsed < max_wait_seconds:
                            docs_ready = True
                            for doc_id in current_file_ids:
                                doc = await Document.get(doc_id)
                                if doc and doc.status != DocumentStatus.READY:
                                    docs_ready = False
                                    break

                            if docs_ready:
                                logger.info(
                                    "✅ [RAG ANTI-HALLUCINATION] All documents READY",
                                    session_id=chat_session.id,
                                    elapsed_seconds=round(elapsed, 2),
                                    file_count=len(current_file_ids)
                                )
                                break

                            await asyncio.sleep(poll_interval)
                            elapsed += poll_interval

                        if elapsed >= max_wait_seconds:
                            logger.warning(
                                "⚠️ [RAG ANTI-HALLUCINATION] Timeout waiting for documents",
                                session_id=chat_session.id,
                                timeout_seconds=max_wait_seconds,
                                file_count=len(current_file_ids)
                            )

                        # Optionally: Yield SSE event to inform user
                        # yield {
                        #     "event": "system",
                        #     "data": json.dumps({
                        #         "message": result.get("message", "Processing documents..."),
                        #         "documents": result.get("documents", [])
                        #     })
                        # }

                    except Exception as ingest_exc:
                        logger.error(
                            "Document ingestion failed",
                            session_id=chat_session.id,
                            error=str(ingest_exc),
                            exc_info=True
                        )

            # Add user message
            user_message_metadata = request.metadata.copy() if request.metadata else {}
            if current_file_ids:
                user_message_metadata["file_ids"] = current_file_ids

            user_message = await chat_service.add_user_message(
                chat_session=chat_session,
                content=context.message,
                metadata=user_message_metadata if user_message_metadata else None
            )

            # Check for audit command (NOW supported in streaming!)
            if context.message.strip().startswith("Auditar archivo:"):
                async for event in self._stream_audit_response(
                    chat_service, chat_session, context, user_message
                ):
                    yield event
                return

            # Stream chat response
            async for event in self._stream_chat_response(
                context, chat_service, chat_session, cache, user_message
            ):
                yield event

        except Exception as exc:
            import traceback
            # ISSUE-020: Enhanced error logging with full context
            error_details = {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
                "user_id": user_id,
                "model": request.model if request.model else "default",
                "stream": request.stream if hasattr(request, 'stream') else None
            }

            # Add context fields if available (may not exist if error during context creation)
            if 'context' in locals():
                error_details.update({
                    "chat_id": context.chat_id,
                    "session_id": getattr(context, 'session_id', None),
                    "message_preview": context.message[:100] if context.message else None,
                    "request_id": context.request_id,
                })

            logger.error(
                "🚨 STREAMING CHAT FAILED - CRITICAL ERROR",
                **error_details,
                exc_info=True
            )

            # Also print to stderr for immediate visibility (ISSUE-020: with context)
            print(f"\n{'='*80}")
            print(f"🚨 STREAMING ERROR: {type(exc).__name__}")
            print(f"Message: {str(exc)}")
            print(f"User: {user_id}")
            if 'context' in locals():
                print(f"Chat ID: {context.chat_id}")
                print(f"Model: {context.model}")
                print(f"Message Preview: {context.message[:100] if context.message else 'N/A'}")
            print(f"Traceback:\n{traceback.format_exc()}")
            print(f"{'='*80}\n")

            yield {
                "event": "error",
                "data": json.dumps({
                    "error": type(exc).__name__,
                    "message": str(exc),
                    "details": "Check server logs for full traceback"
                })
            }

    async def _stream_audit_response(
        self,
        chat_service: ChatService,
        chat_session,
        context: ChatContext,
        user_message
    ) -> AsyncGenerator[dict, None]:
        """
        Stream audit validation progress in real-time.

        Args:
            chat_service: ChatService instance
            chat_session: ChatSession model
            context: ChatContext with request data
            user_message: Saved user message model

        Yields:
            SSE events for audit progress
        """
        logger.info(
            "Streaming audit command",
            message=context.message,
            user_id=context.user_id,
            file_ids=context.document_ids
        )

        # Extract filename from command: "Auditar archivo: filename.pdf"
        filename = context.message.strip().replace("Auditar archivo:", "").strip()

        # Find document by filename in document_ids
        document = None
        if context.document_ids and len(context.document_ids) > 0:
            doc_service = DocumentService()
            for file_id in context.document_ids:
                try:
                    doc = await Document.get(file_id)
                    if doc and doc.filename == filename:
                        document = doc
                        break
                except Exception as e:
                    logger.warning(f"Could not load document {file_id}: {e}")

        if not document:
            error_msg = f"❌ No se encontró el archivo: {filename}"
            await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=error_msg,
                model=context.model,
                metadata={"error": "document_not_found"}
            )
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": "document_not_found",
                    "message": error_msg
                })
            }
            return

        # Resolve policy
        try:
            policy = await resolve_policy("auto", document=document)
        except Exception as e:
            logger.error(f"Failed to resolve policy: {e}")
            policy = await resolve_policy("414-std")

        # Materialize PDF - follow pattern from audit_handler.py
        pdf_path = Path(document.minio_key)
        is_temp = False

        if not pdf_path.exists():
            minio_storage = get_minio_storage()
            if minio_storage:
                try:
                    pdf_path, is_temp = minio_storage.materialize_document(
                        document.minio_key,
                        filename=document.filename
                    )
                except Exception as storage_exc:
                    logger.error(
                        "Failed to materialize PDF from MinIO",
                        doc_id=str(document.id),
                        error=str(storage_exc)
                    )
                    error_msg = f"❌ Error al cargar el archivo: {str(storage_exc)}"
                    await chat_service.add_assistant_message(
                        chat_session=chat_session,
                        content=error_msg,
                        model=context.model,
                        metadata={"error": "pdf_materialization_failed"}
                    )
                    yield {
                        "event": "error",
                        "data": json.dumps({
                            "error": "pdf_materialization_failed",
                            "message": error_msg
                        })
                    }
                    return
            else:
                error_msg = "❌ Sistema de almacenamiento no disponible"
                await chat_service.add_assistant_message(
                    chat_session=chat_session,
                    content=error_msg,
                    model=context.model,
                    metadata={"error": "storage_unavailable"}
                )
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": "storage_unavailable",
                        "message": error_msg
                    })
                }
                return

        # Yield metadata event
        yield {
            "event": "meta",
            "data": json.dumps({
                "chat_id": str(chat_session.id),
                "user_message_id": str(user_message.id),
                "model": context.model,
                "audit_streaming": True,
                "document_id": str(document.id),
                "filename": document.filename,
            })
        }

        accumulated_content = []
        last_job_id = None  # Track job_id from validation_complete event

        try:
            # Stream validation progress
            async for audit_event in validate_document_streaming(
                document=document,
                pdf_path=pdf_path,
                client_name=policy.client_name,
                enable_disclaimer=True,
                enable_format=True,
                enable_typography=True,
                enable_grammar=True,
                enable_logo=True,
                enable_color_palette=True,
                enable_entity_consistency=True,
                enable_semantic_consistency=True,
                policy_config=policy.to_compliance_config(),
                policy_id=policy.id,
                policy_name=policy.name,
            ):
                event_type = audit_event.get("type")

                if event_type == "validation_start":
                    content = f"🔍 **Iniciando auditoría de {audit_event['filename']}**\n\n"
                    content += f"Total de auditores: {audit_event['total_auditors']}\n\n"
                    accumulated_content.append(content)

                elif event_type == "fragments_extracted":
                    content = f"✅ Fragmentos extraídos: {audit_event['fragments_count']} ({audit_event['duration_ms']}ms)\n\n"
                    accumulated_content.append(content)

                elif event_type == "auditor_start":
                    content = f"⏳ **[{audit_event['current']}/{audit_event['total_auditors']}] {audit_event['auditor_name']}**\n"
                    accumulated_content.append(content)

                elif event_type == "auditor_complete":
                    findings_count = len(audit_event.get("findings", []))
                    duration = audit_event.get("duration_ms", 0)
                    content = f"✅ Completado - {findings_count} hallazgos ({duration}ms)\n\n"
                    accumulated_content.append(content)

                elif event_type == "auditor_error":
                    error = audit_event.get("error", "Error desconocido")
                    content = f"❌ Error: {error}\n\n"
                    accumulated_content.append(content)

                elif event_type == "validation_complete":
                    # Capture job_id for metadata
                    last_job_id = audit_event.get("job_id")

                    summary = audit_event.get("summary", {})
                    total_findings = summary.get("total_findings", 0)
                    duration = audit_event.get("duration_ms", 0)

                    content = f"\n---\n\n"
                    content += f"## 📊 Resumen de Auditoría\n\n"
                    content += f"**Total de hallazgos:** {total_findings}\n"
                    content += f"**Duración total:** {duration}ms\n\n"

                    findings_by_severity = summary.get("findings_by_severity", {})
                    content += f"**Por severidad:**\n"
                    content += f"- 🔴 Crítico: {findings_by_severity.get('critical', 0)}\n"
                    content += f"- 🟠 Alto: {findings_by_severity.get('high', 0)}\n"
                    content += f"- 🟡 Medio: {findings_by_severity.get('medium', 0)}\n"
                    content += f"- 🟢 Bajo: {findings_by_severity.get('low', 0)}\n\n"

                    content += f"**Job ID:** `{last_job_id}`\n"

                    accumulated_content.append(content)

                # Yield SSE chunk event
                yield {
                    "event": "chunk",
                    "data": json.dumps({
                        "content": accumulated_content[-1],  # Only send the new content
                        "audit_event": audit_event,  # Include full audit event for frontend processing
                    })
                }

            # Save final response
            full_content = "".join(accumulated_content)
            assistant_message = await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=full_content,
                model=context.model,
                metadata={
                    "audit_completed": True,
                    "document_id": str(document.id),
                    "filename": document.filename,
                    "job_id": last_job_id,
                }
            )

            # Yield done event
            yield {
                "event": "done",
                "data": json.dumps({
                    "message_id": str(assistant_message.id),
                    "content": full_content,
                    "model": context.model,
                    "chat_id": str(chat_session.id),
                })
            }

        except Exception as exc:
            logger.error(
                "Audit streaming failed",
                error=str(exc),
                exc_info=True
            )

            error_msg = f"❌ Error durante la auditoría: {str(exc)}"
            await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=error_msg,
                model=context.model,
                metadata={"error": "audit_execution_failed"}
            )

            yield {
                "event": "error",
                "data": json.dumps({
                    "error": "audit_execution_failed",
                    "message": error_msg,
                    "details": str(exc)
                })
            }

        finally:
            # Clean up temporary PDF file
            if is_temp and pdf_path.exists():
                pdf_path.unlink()

    async def _stream_chat_response(
        self,
        context: ChatContext,
        chat_service: ChatService,
        chat_session,
        cache,
        user_message
    ) -> AsyncGenerator[dict, None]:
        """
        Stream chat response from Saptiva API.

        Args:
            context: ChatContext with request data
            chat_service: ChatService instance
            chat_session: ChatSession model
            cache: Redis cache instance
            user_message: User message model with ID

        Yields:
            SSE events with message chunks and completion
        """
        # FIX-001: Wrap entire streaming logic in try-catch for proper error propagation
        try:
            # NEW: Prepare document context for RAG using GetRelevantSegmentsTool
            document_context = None
            doc_warnings = []

            # DEBUG: Log before RAG retrieval
            logger.info(
                "🔍 [RAG DEBUG] Checking if should retrieve segments",
                has_document_ids=bool(context.document_ids),
                document_ids_count=len(context.document_ids) if context.document_ids else 0,
                document_ids=context.document_ids
            )

            if context.document_ids:
                logger.info(
                    "🚀 [RAG DEBUG] Starting GetRelevantSegmentsTool",
                    conversation_id=context.session_id,
                    question_preview=context.message[:100]
                )

                try:
                    # Use new GetRelevantSegmentsTool for semantic retrieval
                    get_segments_tool = GetRelevantSegmentsTool()
                    segments_result = await get_segments_tool.execute(
                        payload={
                            "conversation_id": context.session_id,
                            "question": context.message,
                            "max_segments": 2  # Reduced for token budget optimization
                        }
                    )

                    segments = segments_result.get("segments", [])

                    if segments:
                        # Build context from retrieved segments
                        segment_texts = []
                        for seg in segments:
                            source = f"**{seg['doc_name']}** (relevancia: {seg['score']:.2f})"
                            segment_texts.append(f"{source}\n{seg['text']}")

                        document_context = "\n\n---\n\n".join(segment_texts)

                        logger.info(
                            "Document segments retrieved for RAG",
                            session_id=context.session_id,
                            segments_count=len(segments),
                            ready_docs=segments_result.get("ready_docs", 0),
                            total_docs=segments_result.get("total_docs", 0)
                        )
                    else:
                        # No segments available - documents might be processing
                        message = segments_result.get("message", "")
                        if "procesando" in message.lower() or "processing" in message.lower():
                            warning_msg = "⏳ Los documentos se están procesando. Estarán disponibles en breve."
                            doc_warnings.append(warning_msg)
                            logger.warning(
                                "⚠️ [RAG DEBUG] Documents still processing - warning added",
                                session_id=context.session_id,
                                warning_message=warning_msg,
                                total_docs=segments_result.get("total_docs", 0),
                                ready_docs=segments_result.get("ready_docs", 0),
                                timestamp=datetime.utcnow().isoformat()
                            )

                except Exception as doc_exc:
                    logger.error(
                        "Document segment retrieval failed - continuing without documents",
                        error=str(doc_exc),
                        exc_type=type(doc_exc).__name__,
                        document_ids=context.document_ids,
                        user_id=context.user_id
                    )
                    # Don't fail the entire request - continue without document context
                    doc_warnings.append(
                        f"No se pudieron cargar los documentos adjuntos: {str(doc_exc)[:100]}"
                    )

            # Initialize Saptiva client (singleton managed async factory)
            saptiva_client = await get_saptiva_client()

            # FIX-001: Use centralized prompt registry instead of hardcoded string
            # This ensures consistent Saptiva branding across all models
            from ....core.prompt_registry import get_prompt_registry
            prompt_registry = get_prompt_registry()

            # Build tools markdown when documents are available so the LLM knows about RAG tool
            has_docs_available = bool(
                document_context
                or context.document_ids
                or (locals().get("current_file_ids") and len(locals().get("current_file_ids")) > 0)
            )

            # Resolve system prompt for this model
            system_prompt, model_params = prompt_registry.resolve(
                model=context.model,
                tools_markdown=self._build_tools_markdown(has_documents=has_docs_available),
                channel="chat"
            )

            # Add document context if available
            if document_context:
                system_prompt += f"\n\n**Documentos adjuntos por el usuario:**\n{document_context}"

            logger.info(
                "Resolved system prompt for streaming",
                model=context.model,
                prompt_hash=model_params.get("_metadata", {}).get("system_hash"),
                has_documents=bool(document_context)
            )

            # ISSUE-004: Implement backpressure with producer-consumer pattern
            # Queue with maxsize=10 provides backpressure when client is slow
            event_queue: Queue = Queue(maxsize=10)
            full_response = ""
            producer_error = None

            async def producer():
                """
                Producer task: reads chunks from Saptiva and puts them in queue.

                If queue is full (slow consumer), put() will block, providing backpressure.
                This prevents unbounded memory growth on the server.
                """
                nonlocal full_response, producer_error

                try:
                    logger.info(
                        "Starting Saptiva stream (producer)",
                        model=context.model,
                        user_id=context.user_id,
                        has_document_context=bool(document_context)
                    )

                    # Send metadata event first
                    await event_queue.put({
                        "event": "meta",
                        "data": json.dumps({
                            "chat_id": str(chat_session.id),
                            "user_message_id": str(user_message.id),
                            "model": context.model
                        })
                    })

                    # FIX-001: Use resolved system_prompt (not hardcoded system_message)
                    # Use model_params for temperature/max_tokens (registry overrides context)

                    # Prepare messages for token calculation
                    messages_for_api = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": context.message}
                    ]

                    # Calculate dynamic max_tokens based on actual prompt size
                    dynamic_max_tokens = calculate_dynamic_max_tokens(
                        messages=messages_for_api,
                        model_limit=8192,  # Saptiva Turbo limit
                        min_tokens=500,
                        max_tokens=model_params.get("max_tokens", 3000)
                    )

                    # Estimate prompt size to detect potential overflows
                    total_prompt_chars = sum(len(str(msg.get("content", ""))) for msg in messages_for_api)
                    estimated_prompt_tokens = total_prompt_chars // 4

                    logger.info(
                        "Token budget calculation",
                        prompt_chars=total_prompt_chars,
                        estimated_prompt_tokens=estimated_prompt_tokens,
                        dynamic_max_tokens=dynamic_max_tokens,
                        total_estimated=estimated_prompt_tokens + dynamic_max_tokens,
                        model_limit=8192,
                        will_exceed=estimated_prompt_tokens + dynamic_max_tokens > 8192
                    )

                    # If prompt is too large, reject or truncate
                    if estimated_prompt_tokens > 7500:
                        logger.error(
                            "⚠️ Prompt exceeds safe token limit - request will likely fail",
                            estimated_prompt_tokens=estimated_prompt_tokens,
                            model_limit=8192
                        )

                    # Use non-streaming for RAG to avoid RemoteProtocolError
                    has_rag_context = context.document_ids and len(context.document_ids) > 0

                    if has_rag_context:
                        # Non-streaming mode for RAG (more stable)
                        logger.info(
                            "Using non-streaming mode for RAG",
                            has_documents=True,
                            document_count=len(context.document_ids)
                        )

                        try:
                            response = await saptiva_client.chat_completion(
                                messages=messages_for_api,
                                model=context.model,
                                temperature=model_params.get("temperature", context.temperature),
                                max_tokens=dynamic_max_tokens
                            )
                        except Exception as e:
                            logger.error(
                                "Non-streaming API call failed",
                                error=str(e),
                                error_type=type(e).__name__
                            )
                            raise

                        # Extract full response
                        if response and response.choices and len(response.choices) > 0:
                            choice = response.choices[0]  # This is a Dict, not an object

                            # Access dict keys instead of attributes
                            if isinstance(choice, dict):
                                message = choice.get('message', {})
                                response_content = message.get('content', '') if isinstance(message, dict) else ''
                            else:
                                # Fallback for object-style access (shouldn't happen)
                                message = getattr(choice, 'message', None)
                                response_content = getattr(message, 'content', '') if message else ''

                            response_content = response_content or ""

                            # Update the nonlocal full_response variable
                            full_response = response_content

                            logger.info(
                                "Non-streaming response extracted",
                                response_length=len(full_response),
                                response_preview=full_response[:100] if full_response else "(empty)",
                                choice_keys=list(choice.keys()) if isinstance(choice, dict) else "not_dict"
                            )

                            # Simulate streaming by sending in chunks
                            chunk_size = 50  # Characters per chunk
                            for i in range(0, len(full_response), chunk_size):
                                chunk_text = full_response[i:i + chunk_size]
                                await event_queue.put({
                                    "event": "chunk",
                                    "data": json.dumps({"content": chunk_text})
                                })
                        else:
                            logger.error(
                                "Non-streaming response malformed",
                                response_has_choices=bool(response and response.choices),
                                choices_length=len(response.choices) if response and response.choices else 0
                            )
                            raise ValueError("SAPTIVA API returned response without choices")

                    else:
                        # Streaming mode for normal chat (without RAG)
                        async for chunk in saptiva_client.chat_completion_stream(
                            messages=messages_for_api,
                            model=context.model,
                            temperature=model_params.get("temperature", context.temperature),
                            max_tokens=dynamic_max_tokens
                        ):
                            # Extract content from chunk
                            # choices is a List[Dict] according to SaptivaStreamChunk model
                            content = ""
                            if hasattr(chunk, 'choices') and chunk.choices:
                                choice = chunk.choices[0]  # This is a dict
                                if isinstance(choice, dict):
                                    delta = choice.get('delta', {})
                                    if isinstance(delta, dict):
                                        content = delta.get('content', '')
                                # Fallback for object-style access (shouldn't happen)
                                elif hasattr(choice, 'delta'):
                                    delta = choice.delta
                                    if hasattr(delta, 'content'):
                                        content = delta.content or ''

                            if content:
                                # Backpressure: this blocks if queue is full (maxsize=10)
                                await event_queue.put({
                                    "event": "chunk",
                                    "data": json.dumps({"content": content})
                                })
                                full_response += content

                    # Signal end of stream
                    await event_queue.put(None)

                    logger.info(
                        "Producer completed successfully",
                        response_length=len(full_response)
                    )

                except CancelledError:
                    logger.info("Producer cancelled by consumer")
                    raise
                except Exception as e:
                    logger.error(
                        "Producer error",
                        error=str(e),
                        exc_type=type(e).__name__
                    )
                    producer_error = e
                    # Signal error to consumer
                    await event_queue.put(None)

            # Start producer task
            producer_task = create_task(producer())

            try:
                # Consumer loop: yield events from queue
                while True:
                    event = await event_queue.get()

                    if event is None:  # End signal
                        break

                    yield event

            finally:
                # Cleanup: cancel producer if consumer exits early
                if not producer_task.done():
                    producer_task.cancel()
                    try:
                        await producer_task
                    except CancelledError:
                        logger.info("Producer task cancelled in cleanup")

                # Check if producer had an error
                if producer_error:
                    logger.error(
                        "Producer error detected in cleanup",
                        error=str(producer_error)
                    )
                    raise producer_error

                # Save assistant message
                assistant_message = await chat_service.add_assistant_message(
                    chat_session=chat_session,
                    content=full_response,
                    model=context.model,
                    metadata={
                        "streaming": True,
                        "has_documents": bool(context.document_ids),
                        "document_warnings": doc_warnings if doc_warnings else None
                    }
                )

                # Yield completion event
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "message_id": str(assistant_message.id),
                        "chat_id": str(chat_session.id)
                    })
                }

                # Invalidate cache
                await cache.invalidate_chat_history(chat_session.id)

        # FIX-001: Catch all streaming errors and propagate to frontend
        except Exception as stream_exc:
            logger.error(
                "CRITICAL: Streaming chat failed",
                error=str(stream_exc),
                exc_type=type(stream_exc).__name__,
                model=context.model,
                user_id=context.user_id,
                has_documents=bool(context.document_ids),
                exc_info=True
            )

            # Save error message to database for visibility
            error_content = (
                f"❌ Error al procesar la solicitud: {str(stream_exc)[:200]}\n\n"
                f"Por favor, intenta nuevamente o contacta al equipo de soporte si el error persiste."
            )
            try:
                await chat_service.add_assistant_message(
                    chat_session=chat_session,
                    content=error_content,
                    model=context.model,
                    metadata={
                        "error": True,
                        "error_type": type(stream_exc).__name__,
                        "error_message": str(stream_exc)[:500]
                    }
                )
            except Exception as save_exc:
                logger.error(
                    "Failed to save error message to database",
                    error=str(save_exc),
                    exc_info=True
                )

            # Yield error event to frontend
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": type(stream_exc).__name__,
                    "message": str(stream_exc),
                    "details": "Ocurrió un error al procesar tu solicitud. Por favor, intenta nuevamente."
                })
            }
