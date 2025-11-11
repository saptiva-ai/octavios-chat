"""
Chat API endpoints - Refactored with Design Patterns.

Uses:
- Dataclasses for type-safe DTOs
- Builder Pattern for response construction
- Strategy Pattern for pluggable chat handlers
- Thin Controller Pattern
"""

import asyncio
import os
import time
import json
from datetime import datetime
from typing import Optional, List, AsyncGenerator
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from ..core.config import get_settings, Settings
from ..core.redis_cache import get_redis_cache
from ..core.auth import get_current_user  # P2.BE.3: For audit tool endpoint
from ..core.telemetry import (
    trace_span,
    metrics_collector,
    increment_docs_used,  # OBS-1: New metric
    record_chat_completion_latency,  # OBS-1: New metric
    increment_llm_timeout,  # OBS-1: New metric
)
from ..models.chat import ChatSession as ChatSessionModel, ChatMessage as ChatMessageModel, MessageRole
from ..models.document import Document, DocumentStatus
from ..models.user import User  # P2.BE.3: For audit tool endpoint
from ..models.validation_report import ValidationReport
from ..schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    ChatSessionListResponse,
    ChatSessionUpdateRequest,
    ChatMessage,
    ChatSession
)
from ..schemas.common import ApiResponse
from ..services.text_sanitizer import sanitize_response_content
from ..services.tools import normalize_tools_state
from ..services.chat_service import ChatService
from ..services.history_service import HistoryService
from ..services.chat_helpers import build_chat_context
from ..services.session_context_manager import SessionContextManager
from ..services.validation_coordinator import validate_document
from ..services.policy_manager import resolve_policy
from ..services.minio_storage import get_minio_storage
from ..services.report_generator import generate_audit_report_pdf
from ..services.summary_formatter import generate_executive_summary, format_executive_summary_as_markdown
from pathlib import Path
from datetime import timedelta
from ..domain import (
    ChatContext,
    ChatResponseBuilder,
    SimpleChatStrategy
)
from ..domain.message_handlers import create_handler_chain
# TODO: Fix MCP integration - backend.mcp.protocol doesn't exist
# from backend.mcp.protocol import ToolInvokeContext

logger = structlog.get_logger(__name__)
router = APIRouter()

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}




