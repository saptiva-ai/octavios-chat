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


async def invoke_relevant_tools(
    context: ChatContext,
    user_id: str
) -> Dict:
    """
    Invoke relevant MCP tools based on context and return results.

    This function determines which tools should be executed based on the
    chat context (document types, enabled tools, etc.) and collects their
    results for LLM context injection.

    Features:
    - Redis caching to avoid re-execution
    - Graceful error handling
    - Per-tool TTL configuration
    - Smart cache key generation

    Args:
        context: ChatContext with message, document IDs, and tools_enabled
        user_id: User ID for tool invocation authorization

    Returns:
        Dict mapping tool_name -> result for tools that were successfully invoked

    Example return:
        {
            "audit_file_doc123": {...ValidationReport...},
            "excel_analyzer_doc456": {...ExcelAnalysis...}
        }
    """
    from ....services.document_service import DocumentService
    from ....mcp import get_mcp_adapter
    from ....core.redis_cache import get_redis_cache
    import json
    import hashlib

    results = {}

    # TTL configuration for each tool (in seconds)
    TOOL_CACHE_TTL = {
        "audit_file": 3600,       # 1 hour (findings don't change)
        "excel_analyzer": 1800,   # 30 min (data might update)
        "deep_research": 86400,   # 24 hours (research is expensive)
        "extract_document_text": 3600,  # 1 hour (text is stable)
    }

    def generate_cache_key(tool_name: str, doc_id: str, params: Dict = None) -> str:
        """
        Generate unique cache key for tool result.

        Format: mcp:tool:{tool_name}:{doc_id}:{params_hash}
        """
        if params:
            # Create deterministic hash of params
            params_str = json.dumps(params, sort_keys=True)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
            return f"mcp:tool:{tool_name}:{doc_id}:{params_hash}"
        return f"mcp:tool:{tool_name}:{doc_id}"

    # Get Redis cache
    try:
        cache = await get_redis_cache()
    except Exception as e:
        logger.warning(
            "Failed to get Redis cache for tool results",
            error=str(e),
            exc_type=type(e).__name__
        )
        cache = None

    # Skip if no tools enabled
    if not context.tools_enabled or not any(context.tools_enabled.values()):
        logger.debug("No tools enabled, skipping tool invocation")
        return results

    # Skip if no documents attached
    if not context.document_ids:
        logger.debug("No documents attached, skipping tool invocation")
        return results

    try:
        # Get MCP adapter for internal tool invocation
        mcp_adapter = get_mcp_adapter()
        tool_map = await mcp_adapter._get_tool_map()

        # Check if audit_file should run
        if context.tools_enabled.get("audit_file", False) and "audit_file" in tool_map:
            for doc_id in context.document_ids:
                try:
                    # Generate cache key
                    cache_params = {"policy_id": "auto"}
                    cache_key = generate_cache_key("audit_file", doc_id, cache_params)

                    # Try to get from cache first
                    cached_result = None
                    if cache:
                        try:
                            cached_result = await cache.get(cache_key)
                            if cached_result:
                                logger.info(
                                    "audit_file result loaded from cache",
                                    doc_id=doc_id,
                                    cache_hit=True
                                )
                        except Exception as e:
                            logger.warning(
                                "Failed to read from cache",
                                cache_key=cache_key,
                                error=str(e)
                            )

                    if cached_result:
                        # Use cached result
                        audit_result = cached_result
                    else:
                        # Execute tool
                        logger.info(
                            "Invoking audit_file tool",
                            doc_id=doc_id,
                            user_id=user_id,
                            cache_hit=False
                        )

                        tool_impl = tool_map["audit_file"]
                        audit_result = await mcp_adapter._execute_tool_impl(
                            tool_name="audit_file",
                            tool_impl=tool_impl,
                            payload={
                                "doc_id": doc_id,
                                "policy_id": "auto",
                                "user_id": user_id
                            }
                        )

                        # Store in cache
                        if cache:
                            try:
                                ttl = TOOL_CACHE_TTL.get("audit_file", 3600)
                                await cache.set(cache_key, audit_result, expire=ttl)
                                logger.debug(
                                    "Cached audit_file result",
                                    cache_key=cache_key,
                                    ttl=ttl
                                )
                            except Exception as e:
                                logger.warning(
                                    "Failed to cache audit result",
                                    cache_key=cache_key,
                                    error=str(e)
                                )

                    results[f"audit_file_{doc_id}"] = audit_result
                    logger.info(
                        "audit_file tool succeeded",
                        doc_id=doc_id,
                        findings_count=len(audit_result.get("findings", [])),
                        from_cache=cached_result is not None
                    )

                except Exception as e:
                    logger.warning(
                        "audit_file tool failed",
                        doc_id=doc_id,
                        error=str(e),
                        exc_type=type(e).__name__
                    )
                    # Continue with other tools even if this one fails

        # Check if excel_analyzer should run for Excel files
        if context.tools_enabled.get("excel_analyzer", False) and "excel_analyzer" in tool_map:
            from src.models.document import Document

            for doc_id in context.document_ids:
                try:
                    # Check if document is an Excel file
                    doc = await Document.get(doc_id)
                    if not doc:
                        continue

                    # Verify ownership
                    if str(doc.user_id) != user_id:
                        continue

                    is_excel = doc.content_type in [
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "application/vnd.ms-excel"
                    ]

                    if not is_excel:
                        continue

                    # Generate cache key
                    cache_params = {"operations": ["stats", "preview"]}
                    cache_key = generate_cache_key("excel_analyzer", doc_id, cache_params)

                    # Try to get from cache first
                    cached_result = None
                    if cache:
                        try:
                            cached_result = await cache.get(cache_key)
                            if cached_result:
                                logger.info(
                                    "excel_analyzer result loaded from cache",
                                    doc_id=doc_id,
                                    cache_hit=True
                                )
                        except Exception as e:
                            logger.warning(
                                "Failed to read from cache",
                                cache_key=cache_key,
                                error=str(e)
                            )

                    if cached_result:
                        # Use cached result
                        excel_result = cached_result
                    else:
                        # Execute tool
                        logger.info(
                            "Invoking excel_analyzer tool",
                            doc_id=doc_id,
                            user_id=user_id,
                            cache_hit=False
                        )

                        tool_impl = tool_map["excel_analyzer"]
                        excel_result = await mcp_adapter._execute_tool_impl(
                            tool_name="excel_analyzer",
                            tool_impl=tool_impl,
                            payload={
                                "doc_id": doc_id,
                                "operations": ["stats", "preview"],
                                "user_id": user_id
                            }
                        )

                        # Store in cache
                        if cache:
                            try:
                                ttl = TOOL_CACHE_TTL.get("excel_analyzer", 1800)
                                await cache.set(cache_key, excel_result, expire=ttl)
                                logger.debug(
                                    "Cached excel_analyzer result",
                                    cache_key=cache_key,
                                    ttl=ttl
                                )
                            except Exception as e:
                                logger.warning(
                                    "Failed to cache excel result",
                                    cache_key=cache_key,
                                    error=str(e)
                                )

                    results[f"excel_analyzer_{doc_id}"] = excel_result
                    logger.info(
                        "excel_analyzer tool succeeded",
                        doc_id=doc_id,
                        from_cache=cached_result is not None
                    )

                except Exception as e:
                    logger.warning(
                        "excel_analyzer tool failed",
                        doc_id=doc_id,
                        error=str(e),
                        exc_type=type(e).__name__
                    )
                    # Continue with other tools

        logger.info(
            "Tool invocation completed",
            tools_executed=len(results),
            user_id=user_id
        )

    except Exception as e:
        logger.error(
            "Failed to invoke tools",
            error=str(e),
            exc_type=type(e).__name__,
            exc_info=True
        )
        # Return empty results on error - don't fail the entire request

    return results


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
    if getattr(request, 'stream', False):
        accept_header = http_request.headers.get("accept", "")
        if "text/event-stream" in accept_header:
            streaming_handler = StreamingHandler(settings)
            return EventSourceResponse(
                streaming_handler.handle_stream(request, user_id, background_tasks),
                media_type="text/event-stream"
            )
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
                tool_results={},  # Will be populated below
                model=context.model,
                tools_enabled=context.tools_enabled,
                stream=context.stream,
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                kill_switch_active=context.kill_switch_active
            )

        # 4.5. Invoke MCP tools before LLM (NEW: Phase 2 MCP integration)
        tool_results = await invoke_relevant_tools(context, user_id)
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
        if current_file_ids:
            user_message_metadata["file_ids"] = current_file_ids

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
            current_file_ids=current_file_ids
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
            assistant_message = await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=handler_result.sanitized_content or handler_result.content,
                model=context.model,
                metadata={
                    "strategy_used": handler_result.strategy_used,
                    "processing_time_ms": handler_result.processing_time_ms,
                    "tokens_used": handler_result.metadata.tokens_used if handler_result.metadata else None,
                    "decision_metadata": handler_result.metadata.decision_metadata if handler_result.metadata else None
                }
            )

            logger.info(
                "Assistant message saved to database",
                message_id=str(assistant_message.id),
                session_id=str(chat_session.id),
                content_length=len(handler_result.content)
            )

            # Invalidate caches
            await cache.invalidate_chat_history(chat_session.id)

            # Return response
            return (ChatResponseBuilder()
                .from_processing_result(handler_result)
                .with_metadata("processing_time_ms", (time.time() - start_time) * 1000)
                .with_metadata("assistant_message_id", str(assistant_message.id))
                .build())

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
