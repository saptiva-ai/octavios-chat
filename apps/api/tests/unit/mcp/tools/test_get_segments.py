"""
Unit tests for GetRelevantSegmentsTool.

Tests cover:
- Input validation
- Segment retrieval and ranking
- Error handling
- Scoring algorithm
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.mcp.tools.get_segments import GetRelevantSegmentsTool
from src.models.document_state import ProcessingStatus
from src.models.chat import ChatSession


class TestGetSegmentsToolSpec:
    """Test tool specification."""

    def test_get_spec(self):
        """Should return valid ToolSpec."""
        tool = GetRelevantSegmentsTool()
        spec = tool.get_spec()

        assert spec.name == "get_relevant_segments"
        assert spec.version == "1.0.0"
        assert "sync" in [c.value for c in spec.capabilities]
        assert "cacheable" in [c.value for c in spec.capabilities]
        assert "conversation_id" in spec.input_schema["required"]
        assert "question" in spec.input_schema["required"]


class TestInputValidation:
    """Test input payload validation."""

    @pytest.mark.asyncio
    async def test_missing_conversation_id(self):
        """Should raise ValueError if conversation_id missing."""
        tool = GetRelevantSegmentsTool()

        with pytest.raises(ValueError, match="Missing required field: conversation_id"):
            await tool.validate_input({"question": "test"})

    @pytest.mark.asyncio
    async def test_missing_question(self):
        """Should raise ValueError if question missing."""
        tool = GetRelevantSegmentsTool()

        with pytest.raises(ValueError, match="Missing required field: question"):
            await tool.validate_input({"conversation_id": "chat-123"})

    @pytest.mark.asyncio
    async def test_empty_question(self):
        """Should raise ValueError if question is empty."""
        tool = GetRelevantSegmentsTool()

        with pytest.raises(ValueError, match="question cannot be empty"):
            await tool.validate_input({
                "conversation_id": "chat-123",
                "question": "   "
            })

    @pytest.mark.asyncio
    async def test_invalid_max_segments(self):
        """Should raise ValueError if max_segments out of range."""
        tool = GetRelevantSegmentsTool()

        with pytest.raises(ValueError, match="max_segments must be an integer between 1 and 20"):
            await tool.validate_input({
                "conversation_id": "chat-123",
                "question": "test",
                "max_segments": 50
            })

    @pytest.mark.asyncio
    async def test_valid_payload(self):
        """Should not raise for valid payload."""
        tool = GetRelevantSegmentsTool()

        # Should not raise
        await tool.validate_input({
            "conversation_id": "chat-123",
            "question": "What is the pricing?",
            "max_segments": 10
        })


class TestSegmentRetrieval:
    """Test segment retrieval logic."""

    @pytest.mark.asyncio
    async def test_session_not_found(self):
        """Should return empty result if session doesn't exist."""
        tool = GetRelevantSegmentsTool()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=None):
            result = await tool.execute({
                "conversation_id": "nonexistent",
                "question": "test question"
            })

            assert result["segments"] == []
            assert result["total_docs"] == 0
            assert "no encontrada" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_no_ready_documents(self):
        """Should return empty result if no documents are ready."""
        tool = GetRelevantSegmentsTool()

        # Mock session with no ready docs
        mock_session = MagicMock(spec=ChatSession)
        mock_session.documents = []
        mock_session.get_ready_documents = MagicMock(return_value=[])

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session):
            result = await tool.execute({
                "conversation_id": "chat-123",
                "question": "test question"
            })

            assert result["segments"] == []
            assert result["ready_docs"] == 0
            assert "no hay documentos procesados" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_segments_not_in_cache(self):
        """Should handle missing cache gracefully."""
        tool = GetRelevantSegmentsTool()

        # Mock session with ready doc
        mock_doc = MagicMock()
        mock_doc.doc_id = "doc-123"
        mock_doc.name = "test.pdf"
        mock_doc.is_ready = MagicMock(return_value=True)

        mock_session = MagicMock(spec=ChatSession)
        mock_session.documents = [mock_doc]
        mock_session.get_ready_documents = MagicMock(return_value=[mock_doc])

        # Mock cache returning None
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch('src.mcp.tools.get_segments.get_redis_cache', new_callable=AsyncMock, return_value=mock_cache):

            result = await tool.execute({
                "conversation_id": "chat-123",
                "question": "test question"
            })

            assert result["segments"] == []
            assert result["ready_docs"] == 1
            assert "no tienen segmentos" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_successful_retrieval(self):
        """Should retrieve and rank segments successfully."""
        tool = GetRelevantSegmentsTool()

        # Mock document
        mock_doc = MagicMock()
        mock_doc.doc_id = "doc-123"
        mock_doc.name = "pricing.pdf"

        # Mock session
        mock_session = MagicMock(spec=ChatSession)
        mock_session.documents = [mock_doc]
        mock_session.get_ready_documents = MagicMock(return_value=[mock_doc])

        # Mock cached segments
        cached_segments = [
            {"index": 0, "text": "The pricing model is based on usage."},
            {"index": 1, "text": "Support is available 24/7."},
            {"index": 2, "text": "Pricing starts at $99 per month."}
        ]

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=cached_segments)

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch('src.mcp.tools.get_segments.get_redis_cache', new_callable=AsyncMock, return_value=mock_cache):

            result = await tool.execute({
                "conversation_id": "chat-123",
                "question": "What is the pricing model?"
            })

            assert len(result["segments"]) > 0
            assert result["ready_docs"] == 1
            assert result["total_segments"] == 3
            assert all("score" in seg for seg in result["segments"])
            assert all("doc_name" in seg for seg in result["segments"])

    @pytest.mark.asyncio
    async def test_max_segments_limit(self):
        """Should respect max_segments parameter."""
        tool = GetRelevantSegmentsTool()

        # Mock document
        mock_doc = MagicMock()
        mock_doc.doc_id = "doc-123"
        mock_doc.name = "test.pdf"

        # Mock session
        mock_session = MagicMock(spec=ChatSession)
        mock_session.documents = [mock_doc]
        mock_session.get_ready_documents = MagicMock(return_value=[mock_doc])

        # Create many segments
        cached_segments = [
            {"index": i, "text": f"Segment {i} with test content"}
            for i in range(20)
        ]

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=cached_segments)

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch('src.mcp.tools.get_segments.get_redis_cache', new_callable=AsyncMock, return_value=mock_cache):

            result = await tool.execute({
                "conversation_id": "chat-123",
                "question": "test",
                "max_segments": 3
            })

            assert len(result["segments"]) <= 3
            assert result["total_segments"] == 20