async def _stream_chat_response(
    request: ChatRequest,
    user_id: str,
    settings: Settings
) -> AsyncGenerator[dict, None]:
    """
    Handle streaming SSE response for chat.

    Yields Server-Sent Events with incremental chunks from Saptiva API.
    """
    from ..services.saptiva_client import get_saptiva_client

    try:
        # Build context
        context = _build_chat_context(request, user_id, settings)

        logger.info(
            "Processing streaming chat request",
            request_id=context.request_id,
            user_id=context.user_id,
            model=context.model
        )

        # Initialize services
        chat_service = ChatService(settings)
        cache = await get_redis_cache()

        # Get or create session
        chat_session = await chat_service.get_or_create_session(
            chat_id=context.chat_id,
            user_id=context.user_id,
            first_message=context.message,
            tools_enabled=context.tools_enabled
        )

        context = context.with_session(chat_session.id)

        # Handle file context (same logic as non-streaming)
        request_file_ids = list((request.file_ids or []) + (request.document_ids or []))
        request_file_ids = list(dict.fromkeys(request_file_ids)) if request_file_ids else []
        session_file_ids = list(getattr(chat_session, 'attached_file_ids', []) or [])

        current_file_ids = request_file_ids if request_file_ids else session_file_ids

        await _wait_until_ready_and_cached(
            current_file_ids,
            user_id=context.user_id,
            redis_client=cache.client
        )

        if request_file_ids and request_file_ids != session_file_ids:
            await chat_session.update({"$set": {
                "attached_file_ids": request_file_ids,
                "updated_at": datetime.utcnow()
            }})

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

        # Add user message
        user_message_metadata = request.metadata.copy() if request.metadata else {}
        if current_file_ids:
            user_message_metadata["file_ids"] = current_file_ids

        user_message = await chat_service.add_user_message(
            chat_session=chat_session,
            content=context.message,
            metadata=user_message_metadata if user_message_metadata else None
        )

        # ====================================================================
        # AUDIT COMMAND DETECTION (STREAMING PATH)
        # ====================================================================
        if context.message.strip().startswith("Auditar archivo:"):
            logger.info(
                "Audit command detected in streaming path",
                message=context.message,
                user_id=user_id,
                file_ids=current_file_ids
            )

            try:
                # Extract filename from message
                filename_from_message = context.message.replace("Auditar archivo:", "").strip()

                # Find matching document from attached files
                target_doc = None
                if current_file_ids:
                    for file_id in current_file_ids:
                        doc = await Document.get(file_id)
                        if doc and doc.filename == filename_from_message:
                            target_doc = doc
                            break

                if not target_doc:
                    error_msg = f"No se encontró el archivo '{filename_from_message}' en los archivos adjuntos."
                    error_assistant_message = await chat_service.add_assistant_message(
                        chat_session=chat_session,
                        content=error_msg,
                        model=context.model,
                        metadata={"error": "file_not_found"}
                    )

                    yield {
                        "event": "meta",
                        "data": json.dumps({
                            "chat_id": context.chat_id or context.session_id,
                            "user_message_id": str(user_message.id),
                            "model": context.model
                        })
                    }
                    yield {
                        "event": "chunk",
                        "data": json.dumps({"content": error_msg})
                    }
                    yield {
                        "event": "done",
                        "data": json.dumps({
                            "chat_id": str(chat_session.id),
                            "message_id": str(error_assistant_message.id),
                            "content": error_msg,
                            "role": "assistant",
                            "model": context.model,
                            "finish_reason": "stop"
                        })
                    }
                    return

                # Validate document status
                if target_doc.status != DocumentStatus.READY:
                    error_msg = f"El archivo '{target_doc.filename}' no está listo para auditoría. Estado actual: {target_doc.status.value}"
                    error_assistant_message = await chat_service.add_assistant_message(
                        chat_session=chat_session,
                        content=error_msg,
                        model=context.model,
                        metadata={"error": "document_not_ready"}
                    )

                    yield {
                        "event": "meta",
                        "data": json.dumps({
                            "chat_id": context.chat_id or context.session_id,
                            "user_message_id": str(user_message.id),
                            "model": context.model
                        })
                    }
                    yield {
                        "event": "chunk",
                        "data": json.dumps({"content": error_msg})
                    }
                    yield {
                        "event": "done",
                        "data": json.dumps({
                            "chat_id": str(chat_session.id),
                            "message_id": str(error_assistant_message.id),
                            "content": error_msg,
                            "role": "assistant",
                            "model": context.model,
                            "finish_reason": "stop"
                        })
                    }
                    return

                # Get PDF path
                pdf_path = Path(target_doc.minio_key)
                temp_pdf_path: Optional[Path] = None

                if not pdf_path.exists():
                    minio_storage = get_minio_storage()
                    try:
                        pdf_path, is_temp = minio_storage.materialize_document(
                            target_doc.minio_key,
                            filename=target_doc.filename,
                        )
                        if is_temp:
                            temp_pdf_path = pdf_path
                    except Exception as storage_exc:
                        error_msg = "No se pudo recuperar el PDF para auditoría."
                        logger.error(
                            "Audit failed: Unable to materialize PDF",
                            doc_id=str(target_doc.id),
                            error=str(storage_exc),
                        )
                        error_assistant_message = await chat_service.add_assistant_message(
                            chat_session=chat_session,
                            content=error_msg,
                            model=context.model,
                            metadata={"error": "pdf_not_found"},
                        )

                        yield {
                            "event": "meta",
                            "data": json.dumps({
                                "chat_id": context.chat_id or context.session_id,
                                "user_message_id": str(user_message.id),
                                "model": context.model
                            })
                        }
                        yield {
                            "event": "chunk",
                            "data": json.dumps({"content": error_msg})
                        }
                        yield {
                            "event": "done",
                            "data": json.dumps({
                                "chat_id": str(chat_session.id),
                                "message_id": str(error_assistant_message.id),
                                "content": error_msg,
                                "role": "assistant",
                                "model": context.model,
                                "finish_reason": "stop"
                            })
                        }
                        return

                # Resolve policy and run validation
                policy = await resolve_policy("auto", document=target_doc)
                report = await validate_document(
                    document=target_doc,
                    pdf_path=pdf_path,
                    client_name=policy.client_name,
                    enable_disclaimer=True,
                    enable_format=True,
                    enable_typography=True,  # Phase 2
                    enable_grammar=True,
                    enable_logo=True,
                    enable_color_palette=True,  # Phase 3
                    enable_entity_consistency=True,  # Phase 4
                    enable_semantic_consistency=True,  # Phase 5 (FINAL)
                    policy_config=policy.to_compliance_config(),
                    policy_id=policy.id,
                    policy_name=policy.name
                )

                # Save validation report to MongoDB
                validation_report = ValidationReport(
                    document_id=str(target_doc.id),
                    user_id=user_id,
                    job_id=report.job_id,
                    status="done" if report.status == "done" else "error",
                    client_name=policy.client_name,
                    auditors_enabled={
                        "disclaimer": True,
                        "format": True,
                        "typography": True,  # Phase 2
                        "grammar": True,
                        "logo": True,
                        "color_palette": True,  # Phase 3
                        "entity_consistency": True,  # Phase 4
                        "semantic_consistency": True,  # Phase 5 (FINAL)
                    },
                    findings=[f.model_dump() for f in (report.findings or [])],
                    summary=report.summary or {},
                    attachments=report.attachments or {},
                )
                await validation_report.insert()

                # Link validation report to document
                await target_doc.update({"$set": {
                    "validation_report_id": str(validation_report.id),
                    "updated_at": datetime.utcnow()
                }})

                # ====================================================
                # Generate PDF Report URL (MinIO or on-demand endpoint)
                # ====================================================
                minio_storage = get_minio_storage()

                if minio_storage:
                    # MinIO is enabled - generate PDF and upload
                    try:
                        logger.info(
                            "Generating and uploading PDF report to MinIO",
                            report_id=str(validation_report.id)
                        )

                        # 1. Generate full PDF report
                        pdf_buffer = await generate_audit_report_pdf(
                            report=validation_report,
                            filename=target_doc.filename,
                            document_name=target_doc.filename
                        )

                        # 2. Upload to MinIO
                        report_key = f"reports/{validation_report.id}_{int(time.time())}.pdf"

                        await minio_storage.upload_file(
                            bucket_name="audit-reports",
                            object_name=report_key,
                            data=pdf_buffer,
                            length=pdf_buffer.getbuffer().nbytes,
                            content_type="application/pdf"
                        )

                        # 3. Get presigned URL (24h expiration)
                        report_url = minio_storage.get_presigned_url(
                            object_name=report_key,
                            bucket="audit-reports",
                            expires=timedelta(hours=24)
                        )

                        # 4. Save URL in ValidationReport
                        validation_report.attachments = {
                            "full_report_pdf": {
                                "url": report_url,
                                "key": report_key,
                                "generated_at": datetime.utcnow().isoformat(),
                                "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                                "storage": "minio"
                            }
                        }
                        await validation_report.save()

                        logger.info(
                            "PDF report uploaded to MinIO successfully",
                            report_id=str(validation_report.id),
                            report_url=report_url,
                            pdf_size=pdf_buffer.getbuffer().nbytes
                        )

                    except Exception as pdf_exc:
                        logger.error(
                            "Failed to generate/upload PDF report to MinIO",
                            error=str(pdf_exc),
                            exc_type=type(pdf_exc).__name__,
                            report_id=str(validation_report.id)
                        )
                        # Fallback to on-demand endpoint
                        report_url = f"/api/reports/audit/{validation_report.id}/download"
                        logger.info(
                            "Falling back to on-demand PDF endpoint",
                            report_id=str(validation_report.id),
                            report_url=report_url
                        )

                else:
                    # MinIO is disabled - use on-demand endpoint
                    report_url = f"/api/reports/audit/{validation_report.id}/download"

                    logger.info(
                        "MinIO disabled, using on-demand PDF endpoint",
                        report_id=str(validation_report.id),
                        report_url=report_url
                    )

                # ====================================================
                # Generate Executive Summary with PDF download link
                # ====================================================
                executive_summary = generate_executive_summary(validation_report)
                formatted_summary = format_executive_summary_as_markdown(
                    summary=executive_summary,
                    filename=target_doc.filename,
                    report_url=report_url  # Always valid (MinIO presigned URL or on-demand endpoint)
                )

                # Save assistant message with summary + metadata
                audit_assistant_message = await chat_service.add_assistant_message(
                    chat_session=chat_session,
                    content=formatted_summary,  # ← Summary instead of full report
                    model=context.model,
                    metadata={
                        "audit": True,
                        "validation_report_id": str(validation_report.id),
                        "findings_count": len(report.findings),
                        "report_pdf_url": report_url,  # ← NEW: Download URL
                        "report_expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat() if report_url else None
                    }
                )

                # Yield audit result as streaming events
                yield {
                    "event": "meta",
                    "data": json.dumps({
                        "chat_id": context.chat_id or context.session_id,
                        "user_message_id": str(user_message.id),
                        "assistant_message_id": str(audit_assistant_message.id),
                        "model": context.model
                    })
                }

                # Stream the formatted summary in chunks (simulate streaming for UX)
                chunk_size = 100
                for i in range(0, len(formatted_summary), chunk_size):
                    chunk = formatted_summary[i:i + chunk_size]
                    yield {
                        "event": "chunk",
                        "data": json.dumps({"content": chunk})
                    }

                yield {
                    "event": "done",
                    "data": json.dumps({
                        "chat_id": str(chat_session.id),
                        "message_id": str(audit_assistant_message.id),
                        "content": formatted_summary,
                        "role": "assistant",
                        "model": context.model,
                        "finish_reason": "stop",
                        "metadata": {
                            "audit": True,
                            "validation_report_id": str(validation_report.id),
                            "report_pdf_url": report_url,
                            "findings_count": len(report.findings)
                        }
                    })
                }

                # Cleanup temp PDF if created
                if temp_pdf_path and temp_pdf_path.exists():
                    try:
                        temp_pdf_path.unlink()
                        logger.info(
                            "Temporary PDF cleaned up after streaming audit",
                            doc_id=str(target_doc.id),
                            temp_path=str(temp_pdf_path)
                        )
                    except Exception as cleanup_exc:
                        logger.warning(
                            "Failed to cleanup temporary audit PDF",
                            error=str(cleanup_exc)
                        )

                return  # Exit generator after audit

            except (StopAsyncIteration, StopIteration):
                # Re-raise generator control flow exceptions
                raise
            except Exception as audit_exc:
                logger.error(
                    "Audit execution failed in streaming path",
                    error=str(audit_exc),
                    exc_type=type(audit_exc).__name__,
                    user_id=user_id
                )
                error_msg = f"Error al ejecutar la auditoría: {str(audit_exc)}"
                error_assistant_message = await chat_service.add_assistant_message(
                    chat_session=chat_session,
                    content=error_msg,
                    model=context.model,
                    metadata={"error": "audit_execution_failed"}
                )

                yield {
                    "event": "meta",
                    "data": json.dumps({
                        "chat_id": context.chat_id or context.session_id,
                        "user_message_id": str(user_message.id),
                        "model": context.model
                    })
                }
                yield {
                    "event": "chunk",
                    "data": json.dumps({"content": error_msg})
                }
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "chat_id": str(chat_session.id),
                        "message_id": str(error_assistant_message.id),
                        "content": error_msg,
                        "role": "assistant",
                        "model": context.model,
                        "finish_reason": "stop"
                    })
                }
                return

        # ====================================================================
        # NORMAL CHAT PATH (NO AUDIT)
        # ====================================================================

        # Yield initial metadata event
        yield {
            "event": "meta",
            "data": json.dumps({
                "chat_id": context.chat_id or context.session_id,
                "user_message_id": str(user_message.id),
                "model": context.model
            })
        }

        # Emit initial chunk with zero-width space to hide typing indicator immediately
        # This gives instant feedback without waiting for Saptiva's first token
        yield {
            "event": "chunk",
            "data": json.dumps({"content": "\u200b"})  # Zero-width space
        }

        # Get Saptiva client and build messages
        saptiva_client = await get_saptiva_client()
        messages = await chat_service.build_message_context(
            chat_session=chat_session,
            current_message=context.message
        )

        # Inject document context if present
        if context.document_ids:
            from ..services.document_service import DocumentService
            doc_texts = await DocumentService.get_document_text_from_cache(
                document_ids=context.document_ids,
                user_id=context.user_id
            )

            if doc_texts:
                doc_context, _, _ = DocumentService.extract_content_for_rag_from_cache(
                    doc_texts=doc_texts,
                    max_chars_per_doc=8000,
                    max_total_chars=16000,
                    max_docs=3
                )

                if doc_context:
                    # Inject context into system message
                    messages[0] = {
                        "role": "system",
                        "content": f"{messages[0].get('content', '')}\n\nContexto de documentos:\n{doc_context}"
                    }

        # Stream response from Saptiva
        accumulated_content = ""
        async for chunk in saptiva_client.chat_completion_or_stream(
            messages=messages,
            model=context.model,
            stream=True,
            temperature=context.temperature or 0.7
        ):
            if chunk.get("type") == "chunk":
                chunk_data = chunk.get("data")  # SaptivaStreamChunk object

                # Access Pydantic model attributes, not dict keys
                if chunk_data and hasattr(chunk_data, 'choices') and len(chunk_data.choices) > 0:
                    delta = chunk_data.choices[0].get("delta", {})
                    content_chunk = delta.get("content", "")

                    if content_chunk:
                        accumulated_content += content_chunk
                        yield {
                            "event": "chunk",
                            "data": json.dumps({"content": content_chunk})
                        }

        # Save assistant message with accumulated content
        assistant_message = await chat_service.add_assistant_message(
            chat_session=chat_session,
            content=accumulated_content,
            model=context.model,
            metadata={}
        )

        # Yield completion event with full ChatResponse structure
        yield {
            "event": "done",
            "data": json.dumps({
                "chat_id": str(chat_session.id),
                "message_id": str(assistant_message.id),
                "content": accumulated_content,
                "role": "assistant",
                "model": context.model,
                "created_at": assistant_message.created_at.isoformat(),
                "tokens": None,
                "latency_ms": None,
                "finish_reason": "stop",
                "tools_used": [],
                "task_id": None,
                "tools_enabled": context.tools_enabled,
                "decision_metadata": {}
            })
        }

        # Invalidate caches
        await cache.invalidate_chat_history(chat_session.id)

    except Exception as e:
        logger.error(
            "Error in streaming chat",
            error=str(e),
            user_id=user_id,
            exc_info=True
        )
        yield {
            "event": "error",
            "data": json.dumps({"error": str(e)})
        }


