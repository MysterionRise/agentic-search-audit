"""Health check endpoints."""

import time
from datetime import datetime

from fastapi import APIRouter, Depends

from ..config import APISettings, get_settings
from ..schemas import ComponentHealth, HealthStatus

router = APIRouter()


async def check_database() -> ComponentHealth:
    """Check database connectivity."""
    start = time.perf_counter()
    try:
        from ..deps import get_db_session

        async for session in get_db_session():
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
            latency = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                status="healthy",
                latency_ms=latency,
                message=None,
            )
        # Fallback if generator doesn't yield (should never happen)
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            status="unhealthy",
            latency_ms=latency,
            message="Database session not available",
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            status="unhealthy",
            latency_ms=latency,
            message=str(e),
        )


async def check_redis() -> ComponentHealth:
    """Check Redis connectivity."""
    start = time.perf_counter()
    try:
        from ..deps import get_redis

        redis = await get_redis()
        await redis.ping()
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            status="healthy",
            latency_ms=latency,
            message=None,
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            status="unhealthy",
            latency_ms=latency,
            message=str(e),
        )


@router.get("/health", response_model=HealthStatus)
async def health_check(
    settings: APISettings = Depends(get_settings),
) -> HealthStatus:
    """
    Health check endpoint for load balancers and monitoring.

    Returns the status of all system components.
    """
    db_health = await check_database()
    redis_health = await check_redis()

    checks = {
        "database": db_health,
        "redis": redis_health,
    }

    # Determine overall status
    statuses = [c.status for c in checks.values()]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s == "unhealthy" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    return HealthStatus(
        status=overall,
        version=settings.app_version,
        timestamp=datetime.utcnow(),
        checks=checks,
    )


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """
    Kubernetes liveness probe.

    Returns 200 if the application is running.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(
    settings: APISettings = Depends(get_settings),
) -> dict[str, str]:
    """
    Kubernetes readiness probe.

    Returns 200 if the application is ready to serve traffic.
    """
    # Check critical dependencies
    db_health = await check_database()
    redis_health = await check_redis()

    if db_health.status == "unhealthy":
        return {"status": "not_ready", "reason": "database_unavailable"}

    if redis_health.status == "unhealthy":
        return {"status": "not_ready", "reason": "redis_unavailable"}

    return {"status": "ready"}
