"""Async Redis connection pool for WebSocket pub/sub and other async Redis usage."""

import logging

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

_async_redis: aioredis.Redis | None = None


async def init_async_redis() -> None:
    """Create the shared async Redis connection pool."""
    global _async_redis
    settings = get_settings()
    _async_redis = aioredis.from_url(
        settings.REDIS_URL,
        socket_timeout=2,
        max_connections=10,
        decode_responses=True,
    )
    logger.info("Async Redis pool initialized")


async def close_async_redis() -> None:
    """Shut down the async Redis pool gracefully."""
    global _async_redis
    if _async_redis:
        await _async_redis.close()
        _async_redis = None
        logger.info("Async Redis pool closed")


def get_async_redis() -> aioredis.Redis:
    """Return the shared async Redis client. Raises if not yet initialized."""
    if _async_redis is None:
        raise RuntimeError("Async Redis not initialized — call init_async_redis() first")
    return _async_redis
