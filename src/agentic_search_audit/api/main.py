"""FastAPI application entry point."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from .config import get_settings
from .middleware import MetricsMiddleware, RateLimitMiddleware, RequestLoggingMiddleware
from .routes import audits, auth, billing, gdpr, health, users

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize Sentry error tracking."""
    settings = get_settings()
    sentry_dsn = os.getenv("SENTRY_DSN")

    if sentry_dsn and settings.is_production:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=settings.environment,
            release=settings.app_version,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
        )
        logger.info("Sentry initialized")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown."""
    settings = get_settings()
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")

    # Initialize Sentry
    init_sentry()

    # Startup: Initialize connections
    from .deps import init_db, init_redis

    await init_db()
    await init_redis()

    logger.info("Application started successfully")
    yield

    # Shutdown: Close connections
    from .deps import close_db, close_redis

    await close_db()
    await close_redis()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="REST API for running search quality audits using browser automation and LLM evaluation",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Add middleware (order matters - first added is outermost)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add custom middleware
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MetricsMiddleware)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: object, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")

        # Report to Sentry in production
        if settings.is_production:
            import sentry_sdk

            sentry_sdk.capture_exception(exc)

        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "An unexpected error occurred",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    # Prometheus metrics endpoint
    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Prometheus metrics endpoint."""
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(users.router, prefix="/users", tags=["Users"])
    app.include_router(audits.router, prefix="/audits", tags=["Audits"])
    app.include_router(billing.router, prefix="/billing", tags=["Billing"])
    app.include_router(gdpr.router, prefix="/gdpr", tags=["GDPR Compliance"])

    return app


# Create the app instance
app = create_app()
