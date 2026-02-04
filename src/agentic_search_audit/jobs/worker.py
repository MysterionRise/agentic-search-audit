"""Background worker for processing audit jobs."""

import asyncio
import json
import logging
import signal
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

logger = logging.getLogger(__name__)

# Allowed schemes for webhook URLs
WEBHOOK_ALLOWED_SCHEMES = {"http", "https"}

# Blocked hostnames for webhook URLs (SSRF prevention)
WEBHOOK_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
}

# Blocked IP prefixes (internal networks)
WEBHOOK_BLOCKED_PREFIXES = (
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "169.254.",
)


def validate_webhook_url(url: str) -> bool:
    """Validate webhook URL to prevent SSRF attacks.

    Args:
        url: Webhook URL to validate

    Returns:
        True if URL is safe to call, False otherwise
    """
    try:
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme.lower() not in WEBHOOK_ALLOWED_SCHEMES:
            logger.warning(f"Webhook URL blocked: invalid scheme '{parsed.scheme}'")
            return False

        # Check host
        hostname = (parsed.hostname or "").lower()

        if hostname in WEBHOOK_BLOCKED_HOSTS:
            logger.warning("Webhook URL blocked: localhost/loopback address")
            return False

        if hostname.startswith(WEBHOOK_BLOCKED_PREFIXES):
            logger.warning("Webhook URL blocked: internal network address")
            return False

        # Check for IPv6 loopback
        if hostname.startswith("[") and "::1" in hostname:
            logger.warning("Webhook URL blocked: IPv6 loopback")
            return False

        return True

    except Exception as e:
        logger.warning(f"Webhook URL validation error: {e}")
        return False