@router.post("/chat", tags=["chat"])
async def send_chat_message(
    request: ChatRequest,
    http_request: Request,
    response: Response,
    settings: Settings = Depends(get_settings)
):
    """
    Send a chat message and get AI response.

    Refactored using:
    - ChatContext dataclass for type-safe request encapsulation
    - Strategy Pattern for pluggable chat handlers
    - Builder Pattern for declarative response construction

    Handles both new conversations and continuing existing ones.
    Supports streaming via SSE when request.stream = True.
    """

    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    # Check if streaming is requested
    if getattr(request, 'stream', False):
        return EventSourceResponse(
            _stream_chat_response(request, user_id, settings),
            media_type="text/event-stream"
        )

    # Non-streaming path (original implementation)
    start_time = time.time()
    response.headers.update(NO_STORE_HEADERS)

    try:
        # ====================================================================
        # 1. BUILD CONTEXT (using extracted helper)
        # ====================================================================
        context = build_chat_context(request, user_id, settings)

        logger.info(
            "Processing chat request",
            request_id=context.request_id,
            user_id=context.user_id,
            model=context.model,
            has_documents=bool(context.document_ids)
        )

        # ====================================================================
        # 2. INITIALIZE SERVICES
        # ====================================================================
        chat_service = ChatService(settings)
        cache = await get_redis_cache()

        # ====================================================================
        # 3. GET OR CREATE SESSION
        # ====================================================================
        chat_session = await chat_service.get_or_create_session(
            chat_id=context.chat_id,
            user_id=context.user_id,
            first_message=context.message,
            tools_enabled=context.tools_enabled
        )

        # Update context with resolved session
        context = context.with_session(chat_session.id)

        # ====================================================================
        # 4. PREPARE SESSION CONTEXT (files) - using SessionContextManager
        # ====================================================================
        request_file_ids = list(
            (request.file_ids or []) + (request.document_ids or [])
        )

        current_file_ids = await SessionContextManager.prepare_session_context(
            chat_session=chat_session,
            request_file_ids=request_file_ids,
            user_id=user_id,
            redis_cache=cache,
            request_id=context.request_id
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

        # ====================================================================
        # 5. ADD USER MESSAGE
        # ====================================================================
        # 4. Add user message
        # MVP-LOCK: Use metadata from request (contains file_ids AND file info for UI indicator)
        # DEBUG: Log what we received
        logger.info(
            "DEBUG: Received metadata in request",
            has_metadata=request.metadata is not None,
            metadata=request.metadata,
            metadata_keys=list(request.metadata.keys()) if request.metadata else []
        )

        # BUILD METADATA: Include normalized request_file_ids
        # This ensures the ChatMessage stores the correct file_ids
        user_message_metadata = request.metadata.copy() if request.metadata else {}

        # CRITICAL FIX: Add normalized file_ids to metadata
        # The chat service expects file_ids inside metadata.get("file_ids")
        if current_file_ids:
            user_message_metadata["file_ids"] = current_file_ids
            logger.info(
                "Added normalized file_ids to user message metadata",
                file_ids=current_file_ids,
                file_ids_count=len(current_file_ids)
            )

        user_message = await chat_service.add_user_message(
            chat_session=chat_session,
            content=context.message,
            metadata=user_message_metadata if user_message_metadata else None
        )

        # DEBUG: Log what was saved
        logger.info(
            "DEBUG: User message saved",
            message_id=str(user_message.id),
            has_metadata=user_message.metadata is not None,
            saved_metadata=user_message.metadata
        )        # ====================================================================
        # DELEGATE TO HANDLER CHAIN (Chain of Responsibility Pattern)
        # ====================================================================
        # The handler chain will decide how to process the message:
        # 1. AuditCommandHandler - checks for "Auditar archivo:" commands
        # 2. StandardChatHandler - processes normal chat (fallback)

        handler_chain = create_handler_chain()
        handler_result = await handler_chain.handle(
            context=context,
            chat_service=chat_service,
            user_id=user_id,
            chat_session=chat_session,
            user_message=user_message,
            current_file_ids=current_file_ids
        )

        if handler_result:
            # Handler processed the message successfully
            logger.info(
                "Message processed by handler chain",
                strategy=handler_result.strategy_used,
                processing_time_ms=handler_result.processing_time_ms
            )

            # Invalidate caches
            await cache.invalidate_chat_history(chat_session.id)

            # Return response
            return (ChatResponseBuilder()
                .from_processing_result(handler_result)
                .with_metadata("processing_time_ms", (time.time() - start_time) * 1000)
                .build())

        # If no handler processed (should not happen with StandardChatHandler as fallback),
        # fall through to legacy strategy execution below
        logger.warning(
            "No handler processed the message - this should not happen",
            message=context.message[:50],
            session_id=context.session_id
        )

        

        # 5. Select and execute appropriate strategy with timeout protection
        # BE-PERF-2: Apply timeout to prevent hung LLM calls
        llm_timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

        async with trace_span("chat_strategy_execution", {
            "strategy": "simple",
            "session_id": context.session_id,
            "has_documents": bool(context.document_ids),
            "timeout_seconds": llm_timeout
        }):
            # ADR-001: Direct instantiation (factory removed - YAGNI)
            strategy = SimpleChatStrategy(chat_service)

            try:
                result = await asyncio.wait_for(
                    strategy.process(context),
                    timeout=llm_timeout
                )
            except asyncio.TimeoutError:
                # BE-PERF-2: Handle timeout gracefully
                # OBS-1: Record timeout metric
                increment_llm_timeout(context.model)

                logger.warning(
                    "LLM call timeout",
                    chat_id=context.chat_id,
                    session_id=context.session_id,
                    model=context.model,
                    timeout_seconds=llm_timeout,
                    has_documents=bool(context.document_ids)
                )

                # Create friendly timeout response
                timeout_content = (
                    "El análisis tardó más de lo esperado. "
                    "Intenta reformular tu pregunta de forma más específica "
                    "o dividir tu consulta en partes más pequeñas."
                )

                # Save timeout message as assistant response
                timeout_assistant_message = await chat_service.add_assistant_message(
                    chat_session=chat_session,
                    content=timeout_content,
                    model=context.model,
                    metadata={"timeout": True, "timeout_seconds": llm_timeout}
                )

                # Invalidate caches
                await cache.invalidate_chat_history(chat_session.id)

                return (ChatResponseBuilder()
                    .with_content(timeout_content)
                    .with_chat_id(context.chat_id)
                    .with_message_id(str(timeout_assistant_message.id))
                    .with_model(context.model)
                    .with_metadata("timeout", True)
                    .with_metadata("timeout_seconds", llm_timeout)
                    .with_metadata("user_message_id", str(user_message.id))
                    .with_metadata("processing_time_ms", (time.time() - start_time) * 1000)
                    .build())

        # 6. Save assistant message
        assistant_message = await chat_service.add_assistant_message(
            chat_session=chat_session,
            content=result.sanitized_content,
            model=result.metadata.model_used,
            task_id=result.task_id,
            metadata=result.metadata.decision_metadata or {},
            tokens=result.metadata.tokens_used.get("total") if result.metadata.tokens_used else None,
            latency_ms=int(result.metadata.latency_ms) if result.metadata.latency_ms else None
        )

        # Update result with message IDs
        result.metadata.user_message_id = user_message.id
        result.metadata.assistant_message_id = assistant_message.id

        # OBS-1: Record chat completion metrics
        completion_time = (time.time() - start_time)
        has_docs = bool(context.document_ids)
        record_chat_completion_latency(context.model, completion_time, has_docs)

        # OBS-1: Record documents used count
        if has_docs and result.metadata.decision_metadata:
            context_stats = result.metadata.decision_metadata.get("context_stats", {})
            used_docs = context_stats.get("used_docs", 0)
            if used_docs > 0:
                increment_docs_used(context.chat_id, used_docs)

        # OBS-1: Enhanced logging with observability metadata
        logger.info(
            "chat_completed_with_metrics",
            chat_id=context.chat_id,
            session_id=context.session_id,
            model=context.model,
            has_documents=has_docs,
            used_docs=context_stats.get("used_docs", 0) if has_docs and result.metadata.decision_metadata else 0,
            used_chars=context_stats.get("used_chars", 0) if has_docs and result.metadata.decision_metadata else 0,
            completion_time_seconds=completion_time,
            tokens_used=result.metadata.tokens_used.get("total") if result.metadata.tokens_used else 0,
            warnings=result.metadata.decision_metadata.get("document_warnings", []) if result.metadata.decision_metadata else []
        )

        # 7. Invalidate caches
        await cache.invalidate_chat_history(chat_session.id)
        if result.research_triggered:
            await cache.invalidate_research_tasks(chat_session.id)

        # 8. Record metrics
        if result.metadata.tokens_used:
            metrics_collector.record_chat_message(
                model=result.metadata.model_used,
                tokens=result.metadata.tokens_used.get("total", 0),
                duration=(time.time() - start_time)
            )

        # 9. Build and return response using Builder Pattern
        return (ChatResponseBuilder()
            .from_processing_result(result)
            .with_metadata("processing_time_ms", (time.time() - start_time) * 1000)
            .build())

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error processing chat message",
            error=str(e),
            user_id=user_id,
            exc_info=True
        )

        return (ChatResponseBuilder()
            .with_error(f"Failed to process message: {str(e)}")
            .with_metadata("user_id", user_id)
            .build_error(status_code=500))


