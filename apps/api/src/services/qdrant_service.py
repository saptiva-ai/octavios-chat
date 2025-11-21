"""
Qdrant Vector Database Service for RAG

Architecture Decision Record (ADR):
-----------------------------------
1. **Single Collection Strategy**: One collection "rag_documents" with metadata filtering
   - Rationale: Easier TTL management, simpler queries, better for multi-document search
   - Alternative rejected: Per-session collections (management overhead, no cross-doc search)

2. **Distance Metric: Cosine**
   - Rationale: Normalized embeddings, robust to model changes, interpretable scores [-1, 1]
   - Alternative: Dot product (similar performance but less interpretable)

3. **Mandatory session_id Filter**: Defense in depth
   - All queries MUST include session_id filter
   - Prevents context leakage between conversations
   - Enforced at: API layer → Service layer → Query construction

4. **Payload Schema**:
   {
     "session_id": str,        # Conversation UUID (MANDATORY for isolation)
     "document_id": str,        # MongoDB Document._id
     "chunk_id": int,           # Sequential index within document
     "text": str,               # Original chunk text (for LLM context)
     "page": int,               # Page number in PDF
     "created_at": float,       # Unix timestamp (for TTL cleanup)
     "metadata": {              # Extensible metadata
       "filename": str,
       "content_type": str,
       ...
     }
   }

Resource Estimation:
-------------------
Assumptions:
- Embedding dimension: 384 (paraphrase-multilingual-MiniLM-L12-v2)
- Chunks per document: ~100
- Documents per session: ~3
- Active sessions (24h TTL): ~50

Storage calculation:
- Vector: 384 dims × 4 bytes = 1,536 bytes
- Payload: ~1,500 bytes (text + metadata)
- Total per point: ~3 KB
- Total: 50 sessions × 3 docs × 100 chunks × 3 KB = ~45 MB
- With HNSW index overhead (~30%): ~60 MB

Performance expectations:
- Ingestion: ~50ms per chunk (embedding generation)
- Query latency: <10ms for <100k points (HNSW)
- Memory: ~200-300 MB with model loaded
"""

import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
    CollectionInfo,
)
from qdrant_client.http.exceptions import UnexpectedResponse

import structlog

logger = structlog.get_logger(__name__)


