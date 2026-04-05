import logging
from typing import Callable

from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to the response."""
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HTTPS-only headers (only in production)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = "default-src 'self'"

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log incoming requests and responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response details."""
        # Generate correlation ID
        import uuid
        correlation_id = str(uuid.uuid4())

        # Log request
        logger.info(
            "Request started",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "url": str(request.url),
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            }
        )

        # Process request
        response = await call_next(request)

        # Log response
        logger.info(
            "Request completed",
            extra={
                "correlation_id": correlation_id,
                "status_code": response.status_code,
                "response_time_ms": None,  # Could add timing here
            }
        )

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response


def setup_security_middleware(app: FastAPI) -> None:
    """Setup all security-related middleware."""

    # Rate limiting
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[
            f"{settings.rate_limit_requests} per {settings.rate_limit_window} seconds"],
        storage_uri="memory://",  # Use Redis in production
        strategy="fixed-window",
    )

    app.state.limiter = limiter

    def _handle_rate_limit(request: Request, exc: Exception) -> Response:
        # type: ignore[arg-type]
        return _rate_limit_exceeded_handler(request, exc)

    app.add_exception_handler(RateLimitExceeded, _handle_rate_limit)
    app.add_middleware(SlowAPIMiddleware)

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Request logging (only in development or if debug is enabled)
    if settings.is_development or settings.debug:
        app.add_middleware(RequestLoggingMiddleware)
