"""
Message Endpoints - HTTP endpoints for chat message operations.

This module contains endpoints related to sending and processing chat messages.

Endpoints:
    POST /chat - Send chat message (streaming or non-streaming)
    POST /chat/{chat_id}/escalate - Escalate conversation to research mode

Responsibilities:
    - Handle HTTP request/response for chat messages
    - Delegate to handlers (streaming or message handlers)
    - Build responses with ChatResponseBuilder
"""

import os
import time
from datetime import datetime
from typing import Dict

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, BackgroundTasks
from sse_starlette.sse import EventSourceResponse

from ....core.config import get_settings, Settings
from ....core.redis_cache import get_redis_cache
from ....core.telemetry import trace_span, increment_llm_timeout
from ....schemas.chat import ChatRequest, ChatResponse
from ....schemas.common import ApiResponse
from ....services.chat_service import ChatService
from ....services.chat_helpers import build_chat_context
from ....services.tool_execution_service import ToolExecutionService
from ....services.session_context_manager import SessionContextManager
from ....domain import ChatContext, ChatResponseBuilder
from ....domain.message_handlers import create_handler_chain
from ..handlers import StreamingHandler

logger = structlog.get_logger(__name__)
router = APIRouter()

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@router.post("/chat", tags=["chat"])
async def send_chat_message(
    request: ChatRequest,
    http_request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings)
):
    """
    Send a chat message and get AI response.

    Refactored using:
    - ChatContext dataclass for type-safe request encapsulation
    - Chain of Responsibility for message handling
    - Strategy Pattern for pluggable chat handlers
    - Builder Pattern for declarative response construction

    Handles both new conversations and continuing existing ones.
    Supports streaming via SSE when request.stream = True.
    """
    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    # ========================================================================
    # STREAMING PATH
    # ========================================================================
    # WORKAROUND: Force non-streaming when documents are attached
    # This ensures document context is properly loaded via SimpleChatStrategy
    # until Qdrant indexing is fully operational for streaming RAG
    file_ids = getattr(request, 'file_ids', None) or []
    has_documents = len(file_ids) > 0

    if getattr(request, 'stream', False):
        if has_documents:
            # Force non-streaming for document-based queries
            # (until Qdrant RAG streaming is fully operational)
            logger.info(
                "Forcing non-streaming mode",
                reason="attached_documents",
                file_ids=request.file_ids,
                user_id=user_id
            )
            request.stream = False

        # Check Accept header for SSE streaming
        accept_header = http_request.headers.get("accept", "")
        if "text/event-stream" in accept_header:
            streaming_handler = StreamingHandler(settings)
            return EventSourceResponse(
                streaming_handler.handle_stream(request, user_id, background_tasks),
                media_type="text/event-stream"
            )
        else:
            # If the client did not request SSE, fall back to non-streaming JSON
            request.stream = False

    # ========================================================================
    # NON-STREAMING PATH
    # ========================================================================
    start_time = time.time()
    response.headers.update(NO_STORE_HEADERS)

    try:
        # 1. Build context
        context = build_chat_context(request, user_id, settings)

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

        context = context.with_session(chat_session.id)

        # 4. Prepare session context (files)
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

        # 🚨 CRITICAL FIX: Prevent Stale Read after file adoption
        # Even though we just adopted files and committed to DB, MongoDB read replicas
        # may not reflect the write yet (eventual consistency).
        # SOLUTION: Use request_file_ids directly (in-memory) instead of trusting DB
        effective_document_ids = current_file_ids  # Start with what DB says

        if request_file_ids and len(request_file_ids) > 0:
            # FORCE MERGE: Ensure files from request are ALWAYS in context
            # This bypasses DB latency/stale reads
            effective_document_ids = list(set(effective_document_ids + request_file_ids))

            logger.info(
                "🔒 [STALE READ FIX] Using request file_ids directly in context",
                request_file_ids=request_file_ids,
                db_file_ids=current_file_ids,
                effective_file_ids=effective_document_ids,
                nonce=context.request_id[:8]
            )

        # Update context with resolved file IDs
        # BUGFIX: Always update context, even if current_file_ids is empty list
        # Empty list [] is falsy in Python, which prevented context update
        context = ChatContext(
            user_id=context.user_id,
            request_id=context.request_id,
            timestamp=context.timestamp,
            chat_id=context.chat_id,
            session_id=context.session_id,
            message=context.message,
            context=context.context,
            document_ids=effective_document_ids,  # ✅ USE IN-MEMORY FORCED LIST
            tool_results={},  # Will be populated below
            model=context.model,
            tools_enabled=context.tools_enabled,
            stream=context.stream,
            temperature=context.temperature,
            max_tokens=context.max_tokens,
            kill_switch_active=context.kill_switch_active
        )

        # 4.5. Invoke MCP tools before LLM (NEW: Phase 2 MCP integration)
        tool_results = await ToolExecutionService.invoke_relevant_tools(context, user_id)

        # 4.6. Check for bank analytics query (BA-P0-001)
        # Only invoke if bank-advisor tool is explicitly enabled by user
        bank_chart_data = None
        bank_advisor_enabled = context.tools_enabled.get("bank-advisor", False) or context.tools_enabled.get("bank_analytics", False)

        if bank_advisor_enabled:
            bank_chart_data = await ToolExecutionService.invoke_bank_analytics(
                message=context.message,
                user_id=user_id
            )
            if bank_chart_data:
                tool_results["bank_analytics"] = bank_chart_data
                logger.info(
                    "Bank analytics result added",
                    metric=bank_chart_data.get("metric_name"),
                    request_id=context.request_id
                )
        else:
            logger.debug(
                "Bank advisor not enabled - skipping bank analytics check",
                tools_enabled=list(context.tools_enabled.keys()),
                request_id=context.request_id
            )

            # NUEVO: Persist as artifact (BA-P0-003)
            from ....models.artifact import Artifact, ArtifactType
            from datetime import datetime

            try:
                # Create title from metric and banks
                metric_name = bank_chart_data.get("metric_name", "Análisis Bancario")
                bank_names = bank_chart_data.get("bank_names", [])
                chart_title = bank_chart_data.get("title") or f"{metric_name} - {', '.join(bank_names)}"

                artifact = Artifact(
                    user_id=user_id,
                    chat_session_id=chat_session.id,
                    title=chart_title,
                    type=ArtifactType.BANK_CHART,
                    content=bank_chart_data,  # Full BankChartData object
                    versions=[],
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                artifact.add_version(bank_chart_data)
                await artifact.insert()

                logger.info(
                    "bank_chart.artifact_created",
                    artifact_id=str(artifact.id),
                    metric=metric_name,
                    banks=bank_names,
                    request_id=context.request_id
                )

                # Add artifact reference to tool_results for LLM context
                tool_results["bank_analytics_artifact_id"] = str(artifact.id)

            except Exception as e:
                logger.error(
                    "bank_chart.artifact_creation_failed",
                    error=str(e),
                    request_id=context.request_id,
                    exc_info=True
                )
                # Don't fail the request if artifact creation fails

        if tool_results:
            # Update context with tool results for LLM injection
            context = ChatContext(
                user_id=context.user_id,
                request_id=context.request_id,
                timestamp=context.timestamp,
                chat_id=context.chat_id,
                session_id=context.session_id,
                message=context.message,
                context=context.context,
                document_ids=context.document_ids,
                tool_results=tool_results,
                model=context.model,
                tools_enabled=context.tools_enabled,
                stream=context.stream,
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                kill_switch_active=context.kill_switch_active
            )
            logger.info(
                "Tool results added to context",
                request_id=context.request_id,
                tool_count=len(tool_results)
            )

        # 5. Add user message
        user_message_metadata = request.metadata.copy() if request.metadata else {}
        if effective_document_ids:
            user_message_metadata["file_ids"] = effective_document_ids

        user_message = await chat_service.add_user_message(
            chat_session=chat_session,
            content=context.message,
            metadata=user_message_metadata if user_message_metadata else None
        )

        # 6. Delegate to handler chain (Chain of Responsibility Pattern)
        handler_chain = create_handler_chain()
        handler_result = await handler_chain.handle(
            context=context,
            chat_service=chat_service,
            user_id=user_id,
            chat_session=chat_session,
            user_message=user_message,
            current_file_ids=effective_document_ids  # ✅ Use in-memory forced list
        )

        if handler_result:
            # Handler processed the message successfully
            logger.info(
                "Message processed by handler chain",
                strategy=handler_result.strategy_used,
                processing_time_ms=handler_result.processing_time_ms
            )

            # BUGFIX: Save assistant message to database
            # Without this, LLM responses are not persisted in chat history
            # Extract decision_metadata and tool_invocations
            decision_metadata = handler_result.metadata.decision_metadata if handler_result.metadata else None
            tool_invocations = decision_metadata.get("tool_invocations", []) if decision_metadata else []

            # Extract bank_chart_artifact from tool results if present
            bank_chart_artifact = None
            if tool_results:
                for key, result in tool_results.items():
                    # Check for bank_analytics result (BA-P0-001)
                    if key == "bank_analytics" and isinstance(result, dict):
                        bank_chart_artifact = result
                        logger.info(
                            "Bank chart artifact detected",
                            metric=result.get("metric_name")
                        )

            logger.info(
                "🔍 DEBUG: About to save assistant message with metadata",
                decision_metadata=decision_metadata,
                tool_invocations=tool_invocations,
                has_tool_invocations=len(tool_invocations) > 0,
                has_bank_chart=bank_chart_artifact is not None
            )

            # Build message metadata
            message_metadata = {
                "strategy_used": handler_result.strategy_used,
                "processing_time_ms": handler_result.processing_time_ms,
                "tokens_used": handler_result.metadata.tokens_used if handler_result.metadata else None,
                "decision_metadata": decision_metadata,
                "tool_invocations": tool_invocations
            }

            # Add bank_chart artifact if present (BA-P0-001)
            if bank_chart_artifact:
                message_metadata["artifact"] = bank_chart_artifact
                message_metadata["kind"] = "bank_chart"

            assistant_message = await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=handler_result.sanitized_content or handler_result.content,
                model=context.model,
                metadata=message_metadata
            )

            logger.info(
                "🔍 DEBUG: Assistant message saved",
                message_id=str(assistant_message.id),
                message_metadata=assistant_message.metadata
            )

            logger.info(
                "Assistant message saved to database",
                message_id=str(assistant_message.id),
                session_id=str(chat_session.id),
                content_length=len(handler_result.content)
            )

            # Invalidate caches
            await cache.invalidate_chat_history(chat_session.id)

            # Build response
            response_builder = (ChatResponseBuilder()
                .from_processing_result(handler_result)
                .with_metadata("processing_time_ms", (time.time() - start_time) * 1000)
                .with_metadata("assistant_message_id", str(assistant_message.id)))

            # Add bank_chart artifact to response (BA-P0-001)
            if bank_chart_artifact:
                response_builder = response_builder.with_artifact(bank_chart_artifact)
                response_builder = response_builder.with_metadata("kind", "bank_chart")

            return response_builder.build()

        # Fallback (should not happen with StandardChatHandler)
        logger.warning(
            "No handler processed the message - this should not happen",
            message=context.message[:50],
            session_id=context.session_id
        )

        # Legacy strategy execution path (fallback)
        # ... (rest of original implementation if needed)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No handler could process the message"
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Chat request failed",
            error=str(exc),
            exc_type=type(exc).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing failed: {str(exc)}"
        )


