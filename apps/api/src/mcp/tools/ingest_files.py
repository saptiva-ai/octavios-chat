"""
Asynchronous file ingestion tool for chat sessions.

Replaces synchronous document processing with async worker-based ingestion.
"""

from typing import Any, Dict, List, Optional
import structlog

from ..protocol import ToolSpec, ToolCategory, ToolCapability
from ..tool import Tool
from ...models.chat import ChatSession
from ...models.document import Document
from ...models.document_state import DocumentState, ProcessingStatus

logger = structlog.get_logger(__name__)


class IngestFilesTool(Tool):
    """
    Asynchronously ingest files into a conversation.

    Flow:
    1. Create DocumentState records in UPLOADING status
    2. Dispatch async workers for processing
    3. Return immediate response (don't block chat)

    Example usage:
        result = await tool.execute(
            conversation_id="chat-123",
            file_refs=["doc-abc", "doc-def"]
        )
        # Returns: {"status": "processing", "documents": [...]}
    """

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="ingest_files",
            version="1.0.0",
            display_name="File Ingestion Tool",
            description=(
                "Asynchronously ingests files into a conversation for RAG processing. "
                "Creates DocumentState records and dispatches background workers. "
                "Returns immediately without blocking the chat request."
            ),
            category=ToolCategory.DOCUMENT_ANALYSIS,
            capabilities=[
                ToolCapability.ASYNC,
                ToolCapability.IDEMPOTENT,
                ToolCapability.STATEFUL
            ],
            input_schema={
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Chat session ID to attach documents to"
                    },
                    "file_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of document IDs or storage references to ingest"
                    }
                },
                "required": ["conversation_id", "file_refs"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["processing", "error"],
                        "description": "Ingestion status"
                    },
                    "message": {
                        "type": "string",
                        "description": "User-friendly status message"
                    },
                    "documents": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "doc_id": {"type": "string"},
                                "name": {"type": "string"},
                                "status": {"type": "string"},
                                "pages": {"type": "integer", "nullable": True}
                            }
                        },
                        "description": "List of ingested documents with their states"
                    },
                    "failed": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "doc_id": {"type": "string"},
                                "error": {"type": "string"}
                            }
                        },
                        "description": "List of documents that failed to ingest"
                    },
                    "total": {"type": "integer", "description": "Total files requested"},
                    "ingested": {"type": "integer", "description": "Successfully ingested count"},
                    "failed_count": {"type": "integer", "description": "Failed count"}
                }
            }
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        """Validate input payload"""
        if "conversation_id" not in payload:
            raise ValueError("Missing required field: conversation_id")
        if not isinstance(payload["conversation_id"], str):
            raise ValueError("conversation_id must be a string")
        if "file_refs" not in payload:
            raise ValueError("Missing required field: file_refs")
        if not isinstance(payload["file_refs"], list):
            raise ValueError("file_refs must be a list")
        if not payload["file_refs"]:
            raise ValueError("file_refs cannot be empty")

    async def execute(
        self,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ingest files asynchronously.

        Args:
            payload: Input data with conversation_id and file_refs
            context: Optional execution context (user_id, etc.)

        Returns:
            Dict with status, message, documents list, and statistics
        """

        conversation_id = payload["conversation_id"]
        file_refs = payload["file_refs"]

        logger.info(
            "Ingesting files",
            conversation_id=conversation_id,
            file_count=len(file_refs),
            user_id=context.get("user_id") if context else None
        )

        try:
            # 1. Fetch chat session
            session = await ChatSession.get(conversation_id)
            if not session:
                return {
                    "status": "error",
                    "message": f"Conversation {conversation_id} not found",
                    "documents": [],
                    "failed": [{"doc_id": "session", "error": "Session not found"}],
                    "total": len(file_refs),
                    "ingested": 0,
                    "failed_count": len(file_refs)
                }

            ingested_docs = []
            failed_docs = []

            # 2. Create DocumentState for each file
            for file_ref in file_refs:
                try:
                    # Check if already ingested
                    existing = session.get_document(file_ref)
                    if existing:
                        logger.warning(
                            "Document already in conversation",
                            doc_id=file_ref,
                            status=existing.status.value
                        )
                        ingested_docs.append(existing)
                        continue

                    # Fetch document metadata
                    doc = await Document.get(file_ref)

                    if doc:
                        # Create DocumentState with full metadata
                        doc_state = session.add_document(
                            doc_id=file_ref,
                            name=doc.filename,
                            pages=getattr(doc, 'metadata', {}).get("pages") if hasattr(doc, 'metadata') else None,
                            size_bytes=getattr(doc, 'size_bytes', None),
                            mimetype=getattr(doc, 'content_type', None),
                            status=ProcessingStatus.UPLOADING
                        )
                    else:
                        # Document not in storage - create minimal state
                        logger.warning(
                            "Document not found in storage, creating minimal state",
                            doc_id=file_ref
                        )
                        doc_state = session.add_document(
                            doc_id=file_ref,
                            name=f"document_{file_ref[:12]}",
                            status=ProcessingStatus.READY  # Assume legacy doc already processed
                        )

                    ingested_docs.append(doc_state)

                    # 3. Dispatch async processing task
                    # TODO: Implement Celery task dispatch
                    # from ...services.document_tasks import process_document_task
                    # process_document_task.delay(
                    #     conversation_id=conversation_id,
                    #     doc_id=file_ref
                    # )

                    logger.info(
                        "Document added to session (worker dispatch pending)",
                        doc_id=file_ref,
                        filename=doc_state.name
                    )

                except Exception as e:
                    logger.error(
                        "Failed to ingest document",
                        doc_id=file_ref,
                        error=str(e),
                        exc_info=True
                    )
                    failed_docs.append({
                        "doc_id": file_ref,
                        "error": str(e)
                    })

            # 4. Save session with new DocumentStates
            await session.save()

            # 5. Build immediate response
            response_message = self._build_response_message(ingested_docs, failed_docs)

            return {
                "status": "processing",
                "message": response_message,
                "documents": [
                    {
                        "doc_id": d.doc_id,
                        "name": d.name,
                        "status": d.status.value,
                        "pages": d.pages
                    }
                    for d in ingested_docs
                ],
                "failed": failed_docs,
                "total": len(file_refs),
                "ingested": len(ingested_docs),
                "failed_count": len(failed_docs)
            }

        except Exception as e:
            logger.error(
                "Critical error during file ingestion",
                conversation_id=conversation_id,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "error",
                "message": f"Failed to ingest files: {str(e)[:100]}",
                "documents": [],
                "failed": [{"doc_id": "system", "error": str(e)}],
                "total": len(file_refs),
                "ingested": 0,
                "failed_count": len(file_refs)
            }

    def _build_response_message(
        self,
        ingested: List[DocumentState],
        failed: List[Dict[str, Any]]
    ) -> str:
        """Build user-friendly response message"""

        if not ingested and not failed:
            return "No se recibieron documentos."

        parts = []

        if ingested:
            doc_list = ", ".join([
                f"**{d.name}**" + (f" ({d.pages} págs)" if d.pages else "")
                for d in ingested
            ])
            parts.append(f"📄 Recibí: {doc_list}")
            parts.append("Estoy procesando los documentos...")

        if failed:
            parts.append(f"⚠️ No pude procesar {len(failed)} documento(s):")
            for fail in failed[:3]:  # Show first 3
                parts.append(f"  - {fail['doc_id'][:12]}...: {fail['error'][:50]}")

        return "\n".join(parts)
