"""Task definitions for background job queue."""

import json
import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


async def enqueue_audit(
    audit_id: UUID,
    site_url: str,
    queries: list[str],
    config_override: dict[str, Any] | None = None,
    headless: bool = True,
    top_k: int = 10,
) -> str:
    """
    Enqueue an audit job to Redis.

    Args:
        audit_id: Unique identifier for the audit
        site_url: URL of the site to audit
        queries: List of search queries
        config_override: Optional configuration overrides
        headless: Run browser in headless mode
        top_k: Number of results to extract

    Returns:
        Job ID
    """
    from ..api.config import get_settings
    from ..api.deps import get_redis

    settings = get_settings()
    redis = await get_redis()

    job_data = {
        "audit_id": str(audit_id),
        "site_url": site_url,
        "queries": queries,
        "config_override": config_override,
        "headless": headless,
        "top_k": top_k,
    }

    # Push to queue
    job_id = f"audit:{audit_id}"
    await redis.hset(
        f"job:{job_id}",
        mapping={
            "data": json.dumps(job_data),
            "status": "pending",
            "created_at": str(__import__("datetime").datetime.utcnow().isoformat()),
        },
    )

    # Add to job queue
    await redis.lpush("audit:queue", job_id)

    # Set TTL
    await redis.expire(f"job:{job_id}", settings.redis_job_ttl)

    logger.info(f"Enqueued audit job: {job_id}")
    return job_id


async def cancel_audit_job(audit_id: UUID) -> bool:
    """
    Cancel a pending or running audit job.

    Args:
        audit_id: ID of the audit to cancel

    Returns:
        True if cancelled, False if not found
    """
    from ..api.deps import get_redis

    redis = await get_redis()
    job_id = f"audit:{audit_id}"

    # Check if job exists
    exists = await redis.exists(f"job:{job_id}")
    if not exists:
        return False

    # Mark as cancelled
    await redis.hset(f"job:{job_id}", "status", "cancelled")

    # Remove from queue if pending
    await redis.lrem("audit:queue", 0, job_id)

    # Publish cancellation signal for running jobs
    await redis.publish("audit:cancel", str(audit_id))

    logger.info(f"Cancelled audit job: {job_id}")
    return True


async def get_job_status(audit_id: UUID) -> dict[str, Any] | None:
    """
    Get the status of an audit job.

    Args:
        audit_id: ID of the audit

    Returns:
        Job status dict or None if not found
    """
    from ..api.deps import get_redis

    redis = await get_redis()
    job_id = f"audit:{audit_id}"

    job_data = await redis.hgetall(f"job:{job_id}")
    if not job_data:
        return None

    return {
        "job_id": job_id,
        "status": job_data.get("status", "unknown"),
        "created_at": job_data.get("created_at"),
        "started_at": job_data.get("started_at"),
        "completed_at": job_data.get("completed_at"),
        "progress": job_data.get("progress"),
        "error": job_data.get("error"),
    }


async def update_job_progress(
    audit_id: UUID,
    completed: int,
    total: int,
    current_query: str | None = None,
) -> None:
    """
    Update job progress in Redis.

    Args:
        audit_id: ID of the audit
        completed: Number of completed queries
        total: Total number of queries
        current_query: Currently processing query
    """
    from ..api.deps import get_redis

    redis = await get_redis()
    job_id = f"audit:{audit_id}"

    progress: dict[str, int | float | str] = {
        "completed": completed,
        "total": total,
        "percent": round((completed / total) * 100, 1) if total > 0 else 0.0,
    }
    if current_query:
        progress["current_query"] = current_query

    await redis.hset(f"job:{job_id}", "progress", json.dumps(progress))
