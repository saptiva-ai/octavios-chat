"""Base abstractions for MCP tools."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from .protocol import ToolInvokeContext, ToolSpec, ToolLimits
from ._logging import get_logger

logger = get_logger(__name__)


class ToolExecutionError(RuntimeError):
    """Raised when the tool fails to produce a result."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "tool_error",
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}


class BaseTool(ABC):
    """Abstract base class for MCP tools."""

    name: str
    version: str = "v1"
    description: str = ""
    capabilities: tuple[str, ...] = ()
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    limits: ToolLimits = ToolLimits()

    def spec(self) -> ToolSpec:
        """Return ToolSpec for discovery."""
        return ToolSpec(
            name=self.name,
            version=self.version,
            description=self.description,
            capabilities=list(self.capabilities),
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
            limits=self.limits,
        )

    async def invoke(
        self,
        payload: Dict[str, Any],
        context: ToolInvokeContext,
    ) -> Dict[str, Any]:
        """Validate payload and delegate to concrete implementation."""
        parsed_payload = self.input_model(**payload)
        result = await self._call_with_timeout(parsed_payload, context)
        return self.output_model(**result).model_dump()

    async def _call_with_timeout(
        self,
        parsed_payload: BaseModel,
        context: ToolInvokeContext,
    ) -> Dict[str, Any]:
        timeout_seconds = max(self.limits.timeout_ms / 1000, 0.001)
        try:
            return await asyncio.wait_for(
                self._execute(parsed_payload, context),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "Tool timed out",
                tool=self.name,
                version=self.version,
                timeout_ms=self.limits.timeout_ms,
                request_id=context.request_id,
            )
            raise ToolExecutionError(
                f"{self.name} timed out after {self.limits.timeout_ms}ms",
                code="timeout",
                retryable=True,
            ) from exc

    @abstractmethod
    async def _execute(
        self,
        payload: BaseModel,
        context: ToolInvokeContext,
    ) -> Dict[str, Any]:
        """Execute tool logic and return plain dict."""
