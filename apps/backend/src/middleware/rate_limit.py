"""
Rate limiting middleware using slowapi.

Prevents abuse of API endpoints by limiting request rates per user/IP.
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

def get_user_id_or_ip(request: Request) -> str:
    """
    Get user ID from JWT token, fallback to IP address.

    This ensures:
    - Authenticated users are rate-limited per user
    - Anonymous users are rate-limited per IP
    """
    # Try to get user from request state (set by auth middleware)
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "id"):
        return f"user:{user.id}"

    # Fallback to IP address
    return f"ip:{get_remote_address(request)}"


# Initialize rate limiter
limiter = Limiter(
    key_func=get_user_id_or_ip,
    default_limits=["1000/hour"],  # Global default: 1000 requests per hour
    storage_uri="memory://",  # Use in-memory storage (upgrade to Redis for production)
    strategy="fixed-window",  # Fixed window strategy
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Placeholder middleware for rate limiting.
    
    Actual rate limiting is done via @limiter.limit() decorator on endpoints.
    This middleware is just for compatibility with the main.py middleware chain.
    """
    async def dispatch(self, request: Request, call_next):
        # Pass through - actual rate limiting handled by decorators
        response = await call_next(request)
        return response