@router.post("/chat/{chat_id}/escalate", response_model=ApiResponse, tags=["chat"])
async def escalate_to_research(
    chat_id: str,
    http_request: Request,
    settings: Settings = Depends(get_settings)
):
    """
    Escalate conversation to deep research mode.

    BE-6: Deep research escalation endpoint.
    Triggers web search + LLM synthesis for complex queries.

    Args:
        chat_id: Chat session ID to escalate
        http_request: HTTP request with user_id in state
        settings: Application settings

    Returns:
        ApiResponse with success/failure status
    """
    user_id = getattr(http_request.state, 'user_id', 'mock-user-id')

    logger.info(
        "Research escalation requested",
        chat_id=chat_id,
        user_id=user_id,
        kill_switch=settings.deep_research_kill_switch
    )

    # BE-6: Check kill switch
    if settings.deep_research_kill_switch:
        logger.warning(
            "Research escalation blocked by kill switch",
            chat_id=chat_id,
            user_id=user_id
        )
        return ApiResponse(
            success=False,
            message="Deep research is currently disabled.",
            data={"kill_switch_active": True}
        )

    try:
        # Initialize services
        chat_service = ChatService(settings)

        # Get session
        chat_session = await chat_service.get_session(chat_id, user_id)

        if not chat_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session {chat_id} not found"
            )

        # Trigger research (implementation depends on research coordinator)
        # For now, just mark the session
        await chat_session.update({"$set": {
            "research_escalated": True,
            "updated_at": datetime.utcnow()
        }})

        logger.info(
            "Research escalation successful",
            chat_id=chat_id,
            user_id=user_id
        )

        return ApiResponse(
            success=True,
            message="Conversation escalated to research mode",
            data={"chat_id": chat_id, "research_mode": True}
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Research escalation failed",
            chat_id=chat_id,
            error=str(exc),
            exc_type=type(exc).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Escalation failed: {str(exc)}"
        )
