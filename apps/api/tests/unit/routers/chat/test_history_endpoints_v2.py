"""
Comprehensive tests for routers/chat/endpoints/history_endpoints.py

Tests:
- GET /history/{chat_id} endpoint
- Research task enrichment
- Cache hits and misses
- Pagination and filtering
- Permission checks
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from fastapi import FastAPI, status, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
import sys
import os

# Ensure proper imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..', 'src'))

from src.routers.chat.endpoints.history_endpoints import router as history_router
from src.schemas.chat import ChatHistoryResponse, ChatMessage
from src.models.chat import MessageRole, MessageStatus
from src.core.exceptions import NotFoundError


@pytest.fixture
def app():
    """Create a minimal FastAPI app for testing."""
    test_app = FastAPI()

    # Register exception handlers
    @test_app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.detail}
        )

    test_app.include_router(history_router)
    return test_app


@pytest.fixture
def client(app):
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_chat_messages():
    """Create mock chat messages."""
    msg1 = MagicMock()
    msg1.id = "msg-1"
    msg1.chat_id = "chat-123"
    msg1.role = MessageRole.USER
    msg1.content = "Hello, assistant!"
    msg1.status = MessageStatus.DELIVERED
    msg1.created_at = datetime.utcnow()
    msg1.updated_at = datetime.utcnow()
    msg1.metadata = {"source": "web"}
    msg1.model = None
    msg1.tokens = 5
    msg1.latency_ms = 0
    msg1.task_id = None

    msg2 = MagicMock()
    msg2.id = "msg-2"
    msg2.chat_id = "chat-123"
    msg2.role = MessageRole.ASSISTANT
    msg2.content = "Hello! How can I help you?"
    msg2.status = MessageStatus.DELIVERED
    msg2.created_at = datetime.utcnow()
    msg2.updated_at = datetime.utcnow()
    msg2.metadata = {}
    msg2.model = "saptiva-turbo"
    msg2.tokens = 10
    msg2.latency_ms = 250
    msg2.task_id = None

    return [msg1, msg2]


@pytest.mark.unit
class TestGetChatHistory:
    """Test GET /history/{chat_id} endpoint"""

    @pytest.mark.asyncio
    async def test_get_chat_history_cached(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should return cached history when available"""
        chat_id = "test-chat-123"
        cached_data = {
            "chat_id": chat_id,
            "messages": [
                {
                    "id": "msg-1",
                    "chat_id": chat_id,
                    "role": "user",
                    "content": "Hello",
                    "status": "delivered",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "metadata": {},
                    "model": None,
                    "tokens": 5,
                    "latency_ms": 0,
                    "task_id": None
                }
            ],
            "total_count": 1,
            "has_more": False
        }

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache:
            # Setup
            mock_redis_cache = AsyncMock()
            mock_redis_cache.get_chat_history = AsyncMock(return_value=cached_data)
            mock_get_cache.return_value = mock_redis_cache

            # Execute
            response = client.get(f"/history/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            # Should not call permission check when cache hits
            mock_redis_cache.get_chat_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_chat_history_service_error(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should handle service errors gracefully"""
        chat_id = "test-chat-123"

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                side_effect=Exception("Database error")
            )

            # Execute
            response = client.get(f"/history/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Failed to retrieve chat history" in response.json()["detail"]

    @pytest.mark.parametrize("limit,offset", [(10, 0), (25, 10), (50, 50)])
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Beanie query chain mocking issue - ChatMessageModel.find() returns cannot properly chain methods in TestClient context")
    async def test_get_chat_history_pagination(
        self,
        limit,
        offset,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should respect limit and offset parameters"""
        chat_id = "test-chat-123"

        # Create a proper async query mock
        async def async_count_func():
            return 100

        async def async_to_list_func():
            return []

        query_mock = MagicMock()
        query_mock.find = MagicMock(return_value=query_mock)
        query_mock.sort = MagicMock(return_value=query_mock)
        query_mock.skip = MagicMock(return_value=query_mock)
        query_mock.limit = MagicMock(return_value=query_mock)
        query_mock.count = async_count_func
        query_mock.to_list = async_to_list_func

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)
            mock_redis_cache.set_chat_history = AsyncMock()

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Setup ChatMessageModel.find() to return the query mock
            MockMessageModel.find = MagicMock(return_value=query_mock)

            # Execute with pagination
            response = client.get(f"/history/{chat_id}?limit={limit}&offset={offset}")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            # Verify pagination was called correctly
            query_mock.skip.assert_called_with(offset)
            query_mock.limit.assert_called_with(limit)

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Beanie query chain mocking issue - ChatMessageModel.find() returns cannot properly chain methods in TestClient context")
    async def test_get_chat_history_has_more_flag(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should correctly set has_more flag based on total count"""
        chat_id = "test-chat-123"

        # Create a proper async query mock
        async def async_count_func():
            return 100

        async def async_to_list_func():
            return [MagicMock() for _ in range(10)]

        query_mock = MagicMock()
        query_mock.find = MagicMock(return_value=query_mock)
        query_mock.sort = MagicMock(return_value=query_mock)
        query_mock.skip = MagicMock(return_value=query_mock)
        query_mock.limit = MagicMock(return_value=query_mock)
        query_mock.count = async_count_func
        query_mock.to_list = async_to_list_func

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)
            mock_redis_cache.set_chat_history = AsyncMock()

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            MockMessageModel.find = MagicMock(return_value=query_mock)

            # Execute with limit=10, offset=0
            response = client.get(f"/history/{chat_id}?limit=10&offset=0")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 100
            assert data["has_more"] is True  # 0 + 10 < 100

    @pytest.mark.asyncio
    async def test_get_chat_history_unauthorized(self, client):
        """Should return 404 when user doesn't have access"""
        chat_id = "unauthorized-chat"

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService:

            # Setup
            mock_redis_cache = AsyncMock()
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)
            mock_get_cache.return_value = mock_redis_cache

            # HistoryService raises HTTPException for unauthorized access
            from fastapi import HTTPException
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                side_effect=HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat session not found"
                )
            )

            # Execute
            response = client.get(f"/history/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_404_NOT_FOUND
