"""
Unit tests for Nl2SqlContextService

Tests RAG context retrieval with mocked Qdrant and Embedding services.
"""

import pytest
import sys
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from bankadvisor.specs import QuerySpec, TimeRangeSpec, RagContext
from bankadvisor.services.nl2sql_context_service import Nl2SqlContextService

# Mock qdrant_client module for testing (not available in test environment)
if 'qdrant_client' not in sys.modules:
    sys.modules['qdrant_client'] = MagicMock()
    sys.modules['qdrant_client.models'] = MagicMock()


class TestNl2SqlContextService:
    """Test suite for NL2SQL context service."""

    @pytest.fixture
    def mock_qdrant(self):
        """Mock Qdrant service."""
        mock = Mock()
        mock.client = Mock()

        # Mock get_collections
        mock_collection = Mock()
        mock_collection.name = "bankadvisor_schema"
        mock.client.get_collections.return_value = Mock(collections=[mock_collection])

        # Mock query_points
        mock.client.query_points.return_value = Mock(points=[])

        return mock

    @pytest.fixture
    def mock_embedding(self):
        """Mock embedding service."""
        mock = Mock()
        mock.embedding_dim = 384
        mock.encode_single = Mock(return_value=[0.1] * 384)
        return mock

    @pytest.fixture
    def service_with_rag(self, mock_qdrant, mock_embedding):
        """Create service with RAG enabled."""
        return Nl2SqlContextService(
            qdrant_service=mock_qdrant,
            embedding_service=mock_embedding
        )

    @pytest.fixture
    def service_without_rag(self):
        """Create service with RAG disabled (fallback mode)."""
        return Nl2SqlContextService(
            qdrant_service=None,
            embedding_service=None
        )

    @pytest.mark.asyncio
    async def test_rag_disabled_returns_minimal_context(self, service_without_rag):
        """Test that service returns minimal context when RAG is disabled."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="last_n_months", n=3)
        )

        ctx = await service_without_rag.rag_context_for_spec(spec)

        assert isinstance(ctx, RagContext)
        assert ctx.metric_definitions == []
        assert ctx.schema_snippets == []
        assert ctx.example_queries == []
        assert len(ctx.available_columns) > 0  # Should have whitelist columns

    @pytest.mark.asyncio
    async def test_rag_enabled_calls_qdrant(self, service_with_rag, mock_qdrant, mock_embedding):
        """Test that service queries Qdrant when RAG is enabled."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="last_n_months", n=3)
        )

        # Mock Qdrant search results
        mock_hit = Mock()
        mock_hit.payload = {"metric_name": "IMOR", "description": "Test"}
        mock_hit.score = 0.9
        mock_qdrant.client.query_points.return_value = Mock(points=[mock_hit])

        ctx = await service_with_rag.rag_context_for_spec(spec, original_query="IMOR de INVEX")

        # Verify embedding was called
        assert mock_embedding.encode_single.call_count >= 1

        # Verify Qdrant was queried (3 collections: metrics, schema, examples)
        assert mock_qdrant.client.query_points.call_count >= 1

        # Verify context was populated
        assert isinstance(ctx, RagContext)
        assert len(ctx.available_columns) > 0

    @pytest.mark.asyncio
    async def test_build_metric_query(self, service_with_rag):
        """Test metric query construction."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX", "SISTEMA"],
            time_range=TimeRangeSpec(type="year", start_date="2024-01-01", end_date="2024-12-31")
        )

        query = service_with_rag._build_metric_query(spec)

        assert "IMOR" in query
        assert "INVEX" in query
        assert "SISTEMA" in query
        assert "banking metric" in query

    @pytest.mark.asyncio
    async def test_build_schema_query(self, service_with_rag):
        """Test schema query construction."""
        spec = QuerySpec(
            metric="CARTERA_COMERCIAL",
            bank_names=[],
            time_range=TimeRangeSpec(type="all")
        )

        query = service_with_rag._build_schema_query(spec)

        assert "CARTERA_COMERCIAL" in query
        assert "monthly_kpis" in query
        assert "column" in query

    @pytest.mark.asyncio
    async def test_build_example_query(self, service_with_rag):
        """Test example query construction."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="last_n_months", n=3)
        )

        query = service_with_rag._build_example_query(spec)

        assert "IMOR" in query
        assert "INVEX" in query
        assert "últimos 3 meses" in query

    @pytest.mark.asyncio
    async def test_fallback_on_qdrant_error(self, service_with_rag, mock_qdrant):
        """Test that service falls back gracefully on Qdrant errors."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=["INVEX"],
            time_range=TimeRangeSpec(type="all")
        )

        # Simulate Qdrant error
        mock_qdrant.client.query_points.side_effect = Exception("Qdrant unavailable")

        ctx = await service_with_rag.rag_context_for_spec(spec)

        # Should return minimal context (not crash)
        assert isinstance(ctx, RagContext)
        assert ctx.metric_definitions == []
        assert ctx.schema_snippets == []
        assert ctx.example_queries == []
        assert len(ctx.available_columns) > 0

    @pytest.mark.asyncio
    async def test_search_collection_not_found(self, service_with_rag, mock_qdrant):
        """Test handling of missing collections."""
        # Mock empty collections list
        mock_qdrant.client.get_collections.return_value = Mock(collections=[])

        results = await service_with_rag._search_collection(
            collection="bankadvisor_metrics",
            query_text="IMOR",
            top_k=3,
            score_threshold=0.7
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_ensure_collections_creates_missing(self, service_with_rag, mock_qdrant):
        """Test that ensure_collections creates missing collections."""
        # Mock no existing collections
        mock_qdrant.client.get_collections.return_value = Mock(collections=[])

        service_with_rag.ensure_collections()

        # Should have called create_collection for each of 3 collections
        assert mock_qdrant.client.create_collection.call_count == 3

    @pytest.mark.asyncio
    async def test_available_columns_from_analytics_service(self, service_without_rag):
        """Test that available_columns is populated from AnalyticsService."""
        spec = QuerySpec(
            metric="IMOR",
            bank_names=[],
            time_range=TimeRangeSpec(type="all")
        )

        ctx = await service_without_rag.rag_context_for_spec(spec)

        # Should have columns from SAFE_METRIC_COLUMNS
        assert "imor" in ctx.available_columns
        assert "icor" in ctx.available_columns
        assert "cartera_total" in ctx.available_columns
