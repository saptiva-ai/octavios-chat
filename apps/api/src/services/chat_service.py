"""
Chat Service - Business Logic Layer

Extracts business logic from chat router for better separation of concerns.
Handles chat session management, message processing, and AI response generation.
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import HTTPException, status

from ..core.config import Settings
from ..core.redis_cache import get_redis_cache
from ..core.telemetry import trace_span
from ..models.artifact import Artifact, ArtifactType
from ..models.chat import (
    ChatMessage as ChatMessageModel,
    ChatSession as ChatSessionModel,
    MessageRole,
)
from ..services.saptiva_client import SaptivaClient, build_payload
from ..services.tools import normalize_tools_state

logger = structlog.get_logger(__name__)


class ChatService:
    """Service for chat operations"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.saptiva_client = SaptivaClient()

    async def _handle_tool_invocation(
        self,
        name: str,
        args: Dict[str, Any],
        user_id: str,
        chat_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Execute supported tool calls emitted by the LLM.

        Currently supports:
            - create_artifact: persists an artifact and returns minimal metadata.
        """
        if name != "create_artifact":
            return None

        try:
            title = args.get("title") or "Documento sin título"
            raw_type = args.get("type") or ArtifactType.MARKDOWN.value
            try:
                artifact_type = ArtifactType(raw_type)
            except ValueError:
                artifact_type = ArtifactType.MARKDOWN

            content = args.get("content", "")

            artifact = Artifact(
                user_id=user_id,
                chat_session_id=chat_id,
                title=title,
                type=artifact_type,
                content=content,
                versions=[],
            )
            artifact.add_version(content)
            await artifact.insert()

            return {
                "id": str(artifact.id),
                "title": artifact.title,
                "type": artifact.type.value,
            }
        except Exception as exc:  # pragma: no cover - best-effort tool execution
            logger.warning(
                "Tool invocation failed",
                tool=name,
                error=str(exc),
                user_id=user_id,
                chat_id=chat_id,
            )
            return None

    async def get_or_create_session(
        self,
        chat_id: Optional[str],
        user_id: str,
        first_message: str,
        tools_enabled: Dict[str, bool]
    ) -> ChatSessionModel:
        """
        Get existing chat session or create new one.

        Args:
            chat_id: Optional existing chat ID
            user_id: User ID
            first_message: First message content (for new session title)
            tools_enabled: Tools configuration

        Returns:
            ChatSession model

        Raises:
            HTTPException: If chat not found or access denied
        """
        tools_map = normalize_tools_state(tools_enabled)

        if chat_id:
            # Get existing session
            chat_session = await ChatSessionModel.get(chat_id)
            if not chat_session:
                # Fallback: create a new session if the provided chat_id is stale
                logger.warning(
                    "Chat session not found, creating a new one instead",
                    chat_id=chat_id,
                    user_id=user_id
                )
                title = first_message[:50] + "..." if len(first_message) > 50 else first_message
                chat_session = ChatSessionModel(
                    title=title,
                    user_id=user_id,
                    tools_enabled=tools_map
                )
                await chat_session.insert()
                return chat_session

            if chat_session.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to chat session"
                )

            # Update tools if changed
            existing_tools = normalize_tools_state(getattr(chat_session, 'tools_enabled', None))
            if existing_tools != tools_map:
                await chat_session.update({"$set": {
                    "tools_enabled": tools_map,
                    "updated_at": datetime.utcnow()
                }})
                chat_session.tools_enabled = tools_map

            return chat_session
        else:
            # Create new session
            title = first_message[:50] + "..." if len(first_message) > 50 else first_message
            chat_session = ChatSessionModel(
                title=title,
                user_id=user_id,
                tools_enabled=tools_map
            )
            await chat_session.insert()
            logger.info("Created new chat session", chat_id=chat_session.id, user_id=user_id)
            return chat_session

    async def build_message_context(
        self,
        chat_session: ChatSessionModel,
        current_message: str,
        provided_context: Optional[List[Dict]] = None
    ) -> List[Dict[str, str]]:
        """
        Build conversation context for AI.

        Args:
            chat_session: Chat session
            current_message: Current user message
            provided_context: Optional explicit context

        Returns:
            List of message dicts with role and content
        """
        message_history = []

        if provided_context and len(provided_context) > 0:
            # Use provided context
            for ctx_msg in provided_context:
                message_history.append({
                    "role": ctx_msg.get("role", "user"),
                    "content": ctx_msg.get("content", "")
                })
        else:
            # Get recent messages from session
            recent_messages = await ChatMessageModel.find(
                ChatMessageModel.chat_id == chat_session.id
            ).sort(-ChatMessageModel.created_at).limit(10).to_list()

            # Reverse to chronological order
            for msg in reversed(recent_messages):
                message_history.append({
                    "role": msg.role.value,
                    "content": msg.content
                })

        # Add current message
        message_history.append({
            "role": "user",
            "content": current_message
        })

        return message_history

    async def process_with_saptiva(
        self,
        message: str,
        model: str,
        user_id: str,
        chat_id: str,
        tools_enabled: Dict[str, bool],
        channel: str = "chat",
        user_context: Optional[Dict] = None,
        document_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process message using Saptiva (kill switch path).

        Args:
            message: User message
            model: Model name
            user_id: User ID
            chat_id: Chat ID
            tools_enabled: Tools configuration
            channel: Chat channel
            user_context: Additional context
            document_context: Document content for RAG (formatted string)

        Returns:
            Coordinated response format
        """
        async with trace_span(
            "saptiva_simple_chat",
            {
                "chat.id": chat_id,
                "chat.message_length": len(message),
                "chat.model": model,
                "chat.channel": channel
            }
        ):
            # Build context
            context = user_context or {}
            context['chat_id'] = chat_id
            context['user_id'] = user_id

            tool_invocations: List[Dict[str, Any]] = []

            # Build payload using prompt registry
            payload_data, metadata = build_payload(
                model=model,
                user_prompt=message,
                user_context=context,
                tools_enabled=tools_enabled,
                channel=channel
            )

            # Add document context as system message if provided
            if document_context:
                # Check if context contains images (identified by 📷 emoji)
                has_images = "📷" in document_context
                has_pdfs = "📄" in document_context

                if has_images and not has_pdfs:
                    # Only images - be very explicit
                    system_prompt = (
                        f"El usuario ha adjuntado una o más IMÁGENES. "
                        f"Tienes acceso al TEXTO EXTRAÍDO de estas imágenes mediante OCR (reconocimiento óptico de caracteres). "
                        f"IMPORTANTE: Aunque no puedes 'ver' las imágenes, SÍ puedes analizar, leer y responder preguntas sobre el texto que contienen.\n\n"
                        f"Contenido de las imágenes:\n\n{document_context}\n\n"
                        f"Usa esta información para responder las preguntas del usuario sobre las imágenes."
                    )
                elif has_images and has_pdfs:
                    # Mixed content
                    system_prompt = (
                        f"El usuario ha adjuntado documentos (PDFs e imágenes). "
                        f"Para las imágenes, tienes el texto extraído con OCR. "
                        f"Usa toda esta información para responder las preguntas:\n\n{document_context}"
                    )
                else:
                    # Only PDFs - original prompt
                    system_prompt = (
                        f"El usuario ha adjuntado documentos para tu referencia. "
                        f"Usa esta información para responder sus preguntas:\n\n{document_context}"
                    )

                system_message = {
                    "role": "system",
                    "content": system_prompt
                }

                # Prefer to enrich the existing system prompt so downstream
                # callers (and tests) see the document context in the first
                # system message.
                if payload_data["messages"] and payload_data["messages"][0]["role"] == "system":
                    payload_data["messages"][0]["content"] = (
                        f"{payload_data['messages'][0]['content']}\n\n{system_prompt}"
                    )
                else:
                    payload_data["messages"].insert(0, system_message)

                logger.info(
                    "Added document context to prompt",
                    context_length=len(document_context),
                    has_images=has_images,
                    has_pdfs=has_pdfs,
                    chat_id=chat_id
                )

            # Log telemetry
            logger.info(
                "Saptiva request metadata",
                request_id=metadata.get("request_id"),
                system_hash=metadata.get("system_hash"),
                prompt_version=metadata.get("prompt_version"),
                model=model,
                channel=channel,
                has_tools=metadata.get("has_tools", False)
            )

            # Spy log to confirm tool/document context is reaching the LLM payload
            try:
                messages_dump = json.dumps(
                    payload_data["messages"],
                    default=str
                )
                logger.info(
                    "🕵️ [LLM PROMPT SPY]",
                    contains_findings="findings" in messages_dump,
                    contains_analysis="Analysis Results" in messages_dump,
                    contains_audit="audit" in messages_dump.lower(),
                    prompt_length=len(messages_dump),
                    tool_results_keys=list((user_context or {}).get("tool_results", {}).keys()) if user_context else []
                )
            except Exception:
                logger.warning("Failed to emit LLM prompt spy log")

            # Call Saptiva
            start_time = time.time()
            saptiva_response = await self.saptiva_client.chat_completion(
                messages=payload_data["messages"],
                model=model,
                temperature=payload_data.get("temperature", 0.7),
                max_tokens=payload_data.get("max_tokens", 1024),
                stream=False,
                tools=payload_data.get("tools")
            )

            # Handle tool calls returned by the model (function-calling style)
            try:
                choices = getattr(saptiva_response, "choices", []) or []
                if choices:
                    first_choice = choices[0]
                    message_obj = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
                    raw_tool_calls = []

                    if isinstance(message_obj, dict):
                        if message_obj.get("tool_calls"):
                            raw_tool_calls = message_obj.get("tool_calls") or []
                        elif message_obj.get("function_call"):
                            raw_tool_calls = [
                                {"type": "function", "function": message_obj.get("function_call")}
                            ]

                    for call in raw_tool_calls:
                        func = call.get("function") if isinstance(call, dict) else None
                        if not isinstance(func, dict):
                            continue

                        name = func.get("name")
                        raw_args = func.get("arguments")

                        parsed_args: Dict[str, Any] = {}
                        if isinstance(raw_args, str):
                            try:
                                parsed_args = json.loads(raw_args)
                            except json.JSONDecodeError:
                                parsed_args = {}
                        elif isinstance(raw_args, dict):
                            parsed_args = raw_args

                        if name:
                            result = await self._handle_tool_invocation(
                                name=name,
                                args=parsed_args,
                                user_id=user_id,
                                chat_id=chat_id or None,
                            )
                            if result:
                                tool_invocations.append(
                                    {
                                        "tool_name": name,
                                        "arguments": parsed_args,
                                        "result": result,
                                    }
                                )

            except Exception as parse_exc:  # pragma: no cover - defensive parsing
                logger.warning(
                    "Failed to parse or execute tool calls",
                    error=str(parse_exc),
                    user_id=user_id,
                    chat_id=chat_id,
                )

            # Format as coordinated response
            return {
                "type": "chat",
                "response": saptiva_response,
                "decision": {
                    "complexity": {"score": 0.0, "requires_research": False},
                    "reason": "Kill switch active - simple inference only"
                },
                "tool_invocations": tool_invocations,
                "escalation_available": False,
                "processing_time_ms": (time.time() - start_time) * 1000,
                "_metadata": metadata
            }

    async def add_user_message(
        self,
        chat_session: ChatSessionModel,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChatMessageModel:
        """
        Add user message to session with explicit file metadata validation.

        Uses Pydantic models for type-safe metadata instead of Dict[str, Any].

        Args:
            chat_session: Chat session model
            content: Message content
            metadata: Optional metadata dict with 'file_ids' and 'files' keys

        Returns:
            Created ChatMessage with validated file metadata

        Raises:
            ValidationError: If file metadata structure is invalid
            Exception: If database insertion fails
        """
        from pydantic import ValidationError
        from fastapi.encoders import jsonable_encoder
        from ..models.chat import FileMetadata

        try:
            # Extract and validate file metadata using explicit Pydantic models
            file_ids = []
            files = []

            if metadata:
                # Extract file_ids (list of strings)
                file_ids = metadata.get("file_ids", [])

                # Validate and parse files using FileMetadata model
                raw_files = metadata.get("files", [])
                if raw_files:
                    try:
                        files = [FileMetadata.model_validate(f) for f in raw_files]
                        logger.debug(
                            "Validated file metadata",
                            chat_id=chat_session.id,
                            file_count=len(files),
                            filenames=[f.filename for f in files]
                        )
                    except ValidationError as ve:
                        logger.error(
                            "File metadata validation failed (Pydantic)",
                            chat_id=chat_session.id,
                            validation_errors=ve.errors(),
                            raw_files_preview=str(raw_files)[:200],
                            exc_info=True
                        )
                        # Fallback: save only file_ids without rich metadata
                        files = []

            # FIX ISSUE-003: Clean metadata to prevent duplication
            # Remove file_ids and files from metadata since they're stored in explicit fields
            clean_metadata = {"source": "api"}
            if metadata:
                clean_metadata = {
                    k: v for k, v in metadata.items()
                    if k not in ("file_ids", "files")
                }
                clean_metadata["source"] = "api"

            # Create message with explicit typed fields
            user_message = ChatMessageModel(
                chat_id=chat_session.id,
                role=MessageRole.USER,
                content=content,
                file_ids=file_ids,
                files=files,
                schema_version=2,
                # Legacy metadata for backwards compatibility (cleaned)
                metadata=clean_metadata
            )

            # Ensure BSON/JSON serializability before insertion
            try:
                _probe = jsonable_encoder(user_message, by_alias=True)
                logger.debug(
                    "Message is serializable",
                    chat_id=chat_session.id,
                    file_ids_count=len(file_ids),
                    files_count=len(files)
                )
            except Exception as enc_err:
                logger.error(
                    "Message encoding failed (BSON compatibility)",
                    error=str(enc_err),
                    chat_id=chat_session.id,
                    exc_info=True
                )
                raise

            # Persist to MongoDB
            await user_message.insert()

            # Update session stats (message_count, timestamps)
            chat_session.message_count += 1
            chat_session.updated_at = datetime.utcnow()
            chat_session.last_message_at = datetime.utcnow()
            if chat_session.message_count == 1:
                chat_session.first_message_at = datetime.utcnow()
            await chat_session.save()

            logger.info(
                "Added user message with validated files",
                message_id=user_message.id,
                chat_id=chat_session.id,
                file_count=len(files),
                schema_version=2
            )

            # CRITICAL: Record in unified history (so message appears after refresh)
            try:
                from ..services.history_service import HistoryService
                await HistoryService.record_chat_message(
                    chat_id=chat_session.id,
                    user_id=chat_session.user_id,
                    message=user_message
                )
                logger.debug(
                    "Recorded user message in history",
                    message_id=user_message.id,
                    chat_id=chat_session.id
                )
            except Exception as hist_err:
                # Don't fail message creation if history fails, but log it
                logger.error(
                    "Failed to record user message in history",
                    error=str(hist_err),
                    message_id=user_message.id,
                    chat_id=chat_session.id,
                    exc_info=True
                )

            # Invalidate cache
            cache = await get_redis_cache()
            await cache.invalidate_chat_history(chat_session.id)

            return user_message

        except ValidationError as ve:
            logger.error(
                "Pydantic validation failed for user message",
                error=str(ve),
                validation_errors=ve.errors(),
                chat_id=chat_session.id,
                exc_info=True
            )
            raise

        except Exception as e:
            logger.error(
                "Failed to add user message (database or unknown error)",
                error=str(e),
                error_type=type(e).__name__,
                chat_id=chat_session.id,
                has_metadata=bool(metadata),
                exc_info=True
            )
            raise

    async def add_assistant_message(
        self,
        chat_session: ChatSessionModel,
        content: str,
        model: str,
        task_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tokens: Optional[Dict] = None,
        latency_ms: Optional[int] = None
    ) -> ChatMessageModel:
        """Add assistant message to session and record in unified history."""
        # FIX ISSUE-003: Clean metadata to prevent duplication (defensive)
        # Although assistant messages typically don't have file_ids, clean metadata to be safe
        clean_metadata = {}
        if metadata:
            clean_metadata = {
                k: v for k, v in metadata.items()
                if k not in ("file_ids", "files")
            }

        ai_message = await chat_session.add_message(
            role=MessageRole.ASSISTANT,
            content=content,
            model=model,
            task_id=task_id,
            metadata=clean_metadata,
            tokens=tokens,
            latency_ms=latency_ms
        )

        # NOTE: History recording is handled by chat_session.add_message() (chat.py:236)
        # No need to call HistoryService.record_chat_message() here

        # Invalidate cache
        cache = await get_redis_cache()
        await cache.invalidate_chat_history(chat_session.id)
        if task_id:
            await cache.invalidate_research_tasks(chat_session.id)

        return ai_message