@router.post("/chat/{chat_id}/escalate", response_model=ApiResponse, tags=["chat"])
async def escalate_to_research(
    chat_id: str,
    response: Response,
    message_id: Optional[str] = None,
    http_request: Request = None,
    settings: Settings = Depends(get_settings)
) -> ApiResponse:
    """
    Escalate a chat conversation to deep research.

    Takes the last message or specified message and creates a deep research task.
    """

    response.headers.update(NO_STORE_HEADERS)

    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    try:
        # P0-DR-KILL-001: Block escalation when kill switch is active
        if settings.deep_research_kill_switch:
            logger.warning(
                "escalation_blocked",
                message="Escalation blocked by kill switch",
                user_id=user_id,
                chat_id=chat_id,
                kill_switch=True
            )
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "error": "Deep Research feature is not available",
                    "error_code": "DEEP_RESEARCH_DISABLED",
                    "message": "Escalation to research is not available. This feature has been disabled.",
                    "kill_switch": True
                }
            )
        # Verify chat session (using HistoryService for consistent validation)
        chat_session = await HistoryService.get_session_with_permission_check(chat_id, user_id)

        current_tools = normalize_tools_state(getattr(chat_session, 'tools_enabled', None))
        if not current_tools.get('deep_research', False):
            metrics_collector.record_tool_call_blocked('deep_research', 'disabled')
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "TOOL_DISABLED",
                    "message": "Deep research is disabled for this conversation",
                    "tool": "deep_research",
                }
            )

        # Get the message to research
        if message_id:
            target_message = await ChatMessageModel.get(message_id)
            if not target_message or target_message.chat_id != chat_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message not found in this chat"
                )
        else:
            # Get the last user message
            target_message = await ChatMessageModel.find(
                ChatMessageModel.chat_id == chat_id,
                ChatMessageModel.role == MessageRole.USER
            ).sort(-ChatMessageModel.created_at).first_or_none()

            if not target_message:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No user message found to escalate"
                )

        # Use Research Coordinator to force deep research
        from ..services.research_coordinator import get_research_coordinator

        coordinator = get_research_coordinator()
        coordinated_response = await coordinator.execute_coordinated_research(
            query=target_message.content,
            user_id=user_id,
            chat_id=chat_id,
            force_research=True,  # Force research
            stream=True,
            allow_deep_research=True
        )

        if coordinated_response["type"] == "deep_research":
            # Add escalation message to chat
            escalation_message = (
                f"🔬 Escalated to deep research: \"{target_message.content[:100]}...\"\n\n"
                f"Research task started with ID: {coordinated_response['task_id']}\n"
                f"Estimated time: {coordinated_response['estimated_time_minutes']} minutes"
            )

            await chat_session.add_message(
                role=MessageRole.ASSISTANT,
                content=escalation_message,
                model="research_coordinator",
                metadata={
                    "escalation": True,
                    "original_message_id": target_message.id,
                    "task_id": coordinated_response["task_id"],
                    "stream_url": coordinated_response.get("stream_url")
                }
            )

            cache = await get_redis_cache()
            await cache.invalidate_chat_history(chat_id)
            await cache.invalidate_research_tasks(chat_id)

            logger.info(
                "Escalated chat to research",
                chat_id=chat_id,
                message_id=target_message.id,
                task_id=coordinated_response["task_id"]
            )

            return ApiResponse(
                success=True,
                message="Successfully escalated to deep research",
                data={
                    "task_id": coordinated_response["task_id"],
                    "stream_url": coordinated_response.get("stream_url"),
                    "estimated_time_minutes": coordinated_response["estimated_time_minutes"]
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to escalate to research"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error escalating to research", error=str(e), chat_id=chat_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to escalate to research"
        )


@router.get("/history/{chat_id}", response_model=ChatHistoryResponse, tags=["chat"])
async def get_chat_history(
    chat_id: str,
    response: Response,
    limit: int = 50,
    offset: int = 0,
    include_system: bool = False,
    include_research_tasks: bool = True,
    http_request: Request = None
) -> ChatHistoryResponse:
    """
    Get chat history for a specific chat session with optional research tasks.
    """

    response.headers.update(NO_STORE_HEADERS)

    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    try:
        # Check cache first
        cache = await get_redis_cache()
        cached_history = await cache.get_chat_history(
            chat_id=chat_id,
            limit=limit,
            offset=offset,
            include_research=include_research_tasks
        )

        if cached_history:
            logger.debug("Returning cached chat history", chat_id=chat_id)
            return ChatHistoryResponse(**cached_history)

        # Verify access using HistoryService
        chat_session = await HistoryService.get_session_with_permission_check(chat_id, user_id)

        # Query messages with filters
        query = ChatMessageModel.find(ChatMessageModel.chat_id == chat_id)

        if not include_system:
            query = query.find(ChatMessageModel.role != MessageRole.SYSTEM)

        # Get total count
        total_count = await query.count()

        # Get messages with pagination
        messages_docs = await query.sort(-ChatMessageModel.created_at).skip(offset).limit(limit).to_list()

        # Get research tasks for this chat if requested
        research_tasks = {}
        if include_research_tasks:
            from ..models.task import Task as TaskModel

            # Find all research tasks associated with this chat
            task_docs = await TaskModel.find(
                TaskModel.chat_id == chat_id,
                TaskModel.task_type == "deep_research"
            ).to_list()

            # Index by task_id for fast lookup
            research_tasks = {task.id: {
                "task_id": task.id,
                "status": task.status.value,
                "progress": task.progress,
                "current_step": task.current_step,
                "total_steps": task.total_steps,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "error_message": task.error_message,
                "input_data": task.input_data,
                "result_data": task.result_data
            } for task in task_docs}

        # Convert to response schema with research task data
        messages = []
        for msg in messages_docs:
            message_data = ChatMessage(
                id=msg.id,
                chat_id=msg.chat_id,
                role=msg.role,
                content=msg.content,
                status=msg.status,
                created_at=msg.created_at,
                updated_at=msg.updated_at,
                metadata=msg.metadata,
                model=msg.model,
                tokens=msg.tokens,
                latency_ms=msg.latency_ms,
                task_id=msg.task_id
            )

            # Enrich with research task data if available
            if msg.task_id and msg.task_id in research_tasks:
                # Add research task data to metadata
                if not message_data.metadata:
                    message_data.metadata = {}
                message_data.metadata["research_task"] = research_tasks[msg.task_id]

            messages.append(message_data)

        has_more = offset + len(messages) < total_count

        logger.info(
            "Retrieved chat history with research tasks",
            chat_id=chat_id,
            message_count=len(messages),
            research_tasks_count=len(research_tasks),
            total_count=total_count,
            user_id=user_id
        )

        response_data = {
            "chat_id": chat_id,
            "messages": [msg.model_dump(mode='json') for msg in messages],
            "total_count": total_count,
            "has_more": has_more
        }

        # Cache the response
        await cache.set_chat_history(
            chat_id=chat_id,
            data=response_data,
            limit=limit,
            offset=offset,
            include_research=include_research_tasks
        )

        return ChatHistoryResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving chat history", error=str(e), chat_id=chat_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history"
        )