class AuditWorker:
    """Worker that processes audit jobs from Redis queue."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_db",
        concurrency: int = 2,
    ):
        self.redis_url = redis_url
        self.database_url = database_url
        self.concurrency = concurrency
        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def start(self) -> None:
        """Start the worker."""
        import redis.asyncio as redis

        self._running = True
        self._redis = redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        # Set up cancellation listener
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe("audit:cancel")

        # Start listener task
        listener_task = asyncio.create_task(self._listen_cancellations())

        logger.info(f"Worker started with concurrency={self.concurrency}")

        try:
            while self._running:
                # Wait if at capacity
                if len(self._tasks) >= self.concurrency:
                    done, self._tasks = await asyncio.wait(
                        self._tasks,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        if task.exception():
                            logger.error(f"Task failed: {task.exception()}")

                # Get next job
                result = await self._redis.brpop("audit:queue", timeout=1)
                if result:
                    _, job_id = result
                    task = asyncio.create_task(self._process_job(job_id))
                    self._tasks.add(task)

        except asyncio.CancelledError:
            logger.info("Worker shutdown requested")
        finally:
            # Wait for remaining tasks
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)

            listener_task.cancel()
            await self._pubsub.unsubscribe()
            await self._redis.close()

            logger.info("Worker stopped")

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        self._running = False

    async def _listen_cancellations(self) -> None:
        """Listen for job cancellation signals."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    audit_id = message["data"]
                    if audit_id in self._cancel_events:
                        self._cancel_events[audit_id].set()
                        logger.info(f"Cancellation signal received for {audit_id}")
        except asyncio.CancelledError:
            pass

    async def _process_job(self, job_id: str) -> None:
        """Process a single audit job."""
        logger.info(f"Processing job: {job_id}")

        # Get job data
        job_data = await self._redis.hgetall(f"job:{job_id}")
        if not job_data:
            logger.error(f"Job not found: {job_id}")
            return

        # Check if cancelled
        if job_data.get("status") == "cancelled":
            logger.info(f"Job already cancelled: {job_id}")
            return

        # Parse job data
        try:
            data = json.loads(job_data["data"])
        except json.JSONDecodeError:
            logger.error(f"Invalid job data: {job_id}")
            return

        audit_id = data["audit_id"]

        # Set up cancellation event
        cancel_event = asyncio.Event()
        self._cancel_events[audit_id] = cancel_event

        try:
            # Mark as running
            await self._redis.hset(
                f"job:{job_id}",
                mapping={
                    "status": "running",
                    "started_at": datetime.utcnow().isoformat(),
                },
            )

            # Run the audit
            await self._run_audit(
                audit_id=UUID(audit_id),
                site_url=data["site_url"],
                queries=data["queries"],
                config_override=data.get("config_override"),
                headless=data.get("headless", True),
                top_k=data.get("top_k", 10),
                cancel_event=cancel_event,
            )

            # Mark as completed
            await self._redis.hset(
                f"job:{job_id}",
                mapping={
                    "status": "completed",
                    "completed_at": datetime.utcnow().isoformat(),
                },
            )

            logger.info(f"Job completed: {job_id}")

        except asyncio.CancelledError:
            await self._redis.hset(f"job:{job_id}", "status", "cancelled")
            logger.info(f"Job cancelled: {job_id}")

        except Exception as e:
            logger.exception(f"Job failed: {job_id}")
            await self._redis.hset(
                f"job:{job_id}",
                mapping={
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.utcnow().isoformat(),
                },
            )

        finally:
            del self._cancel_events[audit_id]

    async def _run_audit(
        self,
        audit_id: UUID,
        site_url: str,
        queries: list[str],
        config_override: dict[str, Any] | None,
        headless: bool,
        top_k: int,
        cancel_event: asyncio.Event,
    ) -> None:
        """Execute the actual audit."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from ..core.config import load_config
        from ..core.orchestrator import SearchAuditOrchestrator
        from ..core.types import Query
        from ..db.repositories import AuditRepository, UsageRepository

        # Create database session
        engine = create_async_engine(self.database_url)
        session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with session_factory() as session:
            audit_repo = AuditRepository(session)
            usage_repo = UsageRepository(session)

            # Get audit record
            audit = await audit_repo.get_by_id(audit_id)
            if not audit:
                raise ValueError(f"Audit not found: {audit_id}")

            # Update status
            await audit_repo.update_status(audit_id, "running")
            await session.commit()

            try:
                # Load configuration with overrides for headless and top_k
                overrides: dict[str, Any] = {
                    "site": {"url": site_url},
                    "run": {"headless": headless, "top_k": top_k},
                }
                if config_override:
                    # Merge additional overrides
                    for key, value in config_override.items():
                        if (
                            key in overrides
                            and isinstance(overrides[key], dict)
                            and isinstance(value, dict)
                        ):
                            overrides[key].update(value)
                        else:
                            overrides[key] = value

                config = load_config(overrides=overrides)

                # Create Query objects
                query_objects = [Query(id=f"q{i+1:03d}", text=q) for i, q in enumerate(queries)]

                # Create orchestrator
                from pathlib import Path
                from tempfile import mkdtemp

                run_dir = Path(mkdtemp(prefix=f"audit_{audit_id}_"))

                orchestrator = SearchAuditOrchestrator(config, query_objects, run_dir)

                # Run audit with progress updates
                scores = []

                # We need to modify the orchestrator to support progress callbacks
                # For now, run the full audit
                records = await orchestrator.run()

                # Save results to database
                for record in records:
                    await audit_repo.add_result(
                        audit_id=audit_id,
                        query_text=record.query.text,
                        query_data=record.query.model_dump(),
                        items=[item.model_dump() for item in record.items],
                        score=record.judge.model_dump(),
                        screenshot_path=record.page.screenshot_path,
                        html_path=record.page.html_path,
                    )
                    scores.append(record.judge.overall)

                # Calculate average score
                avg_score = sum(scores) / len(scores) if scores else None

                # Update audit status
                await audit_repo.update_progress(
                    audit_id,
                    completed_queries=len(records),
                    average_score=avg_score,
                )
                await audit_repo.update_status(
                    audit_id,
                    status="completed",
                    completed_at=datetime.utcnow(),
                )

                # Update usage
                from uuid import UUID as _UUID  # noqa: N811

                # Convert sqlalchemy UUID to standard UUID if needed
                user_uuid = (
                    audit.user_id if isinstance(audit.user_id, _UUID) else _UUID(str(audit.user_id))
                )
                await usage_repo.increment_usage(
                    user_id=user_uuid,
                    audit_count=1,
                    query_count=len(records),
                )

                await session.commit()

                # Send webhook if configured
                if audit.webhook_url:
                    await self._send_webhook(audit.webhook_url, audit_id, "completed", avg_score)

            except Exception as e:
                await audit_repo.update_status(
                    audit_id,
                    status="failed",
                    error_message=str(e),
                    completed_at=datetime.utcnow(),
                )
                await session.commit()

                # Send webhook on failure
                if audit.webhook_url:
                    await self._send_webhook(audit.webhook_url, audit_id, "failed", error=str(e))

                raise

        await engine.dispose()

    async def _send_webhook(
        self,
        url: str,
        audit_id: UUID,
        status: str,
        average_score: float | None = None,
        error: str | None = None,
    ) -> None:
        """Send webhook notification.

        Validates the webhook URL before sending to prevent SSRF attacks.
        """
        import aiohttp

        # Validate webhook URL to prevent SSRF
        if not validate_webhook_url(url):
            logger.error(
                f"Webhook URL validation failed for audit {audit_id}. "
                "URL points to blocked destination (localhost/internal network)."
            )
            return

        payload = {
            "audit_id": str(audit_id),
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if average_score is not None:
            payload["average_score"] = str(average_score)
        if error:
            payload["error"] = error

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                    # Disable redirects to prevent SSRF via redirect
                    allow_redirects=False,
                ) as response:
                    if response.status >= 400:
                        logger.warning(f"Webhook failed: {response.status}")
                    elif response.status in (301, 302, 303, 307, 308):
                        logger.warning(f"Webhook redirect blocked for security: {response.status}")
        except Exception as e:
            logger.warning(f"Webhook error: {e}")


def run_worker() -> None:
    """Entry point for running the worker."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Audit worker")
    parser.add_argument(
        "--redis-url",
        default=os.getenv("AUDIT_REDIS_URL", "redis://localhost:6379/0"),
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "AUDIT_DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/audit_db",
        ),
    )
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    worker = AuditWorker(
        redis_url=args.redis_url,
        database_url=args.database_url,
        concurrency=args.concurrency,
    )

    loop = asyncio.new_event_loop()

    # Handle shutdown signals
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.stop()))

    try:
        loop.run_until_complete(worker.start())
    finally:
        loop.close()


if __name__ == "__main__":
    run_worker()
