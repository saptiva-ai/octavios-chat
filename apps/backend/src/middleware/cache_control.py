"""
Cache-Control middleware to prevent caching of API responses.

ISSUE-023: Adds no-cache headers to all API responses to prevent
browsers from caching sensitive chat data.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CacheControlMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add Cache-Control headers to API responses.

    Prevents browsers from caching API responses, which is critical for:
    - Chat messages (sensitive, real-time data)
    - User authentication state
    - Document review results
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Apply no-cache headers to all API routes
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response
