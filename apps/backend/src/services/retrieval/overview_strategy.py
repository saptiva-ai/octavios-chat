"""
Overview Retrieval Strategy - For generic document questions.

Used when user asks vague/general questions like:
- "¿Qué es esto?"
- "¿De qué trata?"
- "Resume el documento"

Strategy:
- Retrieve first N chunks from each document (provides context)
- No semantic search needed (user wants overview, not specific facts)
- Can optionally include document metadata
"""

from typing import List, Any
import structlog

from .retrieval_strategy import RetrievalStrategy
from .types import Segment
from ...services.qdrant_service import get_qdrant_service

logger = structlog.get_logger(__name__)


class OverviewRetrievalStrategy(RetrievalStrategy):
    """
    Retrieve document overview by returning first chunks.

    Best for:
    - Vague queries ("¿Qué es esto?")
    - Summary requests ("Resume el documento")
    - General exploration

    Rationale:
    - First chunks typically contain document intro/summary
    - No need for semantic search (we want breadth, not precision)
    - Fast and deterministic
    """

    def __init__(self, chunks_per_doc: int = 3):
        """
        Initialize strategy.

        Args:
            chunks_per_doc: Number of first chunks to retrieve per document
        """
        self.chunks_per_doc = chunks_per_doc

    async def retrieve(
        self,
        query: str,
        session_id: str,
        documents: List[Any],
        max_segments: int,
        **kwargs
    ) -> List[Segment]:
        """
        Retrieve first N chunks from each document.

        Args:
            query: User query (used for logging only)
            session_id: Session ID
            documents: List of ready documents
            max_segments: Maximum total segments to return

        Returns:
            List of Segment objects (first chunks from each doc)
        """

        logger.info(
            "Retrieving overview segments",
            query_preview=query[:50],
            session_id=session_id,
            documents_count=len(documents),
            chunks_per_doc=self.chunks_per_doc
        )

        qdrant_service = get_qdrant_service()
        all_segments = []

        # Get first N chunks from each document
        for doc in documents:
            # Scroll through Qdrant to get first chunks for this document
            # Filter by session_id AND document_id
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue

                # Scroll to get points for this specific document
                scroll_result = qdrant_service.client.scroll(
                    collection_name=qdrant_service.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="session_id",
                                match=MatchValue(value=session_id)
                            ),
                            FieldCondition(
                                key="document_id",
                                match=MatchValue(value=str(doc.id))
                            )
                        ]
                    ),
                    limit=self.chunks_per_doc,
                    with_payload=True,
                    with_vectors=False,
                    # order_by used to require a range index; scrolling without order works for small limits
                )

                points = scroll_result[0]

                for point in points:
                    segment = Segment(
                        doc_id=str(doc.id),
                        doc_name=doc.filename,
                        chunk_id=point.payload.get("chunk_id", 0),
                        text=point.payload.get("text", ""),
                        score=1.0,  # Overview chunks all have same score (not ranked)
                        page=point.payload.get("page", 0),
                        metadata=point.payload.get("metadata", {})
                    )
                    all_segments.append(segment)

            except Exception as e:
                logger.error(
                    "Failed to retrieve overview chunks for document",
                    doc_id=str(doc.id),
                    error=str(e),
                    exc_info=True
                )
                continue

        # Limit to max_segments
        segments = all_segments[:max_segments]

        self._log_retrieval(
            strategy_name="OverviewRetrievalStrategy",
            query=query,
            segments_count=len(segments),
            max_score=1.0,
            documents_processed=len(documents)
        )

        return segments
