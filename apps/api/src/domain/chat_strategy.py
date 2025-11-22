"""
Chat Strategy Pattern - Pluggable handlers for different chat scenarios.

Implements Strategy Pattern to handle:
- Simple chat (kill switch active)
- Coordinated chat (with research coordinator)
- Future: Streaming chat, multi-modal chat, etc.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import structlog

from ..core.telemetry import trace_span
from ..services.chat_service import ChatService
from ..services.document_service import DocumentService
from ..services.text_sanitizer import sanitize_response_content
from ..services.saptiva_client import get_saptiva_client
from ..services.context_manager import ContextManager
from ..services.empty_response_handler import (
    EmptyResponseHandler,
    EmptyResponseScenario,
    ensure_non_empty_content
)
from .chat_context import ChatContext, ChatProcessingResult, MessageMetadata


logger = structlog.get_logger(__name__)


class ChatStrategy(ABC):
    """
    Abstract base class for chat processing strategies.

    Defines the interface that all concrete strategies must implement.
    """

    def __init__(self, chat_service: ChatService):
        self.chat_service = chat_service

    @abstractmethod
    async def process(self, context: ChatContext) -> ChatProcessingResult:
        """
        Process a chat message using this strategy.

        Args:
            context: ChatContext with all request information.

        Returns:
            ChatProcessingResult with response and metadata.
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return strategy name for logging/metadata."""
        pass


class SimpleChatStrategy(ChatStrategy):
    """
    Simple chat strategy - direct Saptiva inference.

    This is the main strategy for regular chat interactions.
    Supports document context but no deep research or web search.
    """

    def get_strategy_name(self) -> str:
        return "simple"

    async def process(self, context: ChatContext) -> ChatProcessingResult:
        """
        Process message with Saptiva, optionally including document context.

        Args:
            context: ChatContext with request data and optional documents.

        Returns:
            ChatProcessingResult with AI response.
        """
        start_time = time.time()

        logger.info(
            "Processing chat with simple strategy",
            user_id=context.user_id,
            session_id=context.session_id,
            model=context.model,
            has_documents=bool(context.document_ids)
        )

        # Phase 2 MCP Integration: Initialize unified context manager
        # Combines document context + tool results with consistent size limits
        doc_warnings = []
        context_metadata = {"used_docs": 0, "used_chars": 0}

        # BE-PERF-1: Load guardrails from environment
        max_docs_per_chat = int(os.getenv("MAX_DOCS_PER_CHAT", "3"))
        max_total_doc_chars = int(os.getenv("MAX_TOTAL_DOC_CHARS", "16000"))
        max_tool_chars = int(os.getenv("MAX_TOOL_CONTEXT_CHARS", "8000"))
        max_total_chars = int(os.getenv("MAX_TOTAL_CONTEXT_CHARS", "24000"))

        # Initialize ContextManager for unified context aggregation
        context_mgr = ContextManager(
            max_document_chars=max_total_doc_chars,
            max_tool_chars=max_tool_chars,
            max_total_chars=max_total_chars
        )

        # 1. Add document context (if documents attached)
        if context.document_ids:
            async with trace_span("retrieve_documents_from_cache", {
                "document_count": len(context.document_ids)
            }):
                # Retrieve text from Redis cache with ownership validation
                doc_texts = await DocumentService.get_document_text_from_cache(
                    document_ids=context.document_ids,
                    user_id=context.user_id
                )

                if doc_texts:
                    preselection_warnings: List[str] = []
                    missing_doc_ids = [
                        doc_id for doc_id in context.document_ids if doc_id not in doc_texts
                    ]
                    if missing_doc_ids:
                        preselection_warnings.append(
                            "Documentos aún en procesamiento o no disponibles: "
                            + ", ".join(missing_doc_ids)
                        )

                    # Add each document to context manager
                    for doc_id, doc_data in doc_texts.items():
                        text = doc_data.get("text", "")
                        filename = doc_data.get("filename", doc_id)
                        if text:
                            context_mgr.add_document_context(
                                doc_id=doc_id,
                                text=text,
                                filename=filename
                            )

                    if preselection_warnings:
                        doc_warnings.extend(preselection_warnings)

                    # Update context_metadata for logging
                    context_metadata["used_docs"] = len(doc_texts)
                    context_metadata["used_chars"] = sum(
                        len(doc_data.get("text", "")) for doc_data in doc_texts.values()
                    )

                    if doc_warnings:
                        logger.warning(
                            "Document processing warnings",
                            warnings=doc_warnings,
                            user_id=context.user_id,
                            used_docs=context_metadata.get("used_docs"),
                            used_chars=context_metadata.get("used_chars")
                        )

                    logger.info(
                        "Retrieved documents for context manager",
                        document_count=len(doc_texts),
                        expired_count=len([w for w in doc_warnings if "expiró" in w]),
                        used_docs=context_metadata.get("used_docs"),
                        used_chars=context_metadata.get("used_chars"),
                        max_docs=max_docs_per_chat,
                        max_total_chars=max_total_doc_chars
                    )
                else:
                    logger.warning(
                        "No accessible documents found in cache",
                        requested_ids=context.document_ids,
                        user_id=context.user_id
                    )

        # 2. Add tool results (if tools were executed)
        if context.tool_results:
            for tool_key, tool_result in context.tool_results.items():
                context_mgr.add_tool_result(
                    tool_name=tool_key,
                    result=tool_result
                )

            logger.info(
                "Added tool results to context manager",
                tool_count=len(context.tool_results),
                user_id=context.user_id
            )

        # 3. Build unified context string for LLM injection
        unified_context, unified_metadata = context_mgr.build_context_string()

        logger.info(
            "Built unified context for LLM",
            total_sources=unified_metadata["total_sources"],
            document_sources=unified_metadata["document_sources"],
            tool_sources=unified_metadata["tool_sources"],
            total_chars=unified_metadata["total_chars"],
            truncated=unified_metadata["truncated"]
        )

        async with trace_span("simple_chat_inference"):
            # Use ChatService to process with Saptiva
            # Phase 2 MCP: Pass unified context (documents + tool results)
            coordinated_response = await self.chat_service.process_with_saptiva(
                message=context.message,
                model=context.model,
                user_id=context.user_id,
                chat_id=context.session_id or "",
                tools_enabled=context.tools_enabled,
                document_context=unified_context if unified_context else None
            )

        tool_invocations = coordinated_response.get("tool_invocations") or []

        # Extract response content from SaptivaResponse object
        response_obj = coordinated_response.get("response")

        # DEBUG: Log response_obj structure
        logger.info(
            "🐛 [DEBUG] Extracting content from Saptiva response",
            has_response_obj=response_obj is not None,
            response_obj_type=type(response_obj).__name__ if response_obj else None,
            has_choices_attr=hasattr(response_obj, 'choices') if response_obj else False,
            choices_length=len(response_obj.choices) if (response_obj and hasattr(response_obj, 'choices')) else 0
        )

        if hasattr(response_obj, 'choices') and len(response_obj.choices) > 0:
            # Extract text from Pydantic SaptivaResponse object
            choice_0 = response_obj.choices[0]
            message_obj = choice_0.get("message", {}) if isinstance(choice_0, dict) else {}

            logger.info(
                "🐛 [DEBUG] First choice structure",
                choice_type=type(choice_0).__name__,
                choice_keys=list(choice_0.keys()) if isinstance(choice_0, dict) else "not_a_dict",
                has_message=choice_0.get("message") is not None if isinstance(choice_0, dict) else False,
                message_type=type(message_obj).__name__,
                message_keys=list(message_obj.keys()) if isinstance(message_obj, dict) else "not_a_dict",
                message_repr=str(message_obj)[:200]
            )

            # CRITICAL FIX: Saptiva Cortex uses reasoning_content for chain-of-thought
            # Extract both content and reasoning_content
            message = response_obj.choices[0].get("message", {})
            content = message.get("content", "")
            reasoning_content = message.get("reasoning_content", "")

            # Use content if available, fallback to reasoning_content
            response_content = content if content else reasoning_content

            logger.info(
                "🐛 [DEBUG] Extracted content",
                content_length=len(content),
                reasoning_length=len(reasoning_content),
                final_content_length=len(response_content),
                content_preview=response_content[:100] if response_content else "(EMPTY)"
            )
        else:
            response_content = ""
            logger.warning(
                "🐛 [DEBUG] No choices found - response_content set to empty string"
            )

        # If the model only returned a tool invocation, provide a minimal message
        if not response_content and tool_invocations:
            primary = tool_invocations[0].get("result", {})
            fallback_title = primary.get("title") or "Nuevo artefacto"
            response_content = (
                f"Creé el artefacto **{fallback_title}** y lo guardé en el panel lateral."
            )

        # ANTI-EMPTY-RESPONSE: Use centralized handler with contextual messages
        # Determine the most likely scenario based on available context
        if not response_content:
            if doc_warnings:
                scenario = EmptyResponseScenario.DOCS_PROCESSING
            elif context.document_ids and len(context.document_ids) > 0:
                scenario = EmptyResponseScenario.DOCS_NOT_FOUND
            else:
                scenario = EmptyResponseScenario.API_EMPTY_CONTENT

            response_content = EmptyResponseHandler.get_fallback_message(
                scenario=scenario,
                context={
                    "user_id": context.user_id,
                    "session_id": context.session_id,
                    "model": context.model,
                    "has_documents": bool(context.document_ids),
                    "document_count": len(context.document_ids) if context.document_ids else 0,
                }
            )

            # Log the incident for monitoring
            EmptyResponseHandler.log_empty_response_incident(
                scenario=scenario,
                context={
                    "user_id": context.user_id,
                    "session_id": context.session_id,
                    "model": context.model,
                    "has_documents": bool(context.document_ids),
                    "document_count": len(context.document_ids) if context.document_ids else 0,
                    "doc_warnings": doc_warnings if doc_warnings else None,
                    "strategy": "simple"
                }
            )

        # Sanitize response
        sanitized_content = sanitize_response_content(response_content)

        logger.info(
            "🐛 [DEBUG] After sanitization",
            original_length=len(response_content),
            sanitized_length=len(sanitized_content) if sanitized_content else 0,
            sanitized_preview=sanitized_content[:100] if sanitized_content else "(NONE)"
        )

        # Build metadata
        # BE-2: Include document warnings in decision_metadata
        # BE-PERF-1: Include context metadata (used_docs, used_chars)
        # Phase 2 MCP: Include unified context metadata (documents + tools)
        decision_metadata = coordinated_response.get("decision") or {}
        if doc_warnings:
            decision_metadata["document_warnings"] = doc_warnings
        if context_metadata:
            decision_metadata["context_stats"] = context_metadata
        # Add unified context metadata from ContextManager
        if unified_metadata:
            decision_metadata["unified_context"] = unified_metadata
        if tool_invocations:
            decision_metadata["tool_invocations"] = tool_invocations

        metadata = MessageMetadata(
            message_id=coordinated_response.get("message_id", ""),
            chat_id=context.session_id or "",
            user_message_id="",  # Set by caller
            assistant_message_id=coordinated_response.get("message_id"),
            model_used=context.model,
            tokens_used=coordinated_response.get("tokens"),
            latency_ms=coordinated_response.get("processing_time_ms"),
            decision_metadata=decision_metadata
        )

        processing_time = (time.time() - start_time) * 1000

        logger.info(
            "🐛 [DEBUG] Creating ChatProcessingResult",
            content_length=len(response_content),
            sanitized_content_length=len(sanitized_content) if sanitized_content else 0,
            strategy=self.get_strategy_name()
        )

        result = ChatProcessingResult(
            content=response_content,
            sanitized_content=sanitized_content,
            metadata=metadata,
            processing_time_ms=processing_time,
            strategy_used=self.get_strategy_name(),
            research_triggered=False,
            session_updated=False
        )

        logger.info(
            "🐛 [DEBUG] ChatProcessingResult created",
            result_content_length=len(result.content),
            result_sanitized_length=len(result.sanitized_content) if result.sanitized_content else 0
        )

        return result


# ADR-001: ChatStrategyFactory removed (YAGNI principle)
# Previous implementation always returned SimpleChatStrategy.
# When multiple strategies are needed, re-introduce factory with real selection logic.
#
# To add strategies in the future:
# 1. Create new strategy class (e.g., RAGChatStrategy)
# 2. Add selection logic based on context
# 3. Re-introduce factory pattern
#
# See: docs/architecture/decisions/001-remove-chat-strategy-factory.md