@router.get("/sessions", response_model=ChatSessionListResponse, tags=["chat"])
async def get_chat_sessions(
    response: Response,
    limit: int = 20,
    offset: int = 0,
    http_request: Request = None
) -> ChatSessionListResponse:
    """
    Get chat sessions for the authenticated user.
    """

    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    try:
        # Use HistoryService for consistent session retrieval
        result = await HistoryService.get_chat_sessions(
            user_id=user_id,
            limit=limit,
            offset=offset
        )

        logger.info(
            "Retrieved chat sessions",
            user_id=user_id,
            session_count=len(result["sessions"]),
            total_count=result["total_count"]
        )

        return ChatSessionListResponse(
            sessions=result["sessions"],
            total_count=result["total_count"],
            has_more=result["has_more"]
        )

    except Exception as e:
        logger.error("Error retrieving chat sessions", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat sessions"
        )


@router.get("/sessions/{session_id}/research", tags=["chat"])
async def get_session_research_tasks(
    session_id: str,
    response: Response,
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[str] = None,
    http_request: Request = None
):
    """
    Get all research tasks associated with a chat session.
    """

    response.headers.update(NO_STORE_HEADERS)

    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    try:
        # Verify access using HistoryService
        await HistoryService.get_session_with_permission_check(session_id, user_id)

        cache = await get_redis_cache()

        # Check cache first for research tasks list
        cached_tasks = await cache.get_research_tasks(
            session_id=session_id,
            limit=limit,
            offset=offset,
            status_filter=status_filter
        )

        if cached_tasks:
            logger.debug(
                "Returning cached research tasks",
                session_id=session_id,
                limit=limit,
                offset=offset,
                status_filter=status_filter
            )
            return cached_tasks

        # Import here to avoid circular imports
        from ..models.task import Task as TaskModel

        # Build query for research tasks
        query = TaskModel.find(
            TaskModel.chat_id == session_id,
            TaskModel.task_type == "deep_research"
        )

        # Apply status filter if provided
        if status_filter:
            query = query.find(TaskModel.status == status_filter)

        # Get total count
        total_count = await query.count()

        # Get tasks with pagination
        task_docs = await query.sort(-TaskModel.created_at).skip(offset).limit(limit).to_list()

        # Convert to response format
        research_tasks = []
        for task in task_docs:
            research_tasks.append({
                "task_id": task.id,
                "status": task.status.value,
                "progress": task.progress,
                "current_step": task.current_step,
                "total_steps": task.total_steps,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "error_message": task.error_message,
                "input_data": task.input_data,
                "result_data": task.result_data,
                "metadata": task.metadata
            })

        has_more = offset + len(research_tasks) < total_count

        logger.info(
            "Retrieved research tasks for session",
            session_id=session_id,
            task_count=len(research_tasks),
            total_count=total_count,
            user_id=user_id
        )

        response_payload = {
            "session_id": session_id,
            "research_tasks": research_tasks,
            "total_count": total_count,
            "has_more": has_more
        }

        await cache.set_research_tasks(
            session_id=session_id,
            data=response_payload,
            limit=limit,
            offset=offset,
            status_filter=status_filter
        )

        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving research tasks", error=str(e), session_id=session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve research tasks"
        )


