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

logger = structlog.get_logger(__name__)
router = APIRouter()

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _format_validation_report_as_markdown(report, filename: str) -> str:
    """
    Format a validation report as markdown for chat display.

    Args:
        report: Validation report object with findings and summary
        filename: Name of the audited file

    Returns:
        Formatted markdown string
    """
    lines = []

    # Header
    lines.append(f"## 📊 Reporte de Auditoría: {filename}\n")

    # Summary section
    summary = report.summary or {}
    total_findings = len(report.findings)

    lines.append("### ✅ Resumen\n")
    lines.append(f"- **Total de hallazgos**: {total_findings}")

    if "policy_name" in summary:
        lines.append(f"- **Política aplicada**: {summary['policy_name']}")

    if "disclaimer_coverage" in summary:
        coverage = summary["disclaimer_coverage"] * 100
        lines.append(f"- **Cobertura de disclaimers**: {coverage:.1f}%")

    # Findings by severity
    if "findings_by_severity" in summary:
        findings_by_sev = summary["findings_by_severity"]
        if findings_by_sev:
            lines.append(f"\n**Hallazgos por severidad:**")
            for severity, count in findings_by_sev.items():
                emoji = "🔴" if severity == "high" else "🟡" if severity == "medium" else "🟢"
                lines.append(f"  - {emoji} {severity.capitalize()}: {count}")

    # Detailed findings
    if report.findings:
        lines.append(f"\n### 📋 Hallazgos Detallados\n")

        for i, finding in enumerate(report.findings, 1):
            # Handle both Pydantic objects and dicts
            if hasattr(finding, 'severity'):
                # Pydantic Finding object
                severity = finding.severity
                issue = finding.issue
                category = finding.category
                rule = finding.rule
                location = finding.location
                suggestion = finding.suggestion
            else:
                # Dictionary (fallback)
                severity = finding.get("severity", "medium")
                issue = finding.get("issue", "Sin descripción")
                category = finding.get("category", "N/A")
                rule = finding.get("rule", "N/A")
                location = finding.get("location")
                suggestion = finding.get("suggestion")

            # Emoji based on severity
            severity_emoji = {
                "critical": "🔴",
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢"
            }.get(severity, "🔵")

            lines.append(f"**{i}. {severity_emoji} {issue}**")

            # Category and rule
            lines.append(f"   - **Categoría**: {category}")
            lines.append(f"   - **Regla**: {rule}")

            # Location
            if location:
                if hasattr(location, 'page'):
                    page = location.page
                else:
                    page = location.get("page") if isinstance(location, dict) else None

                if page:
                    lines.append(f"   - **Ubicación**: Página {page}")

            # Suggestion
            if suggestion:
                lines.append(f"   - **Sugerencia**: {suggestion}")

            lines.append("")  # Empty line between findings
    else:
        lines.append(f"\n### ✅ Sin Hallazgos\n")
        lines.append("El documento cumple con todas las validaciones configuradas.")

    return "\n".join(lines)


async def _is_ready_and_cached(
    file_id: str,
    user_id: str,
    redis_client
) -> bool:
    """Check if a document belongs to the user, is READY, and has cached text."""

    if not file_id:
        return False

    try:
        document = await Document.get(file_id)
    except Exception as exc:
        logger.warning(
            "wait_ready_document_lookup_failed",
            file_id=file_id,
            error=str(exc)
        )
        return False

    if not document or document.user_id != user_id:
        return False

    if document.status != DocumentStatus.READY:
        return False

    redis_key = f"doc:text:{file_id}"

    try:
        cached_value = await redis_client.get(redis_key)
    except Exception as exc:
        logger.warning(
            "wait_ready_redis_lookup_failed",
            file_id=file_id,
            error=str(exc)
        )
        return False

    return bool(cached_value)


