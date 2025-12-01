"""
Tests for BankAdvisor conditional activation.

Verifies that BankAdvisor tool only activates when explicitly enabled by user.

Test Cases:
1. BankAdvisor disabled - should NOT invoke bank analytics
2. BankAdvisor enabled - should invoke bank analytics
3. Banking query with tool disabled - should NOT generate chart
4. Banking query with tool enabled - should generate chart
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.routers.chat.handlers.streaming_handler import StreamingHandler
from src.schemas.chat import ChatRequest


class TestBankAdvisorActivation:
    """Test suite for BankAdvisor conditional activation."""

    @pytest.fixture
    def streaming_handler(self, mock_settings):
        """Create StreamingHandler instance for testing."""
        return StreamingHandler(settings=mock_settings)

    @pytest.fixture
    def base_chat_request(self):
        """Base chat request without BankAdvisor enabled."""
        return ChatRequest(
            message="¿Cuál es el IMOR de INVEX?",
            chat_id=None,
            model="claude-3-5-sonnet",
            temperature=0.3,
            max_tokens=800,
            stream=True,
            tools_enabled={},  # No tools enabled
        )

    @pytest.fixture
    def chat_request_with_bank_advisor(self, base_chat_request):
        """Chat request with BankAdvisor enabled."""
        request = base_chat_request.model_copy()
        request.tools_enabled = {"bank-advisor": True}
        return request

    @pytest.mark.asyncio
    async def test_bank_advisor_disabled_skips_analytics(
        self,
        streaming_handler,
        base_chat_request,
        mock_user
    ):
        """
        Test Case 1: BankAdvisor disabled - should NOT invoke bank analytics

        Given: User sends banking query without BankAdvisor enabled
        When: Request is processed
        Then: invoke_bank_analytics should NOT be called
        """
        user_id = mock_user.id

        with patch(
            "src.services.tool_execution_service.ToolExecutionService.invoke_bank_analytics",
            new_callable=AsyncMock,
            return_value=None
        ) as mock_invoke_bank_analytics:

            # Mock other dependencies
            with patch(
                "src.routers.chat.handlers.streaming_handler.ChatService"
            ) as mock_chat_service, \
            patch(
                "src.routers.chat.handlers.streaming_handler.get_redis_cache"
            ) as mock_cache:

                # Setup mocks
                mock_session = MagicMock()
                mock_session.id = "test-session-id"
                mock_session.user_id = user_id

                mock_chat_service_instance = mock_chat_service.return_value
                mock_chat_service_instance.get_or_create_session = AsyncMock(
                    return_value=mock_session
                )
                mock_chat_service_instance.add_user_message = AsyncMock(
                    return_value=MagicMock(id="msg-123")
                )

                mock_cache.return_value = AsyncMock()

                # Mock the streaming response to avoid full execution
                with patch.object(
                    streaming_handler,
                    "_stream_chat_response",
                    return_value=AsyncMock()
                ):
                    try:
                        # Execute the handler
                        async for _ in streaming_handler.handle_stream(
                            request=base_chat_request,
                            user_id=user_id
                        ):
                            pass
                    except StopAsyncIteration:
                        pass

                # Verify: invoke_bank_analytics was NOT called
                mock_invoke_bank_analytics.assert_not_called()

    @pytest.mark.asyncio
    async def test_bank_advisor_enabled_invokes_analytics(
        self,
        streaming_handler,
        chat_request_with_bank_advisor,
        mock_user
    ):
        """
        Test Case 2: BankAdvisor enabled - should invoke bank analytics

        Given: User sends banking query WITH BankAdvisor enabled
        When: Request is processed
        Then: invoke_bank_analytics should be called
        """
        user_id = mock_user.id

        # Mock bank analytics response
        mock_bank_data = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
            "plotly_config": {"data": [], "layout": {}},
        }

        with patch(
            "src.services.tool_execution_service.ToolExecutionService.invoke_bank_analytics",
            new_callable=AsyncMock,
            return_value=mock_bank_data
        ) as mock_invoke_bank_analytics:

            # Mock other dependencies
            with patch(
                "src.routers.chat.handlers.streaming_handler.ChatService"
            ) as mock_chat_service, \
            patch(
                "src.routers.chat.handlers.streaming_handler.get_redis_cache"
            ) as mock_cache:

                # Setup mocks
                mock_session = MagicMock()
                mock_session.id = "test-session-id"
                mock_session.user_id = user_id

                mock_chat_service_instance = mock_chat_service.return_value
                mock_chat_service_instance.get_or_create_session = AsyncMock(
                    return_value=mock_session
                )
                mock_chat_service_instance.add_user_message = AsyncMock(
                    return_value=MagicMock(id="msg-123")
                )

                mock_cache.return_value = AsyncMock()

                # Mock the streaming response
                with patch.object(
                    streaming_handler,
                    "_stream_chat_response",
                    return_value=AsyncMock()
                ):
                    try:
                        async for _ in streaming_handler.handle_stream(
                            request=chat_request_with_bank_advisor,
                            user_id=user_id
                        ):
                            pass
                    except StopAsyncIteration:
                        pass

                # Verify: invoke_bank_analytics WAS called
                mock_invoke_bank_analytics.assert_called_once()

                # Verify it was called with correct parameters
                call_args = mock_invoke_bank_analytics.call_args
                assert call_args.kwargs["user_id"] == user_id
                assert "IMOR" in call_args.kwargs["message"].upper()

    @pytest.mark.asyncio
    async def test_alternative_tool_name_bank_analytics(
        self,
        streaming_handler,
        base_chat_request,
        mock_user
    ):
        """
        Test Case 3: Alternative tool name 'bank_analytics' also works

        Given: User enables tool as 'bank_analytics' (alternative name)
        When: Request is processed
        Then: invoke_bank_analytics should still be called
        """
        user_id = mock_user.id

        # Use alternative tool name
        request = base_chat_request.model_copy()
        request.tools_enabled = {"bank_analytics": True}

        mock_bank_data = {
            "metric_name": "imor",
            "bank_names": ["INVEX"],
        }

        with patch(
            "src.services.tool_execution_service.ToolExecutionService.invoke_bank_analytics",
            new_callable=AsyncMock,
            return_value=mock_bank_data
        ) as mock_invoke_bank_analytics:

            with patch(
                "src.routers.chat.handlers.streaming_handler.ChatService"
            ) as mock_chat_service, \
            patch(
                "src.routers.chat.handlers.streaming_handler.get_redis_cache"
            ):
                mock_session = MagicMock()
                mock_session.id = "test-session-id"
                mock_session.user_id = user_id

                mock_chat_service_instance = mock_chat_service.return_value
                mock_chat_service_instance.get_or_create_session = AsyncMock(
                    return_value=mock_session
                )
                mock_chat_service_instance.add_user_message = AsyncMock(
                    return_value=MagicMock(id="msg-123")
                )

                with patch.object(
                    streaming_handler,
                    "_stream_chat_response",
                    return_value=AsyncMock()
                ):
                    try:
                        async for _ in streaming_handler.handle_stream(
                            request=request,
                            user_id=user_id
                        ):
                            pass
                    except StopAsyncIteration:
                        pass

                # Verify: invoke_bank_analytics WAS called with alternative name
                mock_invoke_bank_analytics.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_banking_query_with_tool_enabled(
        self,
        streaming_handler,
        mock_user
    ):
        """
        Test Case 4: Non-banking query with tool enabled

        Given: User sends non-banking query WITH BankAdvisor enabled
        When: Request is processed
        Then: invoke_bank_analytics is called but returns None (not a banking query)
        """
        user_id = mock_user.id

        request = ChatRequest(
            message="¿Cómo estás?",  # Non-banking query
            chat_id=None,
            model="claude-3-5-sonnet",
            stream=True,
            tools_enabled={"bank-advisor": True}
        )

        with patch(
            "src.services.tool_execution_service.ToolExecutionService.invoke_bank_analytics",
            new_callable=AsyncMock,
            return_value=None
        ) as mock_invoke_bank_analytics:

            with patch(
                "src.routers.chat.handlers.streaming_handler.ChatService"
            ) as mock_chat_service, \
            patch(
                "src.routers.chat.handlers.streaming_handler.get_redis_cache"
            ):
                mock_session = MagicMock()
                mock_session.id = "test-session-id"
                mock_session.user_id = user_id

                mock_chat_service_instance = mock_chat_service.return_value
                mock_chat_service_instance.get_or_create_session = AsyncMock(
                    return_value=mock_session
                )
                mock_chat_service_instance.add_user_message = AsyncMock(
                    return_value=MagicMock(id="msg-123")
                )

                with patch.object(
                    streaming_handler,
                    "_stream_chat_response",
                    return_value=AsyncMock()
                ):
                    try:
                        async for _ in streaming_handler.handle_stream(
                            request=request,
                            user_id=user_id
                        ):
                            pass
                    except StopAsyncIteration:
                        pass

                # Verify: Was called (tool enabled) but returned None (not banking)
                mock_invoke_bank_analytics.assert_called_once()