@router.patch("/sessions/{chat_id}", response_model=ApiResponse, tags=["chat"])
async def update_chat_session(
    chat_id: str,
    update_request: ChatSessionUpdateRequest,
    http_request: Request,
    response: Response
) -> ApiResponse:
    """
    Update a chat session (rename, pin/unpin).
    """

    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    try:
        # Verify access using HistoryService
        chat_session = await HistoryService.get_session_with_permission_check(chat_id, user_id)

        # Update fields if provided
        update_data = {}
        if update_request.title is not None:
            update_data['title'] = update_request.title
        if update_request.pinned is not None:
            update_data['pinned'] = update_request.pinned

        if update_data:
            update_data['updated_at'] = datetime.utcnow()
            await chat_session.update({"$set": update_data})

        logger.info("Chat session updated",
                   chat_id=chat_id,
                   user_id=user_id,
                   updates=update_data)

        return ApiResponse(
            success=True,
            message="Chat session updated successfully",
            data={"chat_id": chat_id, "updated_fields": list(update_data.keys())}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update chat session",
                    error=str(e),
                    chat_id=chat_id,
                    user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update chat session"
        )


@router.delete("/sessions/{chat_id}", response_model=ApiResponse, tags=["chat"])
async def delete_chat_session(
    chat_id: str,
    http_request: Request,
    response: Response
) -> ApiResponse:
    """
    Delete a chat session and all its messages.
    """

    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    try:
        # Verify access using HistoryService
        chat_session = await HistoryService.get_session_with_permission_check(chat_id, user_id)

        cache = await get_redis_cache()

        # Delete all messages in the chat
        await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()

        # Delete the chat session
        await chat_session.delete()

        await cache.invalidate_all_for_chat(chat_id)

        logger.info("Deleted chat session", chat_id=chat_id, user_id=user_id)

        return ApiResponse(
            success=True,
            message="Chat session deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting chat session", error=str(e), chat_id=chat_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat session"
        )


