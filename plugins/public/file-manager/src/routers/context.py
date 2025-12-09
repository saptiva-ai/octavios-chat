"""
Context endpoints for attachment handling.
"""

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.context_service import prepare_context_payload

router = APIRouter()


class PrepareContextRequest(BaseModel):
    user_id: str = Field(..., description="Owner user ID")
    session_id: Optional[str] = Field(None, description="Chat session ID")
    request_file_ids: List[str] = Field(default_factory=list, description="File IDs provided in the current request")
    previous_file_ids: List[str] = Field(default_factory=list, description="Previously attached file IDs")
    max_docs: int = Field(3, ge=1, le=20, description="Maximum documents to include in context")
    max_chars_per_doc: int = Field(8000, ge=500, le=50000, description="Per-document character budget")
    max_total_chars: int = Field(16000, ge=1000, le=100000, description="Global character budget")


class PrepareContextResponse(BaseModel):
    current_file_ids: List[str]
    documents: List[dict]
    warnings: List[str]
    stats: dict
    combined_text: str
    session_id: Optional[str]
    user_id: str


@router.post("/context/prepare", response_model=PrepareContextResponse)
async def prepare_context(body: PrepareContextRequest) -> PrepareContextResponse:
    """
    Normalize file IDs, persist session context, and build a RAG-friendly payload
    from cached extractions.
    """
    payload = await prepare_context_payload(
        user_id=body.user_id,
        session_id=body.session_id,
        request_file_ids=body.request_file_ids,
        previous_file_ids=body.previous_file_ids,
        max_docs=body.max_docs,
        max_chars_per_doc=body.max_chars_per_doc,
        max_total_chars=body.max_total_chars,
    )
    return PrepareContextResponse(**payload)
