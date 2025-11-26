"""
Unit tests for ToolExecutionService.

Tests:
- invoke_relevant_tools logic
- Caching mechanism (hit/miss/set)
- Tool execution delegation
- Error resilience
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import json
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'src'))

from src.services.tool_execution_service import ToolExecutionService, TOOL_CACHE_TTL
from src.core.constants import TOOL_NAME_AUDIT, TOOL_NAME_EXCEL
from src.domain.chat_context import ChatContext


@pytest.fixture
def mock_redis():
    """Mock Redis cache."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def mock_mcp_adapter():
    """Mock MCP adapter."""
    adapter = AsyncMock()
    # _get_tool_map returns a dict of tool implementations
    tool_map = {
        TOOL_NAME_AUDIT: AsyncMock(),
        TOOL_NAME_EXCEL: AsyncMock()
    }
    adapter._get_tool_map = AsyncMock(return_value=tool_map)
    adapter._execute_tool_impl = AsyncMock()
    return adapter


@pytest.fixture
def mock_context():
    """Mock ChatContext."""
    context = Mock(spec=ChatContext)
    context.tools_enabled = {TOOL_NAME_AUDIT: True, TOOL_NAME_EXCEL: True}
    context.document_ids = ["doc-123"]
    return context


@pytest.mark.unit
class TestToolExecutionService:
    """Test suite for ToolExecutionService."""

    @pytest.mark.asyncio
    async def test_skips_when_no_tools_enabled(self, mock_context):
        """Should return empty dict if no tools are enabled."""
        mock_context.tools_enabled = {}
        
        with patch('src.services.tool_execution_service.get_redis_cache', new_callable=AsyncMock), \
             patch('src.services.tool_execution_service.get_mcp_adapter', new_callable=AsyncMock) as mock_get_adapter:
            
            results = await ToolExecutionService.invoke_relevant_tools(mock_context, "user-123")
            
            assert results == {}
            mock_get_adapter.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_documents(self, mock_context):
        """Should return empty dict if no documents are attached."""
        mock_context.document_ids = []
        
        with patch('src.services.tool_execution_service.get_redis_cache', new_callable=AsyncMock), \
             patch('src.services.tool_execution_service.get_mcp_adapter', new_callable=AsyncMock) as mock_get_adapter:
            
            results = await ToolExecutionService.invoke_relevant_tools(mock_context, "user-123")
            
            assert results == {}
            mock_get_adapter.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_audit_tool_cache_miss(self, mock_context, mock_redis, mock_mcp_adapter):
        """Should execute audit tool and cache result on cache miss."""
        # Setup
        mock_mcp_adapter._execute_tool_impl.return_value = {"findings": ["issue1"]}
        
        with patch('src.services.tool_execution_service.get_redis_cache', return_value=mock_redis), \
             patch('src.services.tool_execution_service.get_mcp_adapter', return_value=mock_mcp_adapter):
            
            results = await ToolExecutionService.invoke_relevant_tools(mock_context, "user-123")
            
            # Verification
            assert f"{TOOL_NAME_AUDIT}_doc-123" in results
            assert results[f"{TOOL_NAME_AUDIT}_doc-123"] == {"findings": ["issue1"]}
            
            # Verify execution
            mock_mcp_adapter._execute_tool_impl.assert_called_once()
            call_args = mock_mcp_adapter._execute_tool_impl.call_args
            assert call_args.kwargs["tool_name"] == TOOL_NAME_AUDIT
            assert call_args.kwargs["payload"]["doc_id"] == "doc-123"
            
            # Verify caching
            mock_redis.get.assert_called_once()
            mock_redis.set.assert_called_once()
            set_args = mock_redis.set.call_args
            assert set_args.kwargs["expire"] == TOOL_CACHE_TTL[TOOL_NAME_AUDIT]

    @pytest.mark.asyncio
    async def test_returns_cached_audit_result(self, mock_context, mock_redis, mock_mcp_adapter):
        """Should return cached result and skip execution on cache hit."""
        # Setup cache hit
        cached_data = {"findings": ["cached_issue"]}
        mock_redis.get.return_value = cached_data
        
        with patch('src.services.tool_execution_service.get_redis_cache', return_value=mock_redis), \
             patch('src.services.tool_execution_service.get_mcp_adapter', return_value=mock_mcp_adapter):
            
            results = await ToolExecutionService.invoke_relevant_tools(mock_context, "user-123")
            
            # Verification
            assert results[f"{TOOL_NAME_AUDIT}_doc-123"] == cached_data
            
            # Verify NO execution
            mock_mcp_adapter._execute_tool_impl.assert_not_called()
            
            # Verify cache read
            mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_executes_excel_tool_for_spreadsheets(self, mock_context, mock_redis, mock_mcp_adapter):
        """Should execute excel analyzer only for spreadsheet files."""
        # Setup Document mock
        mock_doc = AsyncMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        mock_mcp_adapter._execute_tool_impl.return_value = {"sheets": ["Sheet1"]}
        
        with patch('src.services.tool_execution_service.get_redis_cache', return_value=mock_redis), \
             patch('src.services.tool_execution_service.get_mcp_adapter', return_value=mock_mcp_adapter), \
             patch('src.models.document.Document.get', return_value=mock_doc):
            
            # Enable excel tool, disable audit for clarity
            mock_context.tools_enabled = {TOOL_NAME_EXCEL: True}
            
            results = await ToolExecutionService.invoke_relevant_tools(mock_context, "user-123")
            
            # Verification
            assert f"{TOOL_NAME_EXCEL}_doc-123" in results
            assert results[f"{TOOL_NAME_EXCEL}_doc-123"] == {"sheets": ["Sheet1"]}
            
            mock_mcp_adapter._execute_tool_impl.assert_called_once()
            assert mock_mcp_adapter._execute_tool_impl.call_args.kwargs["tool_name"] == TOOL_NAME_EXCEL

    @pytest.mark.asyncio
    async def test_skips_excel_tool_for_non_spreadsheets(self, mock_context, mock_redis, mock_mcp_adapter):
        """Should skip excel analyzer for non-spreadsheet files (e.g. PDF)."""
        # Setup PDF Document mock
        mock_doc = AsyncMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/pdf"
        
        with patch('src.services.tool_execution_service.get_redis_cache', return_value=mock_redis), \
             patch('src.services.tool_execution_service.get_mcp_adapter', return_value=mock_mcp_adapter), \
             patch('src.models.document.Document.get', return_value=mock_doc):
            
            mock_context.tools_enabled = {TOOL_NAME_EXCEL: True}
            
            results = await ToolExecutionService.invoke_relevant_tools(mock_context, "user-123")
            
            # Verification - should be empty as PDF is not Excel
            assert results == {}
            mock_mcp_adapter._execute_tool_impl.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_execution_error_gracefully(self, mock_context, mock_redis, mock_mcp_adapter):
        """Should continue if one tool fails."""
        # Setup execution failure
        mock_mcp_adapter._execute_tool_impl.side_effect = Exception("MCP Error")
        
        with patch('src.services.tool_execution_service.get_redis_cache', return_value=mock_redis), \
             patch('src.services.tool_execution_service.get_mcp_adapter', return_value=mock_mcp_adapter):
            
            results = await ToolExecutionService.invoke_relevant_tools(mock_context, "user-123")
            
            # Verification - should return empty dict, not raise exception
            assert results == {}
            
            # Should verify it tried to execute
            mock_mcp_adapter._execute_tool_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_read_failure_fallback(self, mock_context, mock_redis, mock_mcp_adapter):
        """Should execute tool even if cache read fails."""
        # Setup cache failure
        mock_redis.get.side_effect = Exception("Redis down")
        mock_mcp_adapter._execute_tool_impl.return_value = {"result": "ok"}
        
        with patch('src.services.tool_execution_service.get_redis_cache', return_value=mock_redis), \
             patch('src.services.tool_execution_service.get_mcp_adapter', return_value=mock_mcp_adapter):
            
            results = await ToolExecutionService.invoke_relevant_tools(mock_context, "user-123")
            
            # Should have executed despite redis error
            assert f"{TOOL_NAME_AUDIT}_doc-123" in results
            mock_mcp_adapter._execute_tool_impl.assert_called_once()
