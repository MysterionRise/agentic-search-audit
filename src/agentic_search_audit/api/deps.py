"""API dependencies for database and Redis connections."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)

# Global connection pools
_db_engine = None
_db_session_factory = None
_redis_client = None


async def init_db() -> None:
    """Initialize database connection pool."""
    global _db_engine, _db_session_factory

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    settings = get_settings()

    _db_engine = create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.debug,
    )

    _db_session_factory = async_sessionmaker(
        bind=_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create tables if they don't exist
    from .db.models import Base  # type: ignore[import-untyped]

    async with _db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database connection pool initialized")


async def close_db() -> None:
    """Close database connection pool."""
    global _db_engine

    if _db_engine:
        await _db_engine.dispose()
        _db_engine = None
        logger.info("Database connection pool closed")


async def get_db_session() -> AsyncGenerator:
    """Get a database session."""
    if not _db_session_factory:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with _db_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_redis() -> None:
    """Initialize Redis connection."""
    global _redis_client

    import redis.asyncio as redis

    settings = get_settings()

    _redis_client = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )

    # Test connection
    await _redis_client.ping()  # type: ignore[misc]
    logger.info("Redis connection initialized")


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client

    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


async def get_redis() -> Any:
    """Get Redis client."""
    if not _redis_client:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")

    return _redis_client
