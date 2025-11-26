"""
Document Models for COPILOTO_414 Plugin.

Simplified models for stateless processing (no database dependencies).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class PageFragment(BaseModel):
    """
    Represents a fragment of text from a PDF page.

    Used by auditors to analyze specific regions of a document.
    """

    fragment_id: str = Field(..., description="Unique fragment identifier")
    page: int = Field(..., description="Page number (1-indexed)")
    kind: str = Field(..., description="Fragment type: paragraph, footer, header, table")
    bbox: List[float] = Field(
        default_factory=list,
        description="Bounding box [x0, y0, x1, y1] as percentages"
    )
    text: str = Field(..., description="Extracted text content")


class PageContent(BaseModel):
    """
    Represents the content of a single page.

    Used for passing document data to the plugin.
    """

    page: int = Field(..., description="Page number (1-indexed)")
    text_md: str = Field("", description="Extracted text in markdown format")
    text_raw: Optional[str] = Field(None, description="Raw text without formatting")


class DocumentInput(BaseModel):
    """
    Input model for document validation.

    This is what the MCP tool receives from the caller.
    """

    filename: str = Field(..., description="Original filename")
    file_path: Optional[str] = Field(None, description="Path to PDF file on disk")
    file_bytes: Optional[bytes] = Field(None, description="PDF file content as bytes")
    pages: List[PageContent] = Field(
        default_factory=list,
        description="Pre-extracted page content (optional, for optimization)"
    )
    total_pages: int = Field(0, description="Total number of pages")
    ocr_applied: bool = Field(False, description="Whether OCR was applied")
    processing_metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata from document processing"
    )

    class Config:
        arbitrary_types_allowed = True
