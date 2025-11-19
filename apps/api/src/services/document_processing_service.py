"""
Document Processing Service - SOLID refactored version.

Architecture:
- Service Layer: DocumentProcessingService (orchestration)
- Strategy Pattern: ITextSegmenter implementations
- Single Responsibility: Each class has one job
- Open/Closed: Easy to add new segmentation strategies
- Dependency Inversion: Depends on abstractions (ITextSegmenter)

Patterns:
- Service Layer (orchestration)
- Strategy Pattern (segmentation strategies)
- Template Method (processing flow)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import structlog

from ..models.chat import ChatSession
from ..models.document import Document, PageContent
from ..models.document_state import ProcessingStatus
from ..services.document_extraction import extract_text_from_file
from ..core.redis_cache import get_redis_cache

logger = structlog.get_logger(__name__)


# ============================================================================
# STRATEGY PATTERN: Text Segmentation
# ============================================================================

class ITextSegmenter(ABC):
    """
    Interface for text segmentation strategies.

    Follows Open/Closed Principle: New strategies can be added without modifying existing code.
    """

    @abstractmethod
    def segment(self, text: str) -> List[Dict[str, Any]]:
        """
        Segment text into retrievable chunks.

        Args:
            text: Full document text

        Returns:
            List of segments with metadata
        """
        pass


class WordBasedSegmenter(ITextSegmenter):
    """
    Word-based segmentation with overlap.

    Single Responsibility: Only handles word-based chunking.
    """

    def __init__(self, chunk_size: int = 1000, overlap_ratio: float = 0.25):
        """
        Initialize segmenter.

        Args:
            chunk_size: Target words per chunk
            overlap_ratio: Overlap between chunks (0.0 to 0.5)
        """
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if not 0.0 <= overlap_ratio <= 0.5:
            raise ValueError("overlap_ratio must be between 0.0 and 0.5")

        self.chunk_size = chunk_size
        self.overlap_ratio = overlap_ratio
        self.overlap_words = int(chunk_size * overlap_ratio)

    def segment(self, text: str) -> List[Dict[str, Any]]:
        """Segment text using word-based chunking."""
        words = text.split()

        if not words:
            return []

        segments = []
        i = 0

        while i < len(words):
            # Extract chunk
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)

            segments.append({
                "index": len(segments),
                "text": chunk_text,
                "word_count": len(chunk_words),
                "start_word": i,
                "end_word": i + len(chunk_words)
            })

            # Move forward with overlap
            i += self.chunk_size - self.overlap_words

        logger.debug(
            "Text segmented",
            total_words=len(words),
            segments_count=len(segments),
            chunk_size=self.chunk_size,
            overlap=self.overlap_words
        )

        return segments


class SentenceBasedSegmenter(ITextSegmenter):
    """
    Sentence-based segmentation (future implementation).

    Uses sentence boundaries for more coherent chunks.
    """

    def __init__(self, sentences_per_chunk: int = 10):
        self.sentences_per_chunk = sentences_per_chunk

    def segment(self, text: str) -> List[Dict[str, Any]]:
        """Segment text using sentence boundaries."""
        # TODO: Implement with nltk.sent_tokenize or spacy
        # For now, fallback to word-based
        fallback = WordBasedSegmenter(chunk_size=1000)
        return fallback.segment(text)


# ============================================================================
# SERVICE LAYER: Document Processing Orchestration
# ============================================================================

class DocumentProcessingService:
    """
    Service for document processing operations.

    Responsibilities:
    - Orchestrate document processing flow
    - Manage DocumentState lifecycle
    - Coordinate extraction, segmentation, caching

    Follows:
    - Single Responsibility: Only orchestrates processing
    - Dependency Inversion: Depends on ITextSegmenter abstraction
    - Open/Closed: Can use different segmenters without modification
    """

    def __init__(self, segmenter: Optional[ITextSegmenter] = None):
        """
        Initialize service.

        Args:
            segmenter: Text segmentation strategy (defaults to WordBasedSegmenter)
        """
        self.segmenter = segmenter or WordBasedSegmenter(chunk_size=1000, overlap_ratio=0.25)

    async def process_document(
        self,
        conversation_id: str,
        doc_id: str
    ) -> None:
        """
        Process document: extract → segment → cache.

        Template Method Pattern: Defines processing flow skeleton.

        Args:
            conversation_id: Chat session ID
            doc_id: Document ID to process

        Raises:
            ValueError: If session/document not found
            Exception: On processing errors (marks doc as FAILED)
        """

        logger.info(
            "Starting document processing",
            conversation_id=conversation_id,
            doc_id=doc_id
        )

        try:
            # Step 1: Validate and update status
            session = await self._get_session(conversation_id)
            doc_state = await self._validate_document_in_session(session, doc_id)

            await self._mark_processing(session, doc_state)

            # Step 2: Extract text
            document = await self._get_document_from_storage(doc_id)
            extracted_text = await self._extract_text(document)

            # Step 3: Segment text
            segments = self._segment_text(extracted_text)

            # Step 4: Cache segments
            await self._cache_segments(doc_id, segments)

            # Step 5: Mark as ready
            await self._mark_ready(session, doc_state, len(segments))

            logger.info(
                "Document processing complete",
                doc_id=doc_id,
                segments=len(segments)
            )

        except Exception as e:
            logger.error(
                "Document processing failed",
                conversation_id=conversation_id,
                doc_id=doc_id,
                error=str(e),
                exc_type=type(e).__name__,
                exc_info=True
            )

            await self._mark_failed(conversation_id, doc_id, str(e))
            raise

    async def reprocess_document(
        self,
        conversation_id: str,
        doc_id: str
    ) -> None:
        """
        Reprocess a document (useful for failed/stale documents).

        Args:
            conversation_id: Chat session ID
            doc_id: Document ID to reprocess
        """
        logger.info("Reprocessing document", conversation_id=conversation_id, doc_id=doc_id)

        session = await self._get_session(conversation_id)
        doc_state = await self._validate_document_in_session(session, doc_id)

        # Reset to UPLOADING
        doc_state.status = ProcessingStatus.UPLOADING
        doc_state.error = None
        doc_state.updated_at = datetime.utcnow()
        await session.save()

        # Trigger processing
        await self.process_document(conversation_id, doc_id)

    # ========================================================================
    # PRIVATE METHODS: Processing Steps (Template Method Pattern)
    # ========================================================================

    async def _get_session(self, conversation_id: str) -> ChatSession:
        """Get and validate chat session."""
        session = await ChatSession.get(conversation_id)
        if not session:
            raise ValueError(f"Session {conversation_id} not found")
        return session

    async def _validate_document_in_session(
        self,
        session: ChatSession,
        doc_id: str
    ) -> Any:  # DocumentState
        """Validate document exists in session."""
        doc_state = session.get_document(doc_id)
        if not doc_state:
            raise ValueError(f"Document {doc_id} not in session {session.id}")
        return doc_state

    async def _mark_processing(self, session: ChatSession, doc_state: Any) -> None:
        """Update DocumentState to PROCESSING."""
        doc_state.mark_processing()
        await session.save()

        logger.info(
            "Document marked as processing",
            doc_id=doc_state.doc_id,
            status=doc_state.status.value
        )

    async def _get_document_from_storage(self, doc_id: str) -> Document:
        """Fetch document from MongoDB storage."""
        document = await Document.get(doc_id)
        if not document:
            raise ValueError(f"Document {doc_id} not found in storage")
        return document

    async def _extract_text(self, document: Document) -> str:
        """Extract text from document using multi-tier strategy."""
        pages: List[PageContent] = await extract_text_from_file(
            file_path=Path(document.file_path),
            content_type=document.content_type
        )

        # Combine all pages
        extracted_text = "\n\n".join(page.text_md for page in pages if page.text_md)

        if not extracted_text or not extracted_text.strip():
            raise ValueError("Text extraction returned empty result")

        logger.info(
            "Text extracted successfully",
            doc_id=str(document.id),
            text_length=len(extracted_text),
            pages=len(pages),
            filename=document.filename
        )

        return extracted_text

    def _segment_text(self, text: str) -> List[Dict[str, Any]]:
        """Segment text using configured strategy."""
        segments = self.segmenter.segment(text)

        logger.info("Text segmented", segments_count=len(segments))

        return segments

    async def _cache_segments(self, doc_id: str, segments: List[Dict[str, Any]]) -> None:
        """Cache segments in Redis."""
        cache = await get_redis_cache()
        cache_key = f"doc_segments:{doc_id}"

        await cache.set(cache_key, segments, ttl=3600)  # 1 hour

        logger.info(
            "Segments cached",
            doc_id=doc_id,
            cache_key=cache_key,
            segments=len(segments)
        )

    async def _mark_ready(
        self,
        session: ChatSession,
        doc_state: Any,
        segments_count: int
    ) -> None:
        """Update DocumentState to READY."""
        doc_state.mark_ready(segments_count=segments_count)
        await session.save()

        logger.info(
            "Document marked as ready",
            doc_id=doc_state.doc_id,
            status=doc_state.status.value,
            segments=segments_count
        )

    async def _mark_failed(
        self,
        conversation_id: str,
        doc_id: str,
        error: str
    ) -> None:
        """Mark document as FAILED with error message."""
        try:
            session = await ChatSession.get(conversation_id)
            if session:
                doc_state = session.get_document(doc_id)
                if doc_state:
                    doc_state.mark_failed(error=error[:500])
                    await session.save()

                    logger.info(
                        "Document marked as failed",
                        doc_id=doc_id,
                        error=error[:100]
                    )
        except Exception as save_error:
            logger.error(
                "Failed to mark document as failed",
                doc_id=doc_id,
                error=str(save_error),
                exc_info=True
            )


# ============================================================================
# FACTORY: Create service instances
# ============================================================================

def create_document_processing_service(
    segmentation_strategy: str = "word_based"
) -> DocumentProcessingService:
    """
    Factory function to create DocumentProcessingService with specific strategy.

    Args:
        segmentation_strategy: "word_based" | "sentence_based"

    Returns:
        Configured DocumentProcessingService instance
    """
    if segmentation_strategy == "word_based":
        segmenter = WordBasedSegmenter(chunk_size=1000, overlap_ratio=0.25)
    elif segmentation_strategy == "sentence_based":
        segmenter = SentenceBasedSegmenter(sentences_per_chunk=10)
    else:
        raise ValueError(f"Unknown segmentation strategy: {segmentation_strategy}")

    return DocumentProcessingService(segmenter=segmenter)
