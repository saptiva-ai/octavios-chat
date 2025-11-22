"""
Unit tests for Chat Helpers

Tests:
- build_chat_context
- is_document_ready_and_cached
- wait_for_documents_ready
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'src'))

from src.services.chat_helpers import (
    build_chat_context,
    is_document_ready_and_cached,
    wait_for_documents_ready
)
from src.schemas.chat import ChatRequest
from src.core.config import Settings
from src.models.document import Document, DocumentStatus


@pytest.fixture
def mock_settings():
    """Mock application settings"""
    settings = Mock(spec=Settings)
    settings.deep_research_kill_switch = False
    return settings


@pytest.mark.unit
class TestBuildChatContext:
    """Test build_chat_context function"""

    def test_builds_basic_context(self, mock_settings):
        """Should build context with defaults"""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123"
        )
        user_id = "user-123"

        context = build_chat_context(request, user_id, mock_settings)

        assert context.user_id == user_id
        assert context.chat_id == "chat-123"
        assert context.message == "Hello"
        assert context.model == "Saptiva Turbo"  # Default
        assert context.stream is True  # Default in ChatRequest is True
        assert context.kill_switch_active is False
        assert context.document_ids is None

    def test_merges_document_ids(self, mock_settings):
        """Should merge file_ids and document_ids"""
        request = ChatRequest(
            message="Analyze this",
            chat_id="chat-123",
            file_ids=["file-1"],
            document_ids=["doc-2"]
        )
        
        context = build_chat_context(request, "user-123", mock_settings)
        
        assert context.document_ids == ["file-1", "doc-2"]

    def test_normalizes_tools(self, mock_settings):
        """Should normalize tools enabled state"""
        request = ChatRequest(
            message="Research",
            chat_id="chat-123",
            tools_enabled={"deep_research": True}
        )
        
        context = build_chat_context(request, "user-123", mock_settings)
        
        assert context.tools_enabled["deep_research"] is True
        # Should include defaults from normalize_tools_state
        assert "web_search" in context.tools_enabled


@pytest.mark.unit
class TestDocumentReadiness:
    """Test document readiness helpers"""

    @pytest.mark.asyncio
    async def test_is_document_ready_success(self):
        """Should return True when doc is ready and cached"""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "user-123"
        mock_doc.status = DocumentStatus.READY
        
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "cached content"

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc
            
            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )
            
            assert result is True
            mock_redis.get.assert_called_once_with("doc:text:doc-123")

    @pytest.mark.asyncio
    async def test_is_document_ready_fails_ownership(self):
        """Should return False if user doesn't own document"""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "other-user"
        mock_doc.status = DocumentStatus.READY
        
        mock_redis = AsyncMock()

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc
            
            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )
            
            assert result is False
            mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_wait_for_documents_returns_early(self):
        """Should return early if all docs are ready"""
        mock_redis = AsyncMock()
        
        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True
            
            await wait_for_documents_ready(
                file_ids=["doc-1", "doc-2"],
                user_id="user-123",
                redis_client=mock_redis,
                max_wait_ms=1000
            )
            
            assert mock_check.call_count == 2  # Checked both once

    @pytest.mark.asyncio
    async def test_wait_for_documents_timeouts(self):
        """Should verify timeout logic works (called multiple times)"""
        mock_redis = AsyncMock()
        
        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False  # Never ready
            
            # Small max_wait to fail fast
            await wait_for_documents_ready(
                file_ids=["doc-1"],
                user_id="user-123",
                redis_client=mock_redis,
                max_wait_ms=50,  # 50ms wait
                step_ms=20       # 20ms poll
            )
            
            # Should have been called at least twice (0ms, 20ms, 40ms)
            assert mock_check.call_count >= 2