@router.post("/chat/tools/audit-file", response_model=ChatMessage, tags=["chat", "tools"])
async def invoke_audit_file_tool(
    doc_id: str,
    chat_id: str,
    policy_id: str = "auto",
    current_user: User = Depends(get_current_user),
    http_request: Request = None,
    response: Response = None,
):
    """
    Invoke audit_file tool: validate document and post result as chat message.

    **P2.BE.3**: New endpoint to execute audit from chat.

    This endpoint is called when user clicks "Auditar Archivo" in chat UI.
    It runs validation and posts the result as an assistant message in the chat.

    Args:
        doc_id: Document ID to audit
        chat_id: Chat session ID where result will be posted
        policy_id: Policy to apply (default: "auto")
        current_user: Authenticated user

    Returns:
        ChatResponse with the created audit message

    Example:
        POST /api/chat/tools/audit-file
        {
          "doc_id": "abc123",
          "chat_id": "chat789",
          "policy_id": "auto"
        }

        Response:
        {
          "chat_id": "chat789",
          "message": {
            "id": "msg-456",
            "role": "assistant",
            "content": "✅ Auditoría completada...",
            "validation_report_id": "val-report-123",
            "metadata": { ... }
          },
          "status": "success"
        }
    """
    if response:
        response.headers.update(NO_STORE_HEADERS)

    user_id = str(current_user.id)
    request_id = getattr(http_request.state, "request_id", str(uuid4())) if http_request else str(uuid4())

    logger.info(
        "Audit file tool invoked from chat",
        doc_id=doc_id,
        chat_id=chat_id,
        user_id=user_id,
        policy_id=policy_id,
    )

    try:
        registry = getattr(http_request.app.state, "mcp_registry", None) if http_request else None
        invoke_payload = {
            "doc_id": doc_id,
            "chat_id": chat_id,
            "policy_id": policy_id,
        }

        # Execute audit tool
        result_payload = None

        if registry:
            tool_response = await registry.invoke(
                tool_name="audit_file",
                payload=invoke_payload,
                context={
                    "request_id": request_id,
                    "user_id": user_id,
                    "session_id": chat_id,
                    "trace_id": http_request.headers.get("x-trace-id") if http_request else None,
                    "source": "chat-endpoint",
                },
            )

            if not tool_response.ok or not tool_response.output:
                detail = tool_response.error.message if tool_response.error else "Audit failed"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=detail,
                )
            result_payload = tool_response.output
        else:
            from ..services.tools import execute_audit_file_tool

            result_payload = await execute_audit_file_tool(
                doc_id=doc_id,
                user_id=user_id,
                chat_id=chat_id,
                policy_id=policy_id,
            )

        success_flag = result_payload.get("success", True)

        if not success_flag:
            logger.error(
                "Audit tool execution failed",
                doc_id=doc_id,
                chat_id=chat_id,
                error=result_payload.get("error"),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result_payload.get("error", "Audit failed"),
            )

        # Get the created message
        message_id = result_payload["message_id"]
        message = await ChatMessageModel.get(message_id)

        if not message:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Audit completed but message not found",
            )

        # Build response

        chat_message = ChatMessage(
            id=message.id,
            chat_id=message.chat_id,
            role=message.role,
            content=message.content,
            status=message.status,
            created_at=message.created_at,
            updated_at=message.updated_at,
            file_ids=message.file_ids,
            files=message.files,
            schema_version=message.schema_version,
            metadata=message.metadata,
            validation_report_id=message.validation_report_id,
            model=message.model,
            tokens=message.tokens,
            latency_ms=message.latency_ms,
            task_id=message.task_id,
        )

        logger.info(
            "Audit tool completed successfully",
            doc_id=doc_id,
            chat_id=chat_id,
            message_id=message_id,
            validation_report_id=result_payload.get("validation_report_id"),
            total_findings=result_payload.get("total_findings"),
        )

        return chat_message

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Audit tool invocation failed",
            doc_id=doc_id,
            chat_id=chat_id,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audit tool failed: {exc}",
        )
