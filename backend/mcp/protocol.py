"""Shared Pydantic contracts for MCP."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ToolError(BaseModel):
    """Structured error emitted by a tool."""

    code: str = Field(..., description="Machine-friendly error code")
    message: str = Field(..., description="Human readable message")
    retryable: bool = Field(False, description="Whether the request can be retried safely")
    details: Dict[str, Any] = Field(default_factory=dict, description="Optional contextual metadata")


class ToolLimits(BaseModel):
    """Execution limits advertised by a tool."""

    timeout_ms: int = Field(60000, ge=1, description="Soft timeout applied to the tool invocation")
    max_payload_kb: int = Field(64, ge=1, description="Maximum payload size in kilobytes")
    max_attachment_mb: int = Field(25, ge=0, description="Maximum attachment size in megabytes")


class ToolSpec(BaseModel):
    """Public metadata describing a tool."""

    name: str
    version: str = "v1"
    description: str
    capabilities: List[str] = Field(default_factory=list, description="Free-form tags describing behaviour")
    input_schema: Dict[str, Any] = Field(..., description="JSON schema for request payload")
    output_schema: Dict[str, Any] = Field(..., description="JSON schema for response payload")
    limits: ToolLimits = Field(default_factory=ToolLimits)
    owner: str = Field("copilot-os", description="Owning service or team")


class ToolInvokeContext(BaseModel):
    """Invocation context populated by the HTTP adapter."""

    request_id: str = Field(..., description="Request identifier for tracing")
    user_id: Optional[str] = Field(None, description="End-user executing the tool")
    session_id: Optional[str] = Field(None, description="Chat session or conversation identifier")
    trace_id: Optional[str] = Field(None, description="External trace/correlation id")
    source: str = Field("api", description="Caller surface (api, chat, scheduler, etc.)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context shared with tools")


class ToolInvokeRequest(BaseModel):
    """HTTP payload for POST /mcp/invoke."""

    tool: str = Field(..., description="Tool name")
    version: Optional[str] = Field(default=None, description="Optional version, defaults to latest")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Tool specific payload")

    @field_validator("tool")
    @classmethod
    def _normalize_tool(cls, value: str) -> str:
        """Normalize tool names for consistent routing."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("tool must not be empty")
        return normalized


class ToolInvokeResponse(BaseModel):
    """Normalized tool response returned to callers."""

    tool: str
    version: str
    ok: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[ToolError] = None
    latency_ms: int = Field(..., ge=0)
    request_id: str
    trace_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolDiscoveryResponse(BaseModel):
    """Response model for GET /mcp/tools."""

    tools: List[ToolSpec]
