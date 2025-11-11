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
from typing import AsyncGenerator
from datetime import datetime

import structlog

from ....core.config import Settings
from ....core.redis_cache import get_redis_cache
from ....schemas.chat import ChatRequest
from ....services.chat_service import ChatService
from ....services.chat_helpers import build_chat_context
from ....services.session_context_manager import SessionContextManager
from ....services.document_service import DocumentService
from ....services.saptiva_client import get_saptiva_client
from ....domain import ChatContext

logger = structlog.get_logger(__name__)


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

    async def handle_stream(
        self,
        request: ChatRequest,
        user_id: str
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

            # Add user message
            user_message_metadata = request.metadata.copy() if request.metadata else {}
            if current_file_ids:
                user_message_metadata["file_ids"] = current_file_ids

            user_message = await chat_service.add_user_message(
                chat_session=chat_session,
                content=context.message,
                metadata=user_message_metadata if user_message_metadata else None
            )

            # Check for audit command (not supported in streaming)
            if context.message.strip().startswith("Auditar archivo:"):
                async for event in self._handle_audit_error(
                    chat_service, chat_session, context
                ):
                    yield event
                return

            # Stream chat response
            async for event in self._stream_chat_response(
                context, chat_service, chat_session, cache
            ):
                yield event

        except Exception as exc:
            logger.error(
                "Streaming chat failed",
                error=str(exc),
                exc_type=type(exc).__name__,
                exc_info=True
            )

            yield {
                "event": "error",
                "data": json.dumps({
                    "error": type(exc).__name__,
                    "message": str(exc)
                })
            }

    async def _handle_audit_error(
        self,
        chat_service: ChatService,
        chat_session,
        context: ChatContext
    ) -> AsyncGenerator[dict, None]:
        """
        Handle audit command error (not supported in streaming).

        Args:
            chat_service: ChatService instance
            chat_session: ChatSession model
            context: ChatContext with request data

        Yields:
            Error SSE event
        """
        logger.warning(
            "Audit command not supported in streaming mode",
            message=context.message,
            user_id=context.user_id
        )

        error_msg = (
            "⚠️ La auditoría de archivos no está disponible en modo streaming. "
            "Por favor, desactiva el streaming e intenta nuevamente."
        )

        # Save error message
        await chat_service.add_assistant_message(
            chat_session=chat_session,
            content=error_msg,
            model=context.model,
            metadata={"error": "audit_not_supported_in_streaming"}
        )

        # Yield error event
        yield {
            "event": "error",
            "data": json.dumps({
                "error": "audit_not_supported_in_streaming",
                "message": error_msg
            })
        }

    async def _stream_chat_response(
        self,
        context: ChatContext,
        chat_service: ChatService,
        chat_session,
        cache
    ) -> AsyncGenerator[dict, None]:
        """
        Stream chat response from Saptiva API.

        Args:
            context: ChatContext with request data
            chat_service: ChatService instance
            chat_session: ChatSession model
            cache: Redis cache instance

        Yields:
            SSE events with message chunks and completion
        """
        # Prepare document context for RAG
        document_context = None
        doc_warnings = []

        if context.document_ids:
            doc_texts = await DocumentService.get_document_text_from_cache(
                document_ids=context.document_ids,
                user_id=context.user_id
            )

            if doc_texts:
                max_docs = int(os.getenv("MAX_DOCS_PER_CHAT", "3"))
                max_chars = int(os.getenv("MAX_TOTAL_DOC_CHARS", "16000"))

                document_context, doc_warnings, _ = (
                    DocumentService.extract_content_for_rag_from_cache(
                        doc_texts=doc_texts,
                        max_chars_per_doc=8000,
                        max_total_chars=max_chars,
                        max_docs=max_docs
                    )
                )

        # Initialize Saptiva client
        saptiva_client = get_saptiva_client(self.settings)

        # Prepare system message with document context
        system_message = "Eres un asistente útil."
        if document_context:
            system_message += f"\n\nContexto de documentos:\n{document_context}"

        # Stream from Saptiva
        full_response = ""

        async for chunk in saptiva_client.stream_chat(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": context.message}
            ],
            model=context.model,
            temperature=context.temperature,
            max_tokens=context.max_tokens
        ):
            # Yield chunk to client
            yield {
                "event": "message",
                "data": json.dumps({"chunk": chunk})
            }

            full_response += chunk

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
