"""Shared Redis connection pool — avoids creating a new connection per call."""
import redis

from app.config import get_settings

_pool: redis.ConnectionPool | None = None


def get_redis_pool() -> redis.Redis:
    """Return a Redis client backed by a shared connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            socket_timeout=2,
            max_connections=20,
        )
    return redis.Redis(connection_pool=_pool)
