"""Model Context Protocol (MCP) primitives for OctaviOS backend."""

from .registry import ToolRegistry
from .protocol import (
    ToolSpec,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolInvokeContext,
    ToolError,
)

__all__ = [
    "ToolRegistry",
    "ToolSpec",
    "ToolInvokeRequest",
    "ToolInvokeResponse",
    "ToolInvokeContext",
    "ToolError",
]
