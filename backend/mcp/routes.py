"""FastAPI router exposing MCP discovery and invocation endpoints."""

from __future__ import annotations

import json
import uuid
from typing import Any, Awaitable, Callable, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .protocol import (
    ToolDiscoveryResponse,
    ToolInvokeContext,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolSpec,
)
from .registry import ToolNotFoundError, ToolRegistry
from ._logging import get_logger

logger = get_logger(__name__)

OnInvokeCallback = Union[
    Callable[[ToolInvokeResponse], Awaitable[None]],
    Callable[[ToolInvokeResponse], None],
]


def create_mcp_router(
    registry: ToolRegistry,
    auth_dependency: Optional[Callable[..., Any]] = None,
    on_invoke: Optional[OnInvokeCallback] = None,
) -> APIRouter:
    """Create MCP router with optional auth + instrumentation hooks."""

    if registry is None:
        raise ValueError("registry is required")

    auth_dep = auth_dependency or (lambda: None)

    router = APIRouter(prefix="/mcp", tags=["mcp"])

    @router.get("/tools", response_model=ToolDiscoveryResponse)
    async def list_tools(
        request: Request,
        current_user: Any = Depends(auth_dep),
    ) -> ToolDiscoveryResponse:  # pragma: no cover - simple wiring
        request_id = _resolve_request_id(request)
        logger.info(
            "Listing MCP tools",
            request_id=request_id,
            user_id=getattr(current_user, "id", None),
        )
        return ToolDiscoveryResponse(tools=registry.list_tools())

    @router.post("/invoke", response_model=ToolInvokeResponse)
    async def invoke_tool(
        payload: ToolInvokeRequest,
        request: Request,
        current_user: Any = Depends(auth_dep),
    ) -> ToolInvokeResponse:
        request_id = _resolve_request_id(request)
        trace_id = request.headers.get("x-trace-id")
        source = request.headers.get("x-mcp-source", "api")
        user_id = getattr(current_user, "id", None)

        try:
            tool = registry.resolve(payload.tool, payload.version)
        except ToolNotFoundError as exc:
            logger.warning(
                "Requested MCP tool not found",
                tool=payload.tool,
                version=payload.version,
                request_id=request_id,
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        payload_size_kb = _payload_size_kb(payload.payload)
        if payload_size_kb > tool.limits.max_payload_kb:
            logger.warning(
                "Payload too large for tool",
                tool=tool.name,
                size_kb=payload_size_kb,
                limit_kb=tool.limits.max_payload_kb,
                request_id=request_id,
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Payload exceeds {tool.limits.max_payload_kb}KB limit",
            )

        invoke_context = ToolInvokeContext(
            request_id=request_id,
            user_id=str(user_id) if user_id else None,
            session_id=payload.payload.get("chat_id") or payload.payload.get("session_id"),
            trace_id=trace_id,
            source=source,
            metadata={
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )

        response = await registry.invoke(
            tool_name=payload.tool,
            payload=payload.payload,
            version=payload.version,
            context=invoke_context,
        )

        if on_invoke:
            maybe_await = on_invoke(response)
            if hasattr(maybe_await, "__await__"):
                await maybe_await  # pragma: no cover - hook is optional

        return response

    return router


def _resolve_request_id(request: Request) -> str:
    return (
        getattr(request.state, "request_id", None)
        or request.headers.get("x-request-id")
        or str(uuid.uuid4())
    )


def _payload_size_kb(payload: Any) -> int:
    try:
        encoded = json.dumps(payload).encode("utf-8")
    except Exception:  # pragma: no cover - fallback path
        encoded = str(payload).encode("utf-8")
    return max(int(len(encoded) / 1024), 0)
