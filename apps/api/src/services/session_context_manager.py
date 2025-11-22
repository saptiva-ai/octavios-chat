"""
Session Context Manager - Manages file context persistence for chat sessions.

This module handles the logic for maintaining file attachments across messages
in a chat session, following the "keep only latest message's attachments" strategy.

Responsibilities:
    - Normalize file IDs (remove duplicates, preserve order)
    - Determine current file context (request vs session)
    - Update session with new file attachments
    - Wait for documents to be ready before processing
"""

from typing import List
from datetime import datetime

import structlog

from ..models.chat import ChatSession as ChatSessionModel
from ..core.redis_cache import RedisCache
from .chat_helpers import wait_for_documents_ready

logger = structlog.get_logger(__name__)


class SessionContextManager:
    """
    Manages file context for chat sessions.

    This class encapsulates the complex logic of file context persistence,
    following Single Responsibility Principle.
    """

    @staticmethod
    def normalize_file_ids(file_ids: List[str]) -> List[str]:
        """
        Normalize file IDs by removing duplicates while preserving order.

        Args:
            file_ids: List of file IDs (may contain duplicates)

        Returns:
            List of unique file IDs in original order
        """
        if not file_ids:
            return []
        return list(dict.fromkeys(file_ids))

    @staticmethod
    def determine_current_files(
        request_file_ids: List[str],
        session_file_ids: List[str]
    ) -> List[str]:
        """
        Determine which files should be used for this message.

        Strategy: Use request files if provided, otherwise reuse session files.

        Args:
            request_file_ids: Files provided in current request
            session_file_ids: Files attached to session from previous message

        Returns:
            List of file IDs to use for current message
        """
        if request_file_ids:
            # New message provides files → use them
            return request_file_ids
        else:
            # No files in request → reuse context from previous message
            return session_file_ids

    @staticmethod
    async def wait_for_files_ready(
        file_ids: List[str],
        user_id: str,
        redis_cache: RedisCache
    ) -> None:
        """
        Wait for documents to be processed and cached.

        Args:
            file_ids: List of document IDs
            user_id: User ID for ownership validation
            redis_cache: Redis cache instance
        """
        if not file_ids:
            return

        await wait_for_documents_ready(
            file_ids=file_ids,
            user_id=user_id,
            redis_client=redis_cache.client
        )

    @staticmethod
    async def update_session_files(
        chat_session: ChatSessionModel,
        new_file_ids: List[str],
        previous_file_ids: List[str]
    ) -> bool:
        """
        Update session's attached_file_ids if files changed.

        Args:
            chat_session: ChatSession model instance
            new_file_ids: New file IDs from current request
            previous_file_ids: Previous file IDs from session

        Returns:
            True if session was updated, False otherwise
        """
        # Only update if files changed
        if not new_file_ids or new_file_ids == previous_file_ids:
            return False

        await chat_session.update({"$set": {
            "attached_file_ids": new_file_ids,
            "updated_at": datetime.utcnow()
        }})

        chat_session.attached_file_ids = new_file_ids

        logger.info(
            "Updated session attached_file_ids",
            chat_id=chat_session.id,
            file_count=len(new_file_ids),
            replaced_previous=bool(previous_file_ids)
        )

        return True

    @staticmethod
    async def prepare_session_context(
        chat_session: ChatSessionModel,
        request_file_ids: List[str],
        user_id: str,
        redis_cache: RedisCache,
        request_id: str
    ) -> List[str]:
        """
        Prepare session context with files (high-level orchestration).

        This method:
        1. Normalizes request file IDs
        2. Determines current files (request vs session)
        3. Waits for documents to be ready
        4. Updates session if files changed
        5. Logs context for observability

        Args:
            chat_session: ChatSession model instance
            request_file_ids: File IDs from current request
            user_id: User ID
            redis_cache: Redis cache instance
            request_id: Request ID for logging

        Returns:
            List of file IDs to use for this message
        """
        # 1. Normalize request files
        normalized_request_files = SessionContextManager.normalize_file_ids(
            request_file_ids
        )

        # 2. Get session files
        session_file_ids = list(
            getattr(chat_session, 'attached_file_ids', []) or []
        )

        # 3. Determine current files
        current_file_ids = SessionContextManager.determine_current_files(
            normalized_request_files,
            session_file_ids
        )

        # 4. Log for observability
        logger.info(
            "Session context prepared",
            request_file_ids_count=len(normalized_request_files),
            session_file_ids_count=len(session_file_ids),
            current_file_ids_count=len(current_file_ids),
            current_file_ids=current_file_ids,
            nonce=request_id[:8]
        )

        # 5. Wait for documents to be ready
        await SessionContextManager.wait_for_files_ready(
            current_file_ids,
            user_id,
            redis_cache
        )

        # 6. Update session if files changed
        await SessionContextManager.update_session_files(
            chat_session,
            normalized_request_files,
            session_file_ids
        )

        return current_file_ids
