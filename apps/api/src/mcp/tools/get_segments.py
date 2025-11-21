"""
Retrieve relevant document segments for RAG using semantic search.

Uses Qdrant vector database for semantic similarity search:
- Generates embedding for user's question
- Performs cosine similarity search in Qdrant
- Filters by session_id and document_id for security
- Returns top-k segments with relevance scores
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import structlog

from ..protocol import ToolSpec, ToolCategory, ToolCapability
from ..tool import Tool
from ...models.chat import ChatSession
from ...models.document_state import ProcessingStatus
from ...services.embedding_service import get_embedding_service
from ...services.qdrant_service import get_qdrant_service

# NEW: Adaptive retrieval orchestrator
from ...services.retrieval import AdaptiveRetrievalOrchestrator
from ...services.query_understanding import QueryContext

logger = structlog.get_logger(__name__)


class GetRelevantSegmentsTool(Tool):
    """
    Retrieve relevant document segments for answering questions using semantic search.

    Flow:
    1. Find documents with status=READY in conversation
    2. Generate embedding for user's question
    3. Perform semantic search in Qdrant (cosine similarity)
    4. Return top N segments with metadata and relevance scores

    Semantic Search Architecture:
    - Embedding: paraphrase-multilingual-MiniLM-L12-v2 (384-dim)
    - Vector DB: Qdrant with cosine distance
    - Filtering: session_id + document_id (context isolation)
    - Score threshold: 0.7 (configurable)

    Future enhancements:
    - Re-ranking with cross-encoder
    - Hybrid retrieval (BM25 + semantic)

    Example usage:
        result = await tool.execute(
            conversation_id="chat-123",
            question="What is the pricing model?",
            max_segments=2
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
        max_segments = payload.get("max_segments", 2)

        logger.info(
            "Retrieving segments",
            conversation_id=conversation_id,
            question_preview=question[:100],
            target_docs=target_docs,
            max_segments=max_segments
        )

        try:
            # 1. Fetch session
            logger.info(
                "🔍 [RAG DEBUG] GetRelevantSegmentsTool fetching session",
                conversation_id=conversation_id,
                timestamp=datetime.utcnow().isoformat()
            )

            session = await ChatSession.get(conversation_id)
            if not session:
                logger.error(
                    "❌ [RAG DEBUG] Session not found in GetRelevantSegmentsTool",
                    conversation_id=conversation_id
                )
                return {
                    "segments": [],
                    "message": f"Conversación {conversation_id} no encontrada.",
                    "total_docs": 0,
                    "ready_docs": 0,
                    "total_segments": 0,
                    "returned_segments": 0
                }

            logger.info(
                "✅ [RAG DEBUG] Session fetched successfully",
                conversation_id=conversation_id,
                session_has_attached_file_ids=len(session.attached_file_ids),
                attached_file_ids=session.attached_file_ids,
                timestamp=datetime.utcnow().isoformat()
            )

            # 2. Fetch Document objects from attached_file_ids
            from ...models.document import Document, DocumentStatus

            ready_docs = []
            for doc_id in session.attached_file_ids:
                doc = await Document.get(doc_id)
                if doc and doc.status == DocumentStatus.READY:
                    ready_docs.append(doc)

            if target_docs:
                ready_docs = [
                    d for d in ready_docs
                    if d.filename in target_docs or str(d.id) in target_docs
                ]

            if not ready_docs:
                # Log detailed status of all documents for debugging
                all_docs = []
                for doc_id in session.attached_file_ids:
                    doc = await Document.get(doc_id)
                    if doc:
                        all_docs.append(f"{doc.filename}:{doc.status}")

                logger.warning(
                    "⚠️ [RAG DEBUG] No ready documents - User queried too early!",
                    conversation_id=conversation_id,
                    total_docs=len(session.attached_file_ids),
                    ready_docs=0,
                    target_docs=target_docs,
                    document_statuses=all_docs,
                    timestamp=datetime.utcnow().isoformat()
                )
                return {
                    "segments": [],
                    "message": "No hay documentos procesados disponibles. Los documentos aún se están procesando.",
                    "total_docs": len(session.attached_file_ids),
                    "ready_docs": 0,
                    "total_segments": 0,
                    "returned_segments": 0
                }

            # 3. NEW: Use Adaptive Retrieval Orchestrator
            logger.info(
                "🧠 [RAG ADAPTIVE] Using adaptive retrieval orchestrator",
                question_preview=question[:100]
            )

            # Build query context
            query_context = QueryContext(
                conversation_id=conversation_id,
                has_recent_entities=False,
                recent_entities=[],
                documents_count=len(ready_docs),
                previous_query=None
            )

            # Initialize orchestrator
            orchestrator = AdaptiveRetrievalOrchestrator()

            # Execute adaptive retrieval
            retrieval_result = await orchestrator.retrieve(
                query=question,
                session_id=conversation_id,
                documents=ready_docs,
                max_segments=max_segments,
                context=query_context
            )

            logger.info(
                "✅ [RAG ADAPTIVE] Retrieval completed",
                strategy_used=retrieval_result.strategy_used,
                segments_count=len(retrieval_result.segments),
                max_score=retrieval_result.max_score,
                avg_score=retrieval_result.avg_score,
                query_intent=retrieval_result.metadata.get("intent"),
                query_complexity=retrieval_result.metadata.get("complexity")
            )

            # Filter by target_docs if specified
            segments_list = retrieval_result.segments
            if target_docs:
                doc_ids = {str(d.id) for d in ready_docs}
                segments_list = [
                    s for s in segments_list
                    if s.doc_id in doc_ids
                ]
                logger.info(
                    "Filtered by target_docs",
                    before=len(retrieval_result.segments),
                    after=len(segments_list),
                    target_docs=target_docs
                )

            # Convert Segment objects to dict format
            all_segments = [segment.to_dict() for segment in segments_list]

            if not all_segments:
                return {
                    "segments": [],
                    "message": "No encontré segmentos relevantes en los documentos. Intenta reformular tu pregunta.",
                    "total_docs": len(session.attached_file_ids),
                    "ready_docs": len(ready_docs),
                    "total_segments": 0,
                    "returned_segments": 0,
                    "strategy_used": retrieval_result.strategy_used,
                    "query_analysis": {
                        "intent": retrieval_result.metadata.get("intent"),
                        "complexity": retrieval_result.metadata.get("complexity")
                    }
                }

            # Build user message with intelligence
            max_score = retrieval_result.max_score
            message = self._build_user_message(
                segments_count=len(all_segments),
                ready_docs_count=len(ready_docs),
                max_score=max_score,
                intent=retrieval_result.metadata.get("intent"),
                strategy=retrieval_result.strategy_used
            )

            logger.info(
                "✅ [RAG ADAPTIVE] Segments retrieved successfully",
                total_segments=len(all_segments),
                returned=len(all_segments),
                ready_docs=len(ready_docs),
                max_score=max_score,
                strategy=retrieval_result.strategy_used
            )

            return {
                "segments": all_segments,
                "message": message,
                "total_docs": len(session.attached_file_ids),
                "ready_docs": len(ready_docs),
                "total_segments": len(all_segments),
                "returned_segments": len(all_segments),
                "max_relevance_score": max_score,
                "strategy_used": retrieval_result.strategy_used,
                "query_analysis": {
                    "intent": retrieval_result.metadata.get("intent"),
                    "complexity": retrieval_result.metadata.get("complexity"),
                    "confidence": retrieval_result.confidence
                }
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

    def _build_user_message(
        self,
        segments_count: int,
        ready_docs_count: int,
        max_score: float,
        intent: str,
        strategy: str
    ) -> str:
        """
        Build intelligent user message based on retrieval results.

        Args:
            segments_count: Number of segments retrieved
            ready_docs_count: Number of ready documents
            max_score: Maximum relevance score
            intent: Query intent (overview, specific_fact, etc.)
            strategy: Retrieval strategy used

        Returns:
            User-friendly message explaining results
        """

        # For overview queries, message is simple
        if intent == "overview":
            return (
                f"Te proporciono un resumen general basado en los primeros "
                f"{segments_count} segmentos del documento. "
                f"Esto te dará una idea del contenido principal."
            )

        # For specific queries, include relevance information
        if max_score > 0.5:
            return (
                f"Encontré {segments_count} segmentos relevantes de {ready_docs_count} documento(s). "
                f"La información tiene alta relevancia semántica (score: {max_score:.2f})."
            )
        elif max_score > 0.2:
            return (
                f"Encontré {segments_count} segmentos de {ready_docs_count} documento(s) "
                f"con relevancia moderada (score: {max_score:.2f}). "
                f"La respuesta podría no ser completamente precisa."
            )
        else:
            return (
                f"⚠️ Encontré {segments_count} segmentos, pero la relevancia semántica es baja (score: {max_score:.2f}). "
                f"Te recomiendo reformular tu pregunta con más detalles específicos."
            )