class TestScoringAlgorithm:
    """Test segment scoring logic."""

    def test_score_exact_match(self):
        """Should give high score for exact phrase match."""
        tool = GetRelevantSegmentsTool()

        text = "The pricing model is subscription-based."
        question = "pricing model"

        score = tool._score_segment(text, question)

        # Should have keyword matches + exact phrase bonus
        assert score > 0.5

    def test_score_keyword_matches(self):
        """Should score based on keyword overlap."""
        tool = GetRelevantSegmentsTool()

        text = "Our product offers advanced analytics and reporting."
        question = "product analytics features"

        score = tool._score_segment(text, question)

        # Should match "product" and "analytics"
        assert score > 0

    def test_score_no_matches(self):
        """Should give zero score for no matches."""
        tool = GetRelevantSegmentsTool()

        text = "The weather today is sunny."
        question = "database pricing"

        score = tool._score_segment(text, question)

        assert score == 0.0

    def test_score_case_insensitive(self):
        """Should be case insensitive."""
        tool = GetRelevantSegmentsTool()

        text = "PRICING INFORMATION"
        question = "pricing information"

        score = tool._score_segment(text, question)

        assert score > 0


class TestErrorHandling:
    """Test error scenarios."""

    @pytest.mark.asyncio
    async def test_cache_exception(self):
        """Should handle cache errors gracefully."""
        tool = GetRelevantSegmentsTool()

        mock_doc = MagicMock()
        mock_doc.doc_id = "doc-123"
        mock_doc.name = "test.pdf"

        mock_session = MagicMock(spec=ChatSession)
        mock_session.documents = [mock_doc]
        mock_session.get_ready_documents = MagicMock(return_value=[mock_doc])

        # Mock cache that raises exception
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(side_effect=Exception("Redis connection failed"))

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch('src.mcp.tools.get_segments.get_redis_cache', new_callable=AsyncMock, return_value=mock_cache):

            result = await tool.execute({
                "conversation_id": "chat-123",
                "question": "test"
            })

            # Should return error response
            assert result["segments"] == []
            assert "error" in result["message"].lower()
