"""
Chat Router Package - Modular chat API endpoints.

This package organizes chat-related endpoints into focused modules
following Single Responsibility Principle.

Structure:
    endpoints/
        message_endpoints.py  - POST /chat, escalate
        (future: session_endpoints.py, history_endpoints.py)
    handlers/
        streaming_handler.py  - SSE streaming logic

Architecture Benefits:
    ✅ Single Responsibility: Each module has one clear purpose
    ✅ Open/Closed: Easy to add new endpoint modules
    ✅ Testability: Handlers and endpoints testable independently
    ✅ Maintainability: Changes localized to specific modules
"""

from fastapi import APIRouter

# Import endpoint routers
from .endpoints.message_endpoints import router as message_router

# Create main router and include sub-routers
router = APIRouter()
router.include_router(message_router)

# Export for use in main app
__all__ = ["router"]
