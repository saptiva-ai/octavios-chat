"""
Retrieve relevant document segments for RAG.

Loads document segments from cache and ranks by relevance to user question.
"""

from typing import Any, Dict, List, Optional
import structlog

from ..protocol import ToolSpec, ToolCategory, ToolCapability
from ..tool import Tool
from ...models.chat import ChatSession
from ...models.document_state import ProcessingStatus
from ...core.redis_cache import get_redis_cache

logger = structlog.get_logger(__name__)


class GetRelevantSegmentsTool(Tool):
    """
    Retrieve relevant document segments for answering questions.

    Flow:
    1. Find documents with status=READY in conversation
    2. Load segments from Redis cache
    3. Score/rank segments by relevance (keyword matching)
    4. Return top N segments with metadata

    Future enhancements:
    - Vector embeddings for semantic search
    - Re-ranking with cross-encoder
    - Hybrid retrieval (BM25 + semantic)

    Example usage:
        result = await tool.execute(
            conversation_id="chat-123",
            question="What is the pricing model?",
            max_segments=5
        )
        # Returns: {"segments": [...], "total_docs": 3}
    """

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_relevant_segments",
            version="1.0.0",
            display_name="Document Segment Retrieval",
            description=(
                "Retrieves relevant document segments for RAG-based question answering. "
                "Loads cached segments from ready documents, ranks by relevance, "
                "and returns top matches with source attribution."
            ),
            category=ToolCategory.DOCUMENT_ANALYSIS,
            capabilities=[
                ToolCapability.SYNC,
                ToolCapability.CACHEABLE,
                ToolCapability.STATEFUL
            ],
            input_schema={
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Chat session ID"
                    },
                    "question": {
                        "type": "string",
                        "description": "User's question for segment retrieval"
                    },
                    "target_docs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional filter by document IDs or names",
                        "default": None
                    },
                    "max_segments": {
                        "type": "integer",
                        "description": "Maximum segments to return",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20
                    }
                },
                "required": ["conversation_id", "question"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "segments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "doc_id": {"type": "string"},
                                "doc_name": {"type": "string"},
                                "index": {"type": "integer"},
                                "text": {"type": "string"},
                                "score": {"type": "number"}
                            }
                        },
                        "description": "Ranked segments with relevance scores"
                    },
                    "message": {
                        "type": "string",
                        "description": "User-friendly status message"
                    },
                    "total_docs": {"type": "integer"},
                    "ready_docs": {"type": "integer"},
                    "total_segments": {"type": "integer"},
                    "returned_segments": {"type": "integer"}
                }
            }
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        """Validate input payload"""
        if "conversation_id" not in payload:
            raise ValueError("Missing required field: conversation_id")
        if not isinstance(payload["conversation_id"], str):
            raise ValueError("conversation_id must be a string")
        if "question" not in payload:
            raise ValueError("Missing required field: question")
        if not isinstance(payload["question"], str):
            raise ValueError("question must be a string")
        if not payload["question"].strip():
            raise ValueError("question cannot be empty")

        # Validate optional fields
        if "max_segments" in payload:
            max_seg = payload["max_segments"]
            if not isinstance(max_seg, int) or max_seg < 1 or max_seg > 20:
                raise ValueError("max_segments must be an integer between 1 and 20")

        if "target_docs" in payload and payload["target_docs"] is not None:
            if not isinstance(payload["target_docs"], list):
                raise ValueError("target_docs must be a list")

    async def execute(
        self,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Retrieve segments relevant to question.

        Args:
            payload: Input data with conversation_id, question, optional filters
            context: Optional execution context

        Returns:
            Dict with ranked segments and statistics
        """

        conversation_id = payload["conversation_id"]
        question = payload["question"]
        target_docs = payload.get("target_docs")
        max_segments = payload.get("max_segments", 5)

        logger.info(
            "Retrieving segments",
            conversation_id=conversation_id,
            question_preview=question[:100],
            target_docs=target_docs,
            max_segments=max_segments
        )

        try:
            # 1. Fetch session
            session = await ChatSession.get(conversation_id)
            if not session:
                return {
                    "segments": [],
                    "message": f"Conversación {conversation_id} no encontrada.",
                    "total_docs": 0,
                    "ready_docs": 0,
                    "total_segments": 0,
                    "returned_segments": 0
                }

            # 2. Filter ready documents
            ready_docs = session.get_ready_documents()

            if target_docs:
                ready_docs = [
                    d for d in ready_docs
                    if d.name in target_docs or d.doc_id in target_docs
                ]

            if not ready_docs:
                logger.warning(
                    "No ready documents found",
                    conversation_id=conversation_id,
                    total_docs=len(session.documents),
                    target_docs=target_docs
                )
                return {
                    "segments": [],
                    "message": "No hay documentos procesados disponibles. Los documentos aún se están procesando.",
                    "total_docs": len(session.documents),
                    "ready_docs": 0,
                    "total_segments": 0,
                    "returned_segments": 0
                }

            # 3. Load and score segments
            all_segments = []
            cache = await get_redis_cache()

            for doc in ready_docs:
                cache_key = f"doc_segments:{doc.doc_id}"
                segments = await cache.get(cache_key)

                if not segments:
                    logger.warning(
                        "Segments not in cache (document may need reprocessing)",
                        doc_id=doc.doc_id,
                        doc_name=doc.name
                    )
                    continue

                # Score each segment
                for seg in segments:
                    score = self._score_segment(seg["text"], question)
                    all_segments.append({
                        "doc_id": doc.doc_id,
                        "doc_name": doc.name,
                        "index": seg["index"],
                        "text": seg["text"],
                        "score": score
                    })

            if not all_segments:
                return {
                    "segments": [],
                    "message": "Los documentos están listos pero no tienen segmentos en caché. Intenta volver a procesar los archivos.",
                    "total_docs": len(session.documents),
                    "ready_docs": len(ready_docs),
                    "total_segments": 0,
                    "returned_segments": 0
                }

            # 4. Rank and return top N
            all_segments.sort(key=lambda x: x["score"], reverse=True)
            top_segments = all_segments[:max_segments]

            logger.info(
                "Segments retrieved successfully",
                total_segments=len(all_segments),
                returned=len(top_segments),
                ready_docs=len(ready_docs)
            )

            return {
                "segments": top_segments,
                "message": f"Encontré {len(top_segments)} segmentos relevantes de {len(ready_docs)} documento(s).",
                "total_docs": len(session.documents),
                "ready_docs": len(ready_docs),
                "total_segments": len(all_segments),
                "returned_segments": len(top_segments)
            }

        except Exception as e:
            logger.error(
                "Failed to retrieve segments",
                conversation_id=conversation_id,
                error=str(e),
                exc_info=True
            )
            return {
                "segments": [],
                "message": f"Error al recuperar segmentos: {str(e)[:100]}",
                "total_docs": 0,
                "ready_docs": 0,
                "total_segments": 0,
                "returned_segments": 0
            }

    def _score_segment(self, text: str, question: str) -> float:
        """
        Simple keyword-based scoring (BM25-lite).

        Future improvements:
        - Use sentence transformers for semantic similarity
        - Implement proper BM25 with term frequency
        - Add cross-encoder re-ranking

        Args:
            text: Segment text
            question: User's question

        Returns:
            Relevance score (0.0 to 1.0+)
        """

        text_lower = text.lower()
        question_lower = question.lower()

        # Extract keywords (simple tokenization)
        # TODO: Use proper tokenizer (e.g., spaCy, NLTK)
        question_words = [
            w.strip(".,!?;:()[]{}")
            for w in question_lower.split()
            if len(w) > 3  # Skip short words
        ]

        if not question_words:
            return 0.0

        # Count keyword matches
        matches = sum(1 for word in question_words if word in text_lower)

        # Normalize by question length
        score = matches / len(question_words)

        # Boost if question is substring (exact phrase match)
        if question_lower in text_lower:
            score += 0.5

        return score