async def _wait_until_ready_and_cached(
    file_ids: List[str],
    user_id: str,
    redis_client,
    max_wait_ms: int = 1200,
    step_ms: int = 150
) -> None:
    """Best-effort wait for documents to reach READY status and have cached text."""

    if not file_ids:
        return

    unique_ids = [fid for fid in dict.fromkeys(file_ids) if fid]
    if not unique_ids:
        return

    waited_ms = 0
    missing: List[str] = unique_ids

    while waited_ms <= max_wait_ms:
        current_missing: List[str] = []

        for fid in unique_ids:
            ready = await _is_ready_and_cached(fid, user_id, redis_client)
            if not ready:
                current_missing.append(fid)

        if not current_missing:
            if waited_ms > 0:
                logger.info(
                    "wait_ready_completed",
                    file_ids=unique_ids,
                    waited_ms=waited_ms
                )
            return

        await asyncio.sleep(step_ms / 1000)
        waited_ms += step_ms
        missing = current_missing

    if missing:
        logger.info(
            "wait_ready_timeout",
            missing_file_ids=missing,
            waited_ms=waited_ms,
            total_ids=len(unique_ids)
        )


def _build_chat_context(
    request: ChatRequest,
    user_id: str,
    settings: Settings
) -> ChatContext:
    """
    Build ChatContext from request.

    Encapsulates all request data into immutable dataclass.

    MVP BE-1: Default to 'Saptiva Turbo' (case-sensitive).
    Stream flag defaults to False for non-streaming responses.
    """
    return ChatContext(
        user_id=user_id,
        request_id=str(uuid4()),
        timestamp=datetime.utcnow(),
        chat_id=request.chat_id,
        session_id=None,  # Will be resolved during processing
        message=request.message,
        context=request.context,
        document_ids=(request.file_ids or []) + (request.document_ids or []) if (request.file_ids or request.document_ids) else None,
        model=request.model or "Saptiva Turbo",  # BE-1: Case-sensitive default
        tools_enabled=normalize_tools_state(request.tools_enabled),
        stream=getattr(request, 'stream', False),  # BE-1: Streaming disabled by default
        temperature=getattr(request, 'temperature', None),
        max_tokens=getattr(request, 'max_tokens', None),
        kill_switch_active=settings.deep_research_kill_switch
    )


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
        # 1. Build immutable context from request
        context = _build_chat_context(request, user_id, settings)

        logger.info(
            "Processing chat request",
            request_id=context.request_id,
            user_id=context.user_id,
            model=context.model,
            has_documents=bool(context.document_ids)
        )

        # 2. Initialize services
        chat_service = ChatService(settings)
        cache = await get_redis_cache()

        # 3. Get or create session
        chat_session = await chat_service.get_or_create_session(
            chat_id=context.chat_id,
            user_id=context.user_id,
            first_message=context.message,
            tools_enabled=context.tools_enabled
        )

        # Update context with resolved session
        context = context.with_session(chat_session.id)

        # FILE CONTEXT PERSISTENCE: Keep only the latest message's attachments
        request_file_ids = list((request.file_ids or []) + (request.document_ids or []))
        # Normalize request files to preserve order but remove duplicates
        request_file_ids = list(dict.fromkeys(request_file_ids)) if request_file_ids else []
        session_file_ids = list(getattr(chat_session, 'attached_file_ids', []) or [])

        if request_file_ids:
            # New message provides files → use them and overwrite session context
            current_file_ids = request_file_ids
        else:
            # No files in request → reuse context from previous message (if any)
            current_file_ids = session_file_ids

        # OBS-2: Log post-normalización en backend
        logger.info(
            "message_normalized",
            text_len=len(request.message or ""),
            file_ids_count=len(current_file_ids),
            file_ids=current_file_ids,
            request_file_ids=request_file_ids,
            session_file_ids=session_file_ids,
            nonce=context.request_id[:8]
        )

        await _wait_until_ready_and_cached(
            current_file_ids,
            user_id=context.user_id,
            redis_client=cache.client
        )

        # Update session's attached_file_ids when new files are provided
        if request_file_ids and request_file_ids != session_file_ids:
            await chat_session.update({"$set": {
                "attached_file_ids": request_file_ids,
                "updated_at": datetime.utcnow()
            }})
            chat_session.attached_file_ids = request_file_ids
            logger.info(
                "Updated session attached_file_ids",
                chat_id=chat_session.id,
                file_count=len(request_file_ids),
                replaced_previous=bool(session_file_ids)
            )

        # Update context with ALL accumulated file IDs (request + session)
        if current_file_ids:
            context = ChatContext(
                user_id=context.user_id,
                request_id=context.request_id,
                timestamp=context.timestamp,
                chat_id=context.chat_id,
                session_id=context.session_id,
                message=context.message,
                context=context.context,
                document_ids=current_file_ids,  # Latest files (new or reused)
                model=context.model,
                tools_enabled=context.tools_enabled,
                stream=context.stream,
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                kill_switch_active=context.kill_switch_active
            )

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
        )

        # ====================================================================
        # AUDIT COMMAND DETECTION: Check if user wants to audit a file
        # ====================================================================
        # DEBUG: Log message before audit detection
        logger.info(
            "DEBUG: Before audit detection",
            raw_message=context.message,
            stripped_message=context.message.strip(),
            starts_with_audit=context.message.strip().startswith("Auditar archivo:"),
            message_length=len(context.message),
            first_20_chars=context.message[:20] if len(context.message) >= 20 else context.message
        )

        if context.message.strip().startswith("Auditar archivo:"):
            logger.info(
                "Audit command detected",
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
                    logger.warning(
                        "Audit failed: file not found",
                        filename=filename_from_message,
                        available_files=current_file_ids
                    )

                    # Save error message
                    error_assistant_message = await chat_service.add_assistant_message(
                        chat_session=chat_session,
                        content=error_msg,
                        model=context.model,
                        metadata={"error": "file_not_found"}
                    )

                    # Return error response
                    elapsed_time = (time.time() - start_time) * 1000
                    return (ChatResponseBuilder()
                        .with_chat_id(str(chat_session.id))
                        .with_message(error_msg)
                        .with_model(context.model)
                        .with_message_id(str(error_assistant_message.id))
                        .with_latency(elapsed_time)
                        .with_metadata("user_message_id", str(user_message.id))
                        .build())

                # Validate document status
                if target_doc.status != DocumentStatus.READY:
                    error_msg = f"El archivo '{target_doc.filename}' no está listo para auditoría. Estado actual: {target_doc.status.value}"
                    logger.warning(
                        "Audit failed: document not ready",
                        doc_id=str(target_doc.id),
                        status=target_doc.status.value
                    )

                    error_assistant_message = await chat_service.add_assistant_message(
                        chat_session=chat_session,
                        content=error_msg,
                        model=context.model,
                        metadata={"error": "document_not_ready"}
                    )

                    elapsed_time = (time.time() - start_time) * 1000
                    return (ChatResponseBuilder()
                        .with_chat_id(str(chat_session.id))
                        .with_message(error_msg)
                        .with_model(context.model)
                        .with_message_id(str(error_assistant_message.id))
                        .with_latency(elapsed_time)
                        .with_metadata("user_message_id", str(user_message.id))
                        .build())

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
                            minio_key=target_doc.minio_key,
                            error=str(storage_exc),
                        )

                        error_assistant_message = await chat_service.add_assistant_message(
                            chat_session=chat_session,
                            content=error_msg,
                            model=context.model,
                            metadata={"error": "pdf_not_found"},
                        )

                        elapsed_time = (time.time() - start_time) * 1000
                        return (ChatResponseBuilder()
                            .with_chat_id(str(chat_session.id))
                            .with_message(error_msg)
                            .with_model(context.model)
                            .with_message_id(str(error_assistant_message.id))
                            .with_latency(elapsed_time)
                            .with_metadata("user_message_id", str(user_message.id))
                            .build())

                logger.info(
                    "PDF path resolved for audit",
                    doc_id=str(target_doc.id),
                    pdf_path=str(pdf_path),
                    source="temp" if temp_pdf_path else "local",
                )

                try:
                    # Resolve policy (use auto-detection)
                    policy = await resolve_policy("auto", document=target_doc)

                    # Run validation
                    logger.info(
                        "Running validation for audit command",
                        doc_id=str(target_doc.id),
                        filename=target_doc.filename,
                        policy_id=policy.id
                    )

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
                        findings=[f.model_dump() for f in report.findings],
                        summary=report.summary,
                        attachments=report.attachments,
                    )

                    await validation_report.insert()

                    # Link validation report to document
                    await target_doc.update({"$set": {
                        "validation_report_id": str(validation_report.id),
                        "updated_at": datetime.utcnow()
                    }})

                    logger.info(
                        "Validation report saved",
                        report_id=str(validation_report.id),
                        doc_id=str(target_doc.id),
                        findings_count=len(report.findings)
                    )

                    # Format report as markdown
                    formatted_report = _format_validation_report_as_markdown(report, target_doc.filename)

                    # V2: Upload audit report to MinIO
                    minio_report_path = None
                    try:
                        minio_storage = get_minio_storage()
                        minio_report_path = minio_storage.upload_audit_report(
                            user_id=user_id,
                            report_id=str(validation_report.id),
                            report_content=formatted_report,
                            chat_id=str(chat_session.id),
                            document_id=str(target_doc.id),
                            metadata={
                                "filename": target_doc.filename,
                                "findings_count": str(len(report.findings)),
                                "policy": policy.name,
                            }
                        )

                        logger.info(
                            "Audit report uploaded to MinIO",
                            report_id=str(validation_report.id),
                            minio_path=minio_report_path
                        )

                    except Exception as minio_exc:
                        logger.error(
                            "Failed to upload audit report to MinIO",
                            report_id=str(validation_report.id),
                            error=str(minio_exc)
                        )
                        # Don't fail the request - report is still in MongoDB

                    # Save assistant message with formatted report
                    audit_assistant_message = await chat_service.add_assistant_message(
                        chat_session=chat_session,
                        content=formatted_report,
                        model=context.model,
                        metadata={
                            "audit": True,
                            "document_id": str(target_doc.id),
                            "validation_report_id": str(validation_report.id),
                            "findings_count": len(report.findings),
                            "minio_report_path": minio_report_path,
                        }
                    )

                    logger.info(
                        "Audit completed via chat",
                        doc_id=str(target_doc.id),
                        findings_count=len(report.findings),
                        assistant_message_id=str(audit_assistant_message.id)
                    )

                    # Return formatted response (bypass LLM)
                    elapsed_time = (time.time() - start_time) * 1000
                    return (ChatResponseBuilder()
                        .with_chat_id(str(chat_session.id))
                        .with_message(formatted_report)
                        .with_model(context.model)
                        .with_message_id(str(audit_assistant_message.id))
                        .with_latency(elapsed_time)
                        .with_metadata("user_message_id", str(user_message.id))
                        .with_metadata("audit", True)
                        .with_metadata("validation_report_id", str(validation_report.id))
                        .build())
                finally:
                    if temp_pdf_path and temp_pdf_path.exists():
                        try:
                            temp_pdf_path.unlink()
                            logger.debug(
                                "Temporary PDF cleaned up after chat audit",
                                doc_id=str(target_doc.id),
                                pdf_path=str(temp_pdf_path),
                            )
                        except Exception as cleanup_exc:
                            logger.warning(
                                "Failed to cleanup temporary audit PDF",
                                doc_id=str(target_doc.id),
                                pdf_path=str(temp_pdf_path),
                                error=str(cleanup_exc),
                            )

            except Exception as audit_exc:
                logger.error(
                    "Audit command failed",
                    error=str(audit_exc),
                    exc_info=True
                )

                error_msg = f"Error al ejecutar la auditoría: {str(audit_exc)}"
                error_assistant_message = await chat_service.add_assistant_message(
                    chat_session=chat_session,
                    content=error_msg,
                    model=context.model,
                    metadata={"error": "audit_execution_failed"}
                )

                elapsed_time = (time.time() - start_time) * 1000
                return (ChatResponseBuilder()
                    .with_chat_id(str(chat_session.id))
                    .with_message(error_msg)
                    .with_model(context.model)
                    .with_message_id(str(error_assistant_message.id))
                    .with_latency(elapsed_time)
                    .with_metadata("user_message_id", str(user_message.id))
                    .with_metadata("error", "audit_execution_failed")
                    .build())

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
    from ..services.tools import execute_audit_file_tool

    if response:
        response.headers.update(NO_STORE_HEADERS)

    user_id = str(current_user.id)

    logger.info(
        "Audit file tool invoked from chat",
        doc_id=doc_id,
        chat_id=chat_id,
        user_id=user_id,
        policy_id=policy_id,
    )

    try:
        # Execute audit tool
        result = await execute_audit_file_tool(
            doc_id=doc_id,
            user_id=user_id,
            chat_id=chat_id,
            policy_id=policy_id,
        )

        if not result["success"]:
            logger.error(
                "Audit tool execution failed",
                doc_id=doc_id,
                chat_id=chat_id,
                error=result.get("error"),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Audit failed"),
            )

        # Get the created message
        message_id = result["message_id"]
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
            validation_report_id=result.get("validation_report_id"),
            total_findings=result.get("total_findings"),
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
