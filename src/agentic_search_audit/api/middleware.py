"""API middleware for rate limiting, logging, and metrics."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis sliding window.

    Limits requests per user (authenticated) or IP (anonymous).
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()

        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return cast(Response, await call_next(request))

        # Get identifier (user_id from token or IP)
        identifier = await self._get_identifier(request)

        # Check rate limit
        is_allowed, remaining, reset_at = await self._check_rate_limit(
            identifier,
            settings.rate_limit_requests,
            settings.rate_limit_window,
        )

        if not is_allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": reset_at,
                },
                headers={
                    "X-RateLimit-Limit": str(settings.rate_limit_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                    "Retry-After": str(reset_at),
                },
            )

        # Process request
        response = cast(Response, await call_next(request))

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)

        return response

    async def _get_identifier(self, request: Request) -> str:
        """Get identifier for rate limiting."""
        # Try to get user_id from authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from .routes.auth import verify_token

                settings = get_settings()
                token = auth_header.split(" ")[1]
                payload = verify_token(token, settings)
                return f"user:{payload['sub']}"
            except Exception:
                pass

        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        return f"ip:{client_ip}"

    async def _check_rate_limit(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """
        Check rate limit using Redis sliding window.

        Returns: (is_allowed, remaining_requests, reset_timestamp)
        """
        try:
            from .deps import get_redis

            redis = await get_redis()
            key = f"ratelimit:{identifier}"
            now = int(time.time())
            window_start = now - window_seconds

            # Use Redis pipeline for atomic operations
            pipe = redis.pipeline()

            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current entries
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {str(now): now})

            # Set expiry
            pipe.expire(key, window_seconds)

            results = await pipe.execute()
            current_count = results[1]

            remaining = max(0, max_requests - current_count - 1)
            reset_at = now + window_seconds

            is_allowed = current_count < max_requests

            return is_allowed, remaining, reset_at

        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")
            # Allow request on Redis failure
            return True, max_requests, int(time.time()) + window_seconds


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging requests and responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.perf_counter()

        # Log request
        logger.info(
            f"Request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params),
                "client_ip": request.client.host if request.client else None,
            },
        )

        # Process request
        response = cast(Response, await call_next(request))

        # Calculate duration
        duration = time.perf_counter() - start_time

        # Log response
        logger.info(
            f"Response: {response.status_code} ({duration:.3f}s)",
            extra={
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )

        # Add timing header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for Prometheus metrics collection."""

    def __init__(self, app: Any, registry: Any = None) -> None:
        super().__init__(app)
        from prometheus_client import REGISTRY, Counter, Histogram

        self.registry = registry or REGISTRY

        # Request counter
        self.request_counter = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
            registry=self.registry,
        )

        # Request duration histogram
        self.request_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "path"],
            registry=self.registry,
        )

        # Active requests gauge
        from prometheus_client import Gauge

        self.active_requests = Gauge(
            "http_requests_active",
            "Active HTTP requests",
            registry=self.registry,
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Normalize path for metrics (avoid cardinality explosion)
        path = self._normalize_path(request.url.path)

        self.active_requests.inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start_time
            self.active_requests.dec()

            # Record metrics
            self.request_counter.labels(
                method=request.method,
                path=path,
                status=status_code,
            ).inc()

            self.request_duration.labels(
                method=request.method,
                path=path,
            ).observe(duration)

        return cast(Response, response)

    def _normalize_path(self, path: str) -> str:
        """Normalize path to avoid high cardinality."""
        import re

        # Replace UUIDs with placeholder
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
        )

        # Replace numeric IDs
        path = re.sub(r"/\d+(/|$)", "/{id}\\1", path)

        return path
