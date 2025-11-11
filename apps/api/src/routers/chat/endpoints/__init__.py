"""Chat endpoints - HTTP endpoint modules."""

from .message_endpoints import router as message_router

__all__ = ["message_router"]
