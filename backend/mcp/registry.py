"""Tool registry with async invocation helpers."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolExecutionError
from .protocol import (
    ToolError,
    ToolInvokeContext,
    ToolInvokeResponse,
    ToolSpec,
)
from ._logging import get_logger

logger = get_logger(__name__)


class ToolNotFoundError(LookupError):
    """Raised when the requested tool/version is missing."""


class ToolRegistry:
    """In-memory registry of MCP tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, BaseTool]] = {}
        self._latest_version: Dict[str, str] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool implementation."""
        versions = self._tools.setdefault(tool.name, {})
        versions[tool.version] = tool
        self._latest_version[tool.name] = tool.version
        logger.info(
            "Registered MCP tool",
            tool=tool.name,
            version=tool.version,
            capabilities=list(tool.capabilities),
        )

    def unregister(self, tool_name: str, version: Optional[str] = None) -> None:
        """Remove a tool from the registry."""
        if tool_name not in self._tools:
            return
        if version is None:
            self._tools.pop(tool_name, None)
            self._latest_version.pop(tool_name, None)
            return
        versions = self._tools[tool_name]
        versions.pop(version, None)
        if not versions:
            self._tools.pop(tool_name, None)
            self._latest_version.pop(tool_name, None)
        elif self._latest_version.get(tool_name) == version:
            self._latest_version[tool_name] = sorted(versions.keys())[-1]

    def list_tools(self) -> List[ToolSpec]:
        """Return ToolSpec list for discovery."""
        specs: List[ToolSpec] = []
        for versions in self._tools.values():
            for tool in versions.values():
                specs.append(tool.spec())
        return sorted(specs, key=lambda spec: (spec.name, spec.version))

    def resolve(self, tool_name: str, version: Optional[str] = None) -> BaseTool:
        """Return a tool implementation or raise ToolNotFoundError."""
        versions = self._tools.get(tool_name)
        if not versions:
            raise ToolNotFoundError(f"Tool '{tool_name}' is not registered")

        resolved_version = version or self._latest_version.get(tool_name)
        if not resolved_version or resolved_version not in versions:
            raise ToolNotFoundError(
                f"Tool '{tool_name}' does not have version '{version}'"
            )
        return versions[resolved_version]

    async def invoke(
        self,
        tool_name: str,
        payload: Dict[str, Any],
        context: ToolInvokeContext,
        version: Optional[str] = None,
    ) -> ToolInvokeResponse:
        """Invoke a tool and return normalized response."""
        tool = self.resolve(tool_name, version)
        started = time.perf_counter()
        try:
            output = await tool.invoke(payload, context)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return ToolInvokeResponse(
                tool=tool.name,
                version=tool.version,
                ok=True,
                output=output,
                latency_ms=latency_ms,
                request_id=context.request_id,
                trace_id=context.trace_id,
                metadata={"capabilities": list(tool.capabilities)},
            )
        except ToolExecutionError as exc:
            logger.warning(
                "Tool invocation failed",
                tool=tool.name,
                version=tool.version,
                error=str(exc),
                code=getattr(exc, "code", "tool_error"),
                retryable=getattr(exc, "retryable", False),
                request_id=context.request_id,
            )
            return self._build_error_response(
                tool=tool,
                context=context,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=ToolError(
                    code=getattr(exc, "code", "tool_error"),
                    message=str(exc),
                    retryable=getattr(exc, "retryable", False),
                    details=getattr(exc, "details", {}),
                ),
            )
        except ToolNotFoundError:
            raise
        except Exception as exc:  # pragma: no cover - unexpected failure surface
            logger.error(
                "Tool invocation crashed",
                tool=tool.name,
                version=tool.version,
                error=str(exc),
                request_id=context.request_id,
                exc_info=True,
            )
            return self._build_error_response(
                tool=tool,
                context=context,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=ToolError(
                    code="internal_error",
                    message="Tool failed unexpectedly",
                    retryable=False,
                    details={"reason": str(exc)},
                ),
            )

    def _build_error_response(
        self,
        tool: BaseTool,
        context: ToolInvokeContext,
        latency_ms: int,
        error: ToolError,
    ) -> ToolInvokeResponse:
        return ToolInvokeResponse(
            tool=tool.name,
            version=tool.version,
            ok=False,
            error=error,
            output=None,
            latency_ms=latency_ms,
            request_id=context.request_id,
            trace_id=context.trace_id,
            metadata={"capabilities": list(tool.capabilities)},
        )