class QdrantService:
    """
    Service for managing RAG vectors in Qdrant.

    Responsibilities:
    - Collection lifecycle (create, health check)
    - Vector ingestion (upsert chunks with embeddings)
    - Semantic search (query with session_id filter)
    - TTL cleanup (delete expired points)
    - Session deletion (remove all points for a session)

    Thread-safety: QdrantClient is thread-safe. This service can be used in async contexts.
    """

    def __init__(self):
        """
        Initialize Qdrant client and configuration.

        Environment variables:
        - QDRANT_HOST: Hostname (default: "qdrant")
        - QDRANT_PORT: HTTP port (default: 6333)
        - QDRANT_COLLECTION_NAME: Collection name (default: "rag_documents")
        - QDRANT_EMBEDDING_DIM: Vector dimension (default: 384)
        """
        self.host = os.getenv("QDRANT_HOST", "qdrant")
        self.port = int(os.getenv("QDRANT_PORT", "6333"))
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "rag_documents")
        self.embedding_dim = int(os.getenv("QDRANT_EMBEDDING_DIM", "384"))

        # Initialize client
        # Note: check_compatibility=False to avoid warnings with server v1.7.4 vs client v1.16+
        # The API we use (collections, points, search) is stable across these versions
        self.client = QdrantClient(
            host=self.host,
            port=self.port,
            timeout=10,  # 10 seconds timeout for HTTP requests
            check_compatibility=False,  # Suppress version mismatch warnings
        )

        logger.info(
            "Qdrant service initialized",
            host=self.host,
            port=self.port,
            collection=self.collection_name,
            embedding_dim=self.embedding_dim,
        )

    def ensure_collection(self) -> None:
        """
        Ensure the RAG collection exists with correct configuration.

        If collection doesn't exist, create it.
        If it exists with different config, log warning (don't recreate to preserve data).

        Raises:
            RuntimeError: If Qdrant is unreachable
        """
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name in collection_names:
                # Validate configuration
                collection_info: CollectionInfo = self.client.get_collection(
                    collection_name=self.collection_name
                )

                actual_dim = collection_info.config.params.vectors.size
                actual_distance = collection_info.config.params.vectors.distance

                if actual_dim != self.embedding_dim:
                    logger.warning(
                        "Collection dimension mismatch",
                        expected=self.embedding_dim,
                        actual=actual_dim,
                        collection=self.collection_name,
                        action="Using existing collection (not recreating to preserve data)",
                    )

                if actual_distance != Distance.COSINE:
                    logger.warning(
                        "Collection distance metric mismatch",
                        expected="COSINE",
                        actual=str(actual_distance),
                        collection=self.collection_name,
                    )

                logger.info(
                    "Qdrant collection already exists",
                    collection=self.collection_name,
                    points_count=collection_info.points_count,
                    indexed_vectors_count=collection_info.indexed_vectors_count,
                )
            else:
                # Create collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE,
                    ),
                )

                logger.info(
                    "Qdrant collection created",
                    collection=self.collection_name,
                    embedding_dim=self.embedding_dim,
                    distance="COSINE",
                )

        except Exception as e:
            logger.error(
                "Failed to ensure Qdrant collection",
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Qdrant collection setup failed: {e}") from e

    def health_check(self) -> Dict[str, Any]:
        """
        Check Qdrant service health.

        Returns:
            Dict with health status:
            {
                "status": "healthy" | "unhealthy",
                "collection_exists": bool,
                "points_count": int,
                "error": str (if unhealthy)
            }
        """
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name not in collection_names:
                return {
                    "status": "unhealthy",
                    "collection_exists": False,
                    "points_count": 0,
                    "error": f"Collection '{self.collection_name}' does not exist",
                }

            # Get collection info
            collection_info = self.client.get_collection(
                collection_name=self.collection_name
            )

            return {
                "status": "healthy",
                "collection_exists": True,
                "points_count": collection_info.points_count,
                # vectors_count not available in Qdrant 1.7.x, only indexed_vectors_count
                "indexed_vectors_count": collection_info.indexed_vectors_count,
            }

        except Exception as e:
            logger.error("Qdrant health check failed", error=str(e), exc_info=True)
            return {
                "status": "unhealthy",
                "collection_exists": False,
                "points_count": 0,
                "error": str(e),
            }

    def upsert_chunks(
        self,
        session_id: str,
        document_id: str,
        chunks: List[Dict[str, Any]],
    ) -> int:
        """
        Insert or update document chunks with embeddings.

        Args:
            session_id: Conversation UUID (MANDATORY for session isolation)
            document_id: MongoDB Document._id
            chunks: List of dicts with keys:
                - chunk_id: int (sequential index)
                - text: str (chunk text)
                - embedding: List[float] (384-dim vector)
                - page: int (page number)
                - metadata: dict (optional additional fields)

        Returns:
            Number of points upserted

        Raises:
            ValueError: If session_id or document_id is missing/invalid
            RuntimeError: If upsert fails
        """
        if not session_id or not isinstance(session_id, str):
            raise ValueError("session_id must be a non-empty string")

        if not document_id or not isinstance(document_id, str):
            raise ValueError("document_id must be a non-empty string")

        if not chunks:
            logger.warning(
                "No chunks to upsert",
                session_id=session_id,
                document_id=document_id,
            )
            return 0

        try:
            points = []
            current_timestamp = time.time()

            for chunk in chunks:
                # Validate chunk structure
                if "embedding" not in chunk:
                    logger.error(
                        "Chunk missing 'embedding' field",
                        chunk_id=chunk.get("chunk_id"),
                        session_id=session_id,
                        document_id=document_id,
                    )
                    continue

                if len(chunk["embedding"]) != self.embedding_dim:
                    logger.error(
                        "Embedding dimension mismatch",
                        expected=self.embedding_dim,
                        actual=len(chunk["embedding"]),
                        chunk_id=chunk.get("chunk_id"),
                    )
                    continue

                # Generate unique point ID using UUID
                # Qdrant requires UUIDs or integers, not arbitrary strings
                import uuid
                import hashlib

                # Create deterministic UUID from document_id + chunk_id
                # This ensures same doc+chunk always gets same ID (idempotent upserts)
                unique_string = f"{document_id}_{chunk['chunk_id']}"
                point_id = str(uuid.UUID(hashlib.md5(unique_string.encode()).hexdigest()))

                # Build payload
                payload = {
                    # CRITICAL: Session isolation fields
                    "session_id": session_id,
                    "document_id": document_id,
                    "chunk_id": chunk["chunk_id"],

                    # Context for LLM
                    "text": chunk["text"],

                    # Metadata
                    "page": chunk.get("page", 0),
                    "created_at": current_timestamp,

                    # Extensible metadata
                    "metadata": chunk.get("metadata", {}),
                }

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=chunk["embedding"],
                        payload=payload,
                    )
                )

            # Upsert batch
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

            logger.info(
                "Chunks upserted to Qdrant",
                session_id=session_id,
                document_id=document_id,
                chunks_count=len(points),
                collection=self.collection_name,
            )

            return len(points)

        except Exception as e:
            logger.error(
                "Failed to upsert chunks to Qdrant",
                session_id=session_id,
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Qdrant upsert failed: {e}") from e

    def search(
        self,
        session_id: str,
        query_vector: List[float],
        top_k: int = 3,
        score_threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for relevant chunks within a session.

        CRITICAL: This method ALWAYS filters by session_id to prevent context leakage.

        Args:
            session_id: Conversation UUID (MANDATORY)
            query_vector: Embedding of user's question (384-dim)
            top_k: Maximum number of results (default: 3)
            score_threshold: Minimum similarity score (default: 0.7)

        Returns:
            List of dicts:
            [
                {
                    "document_id": str,
                    "chunk_id": int,
                    "text": str,
                    "page": int,
                    "score": float,  # Cosine similarity [-1, 1]
                    "metadata": dict,
                },
                ...
            ]

        Raises:
            ValueError: If session_id is missing or query_vector dimension is wrong
        """
        if not session_id or not isinstance(session_id, str):
            raise ValueError("session_id must be a non-empty string")

        if len(query_vector) != self.embedding_dim:
            raise ValueError(
                f"Query vector dimension mismatch: expected {self.embedding_dim}, got {len(query_vector)}"
            )

        try:
            # MANDATORY session filter - NO EXCEPTIONS
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="session_id",
                        match=MatchValue(value=session_id),
                    )
                ]
            )

            # Search with filter
            # Note: API changed - use query_points in newer versions
            search_result = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                query_filter=query_filter,
                score_threshold=score_threshold,
            ).points

            # Format results
            results = []
            for hit in search_result:
                results.append({
                    "document_id": hit.payload["document_id"],
                    "chunk_id": hit.payload["chunk_id"],
                    "text": hit.payload["text"],
                    "page": hit.payload["page"],
                    "score": hit.score,
                    "metadata": hit.payload.get("metadata", {}),
                })

            logger.info(
                "Qdrant search completed",
                session_id=session_id,
                results_count=len(results),
                top_k=top_k,
                score_threshold=score_threshold,
                avg_score=sum(r["score"] for r in results) / len(results) if results else 0,
            )

            return results

        except Exception as e:
            logger.error(
                "Qdrant search failed",
                session_id=session_id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Qdrant search failed: {e}") from e

    def delete_session(self, session_id: str) -> int:
        """
        Delete all vectors for a given session.

        Called when user deletes a conversation.

        Args:
            session_id: Conversation UUID

        Returns:
            Number of points deleted (approximate)
        """
        if not session_id:
            raise ValueError("session_id must be non-empty")

        try:
            # Count points before deletion (for logging)
            count_before = self.client.count(
                collection_name=self.collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="session_id",
                            match=MatchValue(value=session_id),
                        )
                    ]
                ),
            ).count

            # Delete all points with this session_id
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="session_id",
                            match=MatchValue(value=session_id),
                        )
                    ]
                ),
            )

            logger.info(
                "Session deleted from Qdrant",
                session_id=session_id,
                points_deleted=count_before,
            )

            return count_before

        except Exception as e:
            logger.error(
                "Failed to delete session from Qdrant",
                session_id=session_id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Qdrant session deletion failed: {e}") from e

    def cleanup_expired_sessions(self, ttl_hours: int = 24) -> int:
        """
        Delete points older than TTL.

        Called periodically by cleanup job (e.g., every hour via APScheduler).

        Args:
            ttl_hours: Time-to-live in hours (default: 24)

        Returns:
            Number of points deleted (approximate)
        """
        try:
            # Calculate cutoff timestamp
            cutoff_time = time.time() - (ttl_hours * 3600)

            # Count points before deletion
            count_before = self.client.count(
                collection_name=self.collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="created_at",
                            range=Range(lt=cutoff_time),
                        )
                    ]
                ),
            ).count

            if count_before == 0:
                logger.info("No expired points to clean up", ttl_hours=ttl_hours)
                return 0

            # Delete expired points
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="created_at",
                            range=Range(lt=cutoff_time),
                        )
                    ]
                ),
            )

            logger.info(
                "Expired sessions cleaned up",
                ttl_hours=ttl_hours,
                cutoff_timestamp=cutoff_time,
                points_deleted=count_before,
            )

            return count_before

        except Exception as e:
            logger.error(
                "Failed to cleanup expired sessions",
                ttl_hours=ttl_hours,
                error=str(e),
                exc_info=True,
            )
            # Don't raise - cleanup failures shouldn't crash the app
            return 0


# Singleton instance
_qdrant_service: Optional[QdrantService] = None


def get_qdrant_service() -> QdrantService:
    """
    Get or create singleton Qdrant service instance.

    This is the preferred way to access QdrantService in the app.

    Returns:
        QdrantService instance
    """
    global _qdrant_service

    if _qdrant_service is None:
        _qdrant_service = QdrantService()
        # Ensure collection exists on first access
        _qdrant_service.ensure_collection()

    return _qdrant_service
