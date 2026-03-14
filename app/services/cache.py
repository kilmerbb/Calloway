"""Generic Redis caching layer for hot data.

All operations are fail-safe: Redis errors are logged as warnings and never
propagate to callers.  When Redis is unavailable the application falls back
to database reads transparently.

Key namespace convention:  ``calloway:{type}:{id}``

Examples::

    calloway:conv:{agent_id}:{contact_id}
    calloway:listings:{agent_id}
    calloway:agent:id:{agent_id}
"""

import logging

from app.services.redis_pool import get_redis_pool

logger = logging.getLogger(__name__)


def cache_get(key: str) -> bytes | None:
    """Fetch a value from Redis.

    Returns ``None`` on cache miss **or** on any Redis error so that callers
    can treat both cases identically (fall through to DB).
    """
    try:
        r = get_redis_pool()
        return r.get(key)
    except Exception as e:
        logger.warning("cache_get failed for key=%s: %s", key, e)
        return None


def cache_set(key: str, value: str | bytes, ttl: int = 300) -> None:
    """Store a value in Redis with a TTL (seconds).

    Silently swallows errors so callers are never blocked by cache writes.
    """
    try:
        r = get_redis_pool()
        r.setex(key, ttl, value)
    except Exception as e:
        logger.warning("cache_set failed for key=%s: %s", key, e)


def cache_invalidate(key: str) -> None:
    """Delete a single cache key.

    No-op (with a warning log) if Redis is unreachable.
    """
    try:
        r = get_redis_pool()
        r.delete(key)
    except Exception as e:
        logger.warning("cache_invalidate failed for key=%s: %s", key, e)


def cache_invalidate_pattern(pattern: str) -> None:
    """Delete all keys matching *pattern* using incremental ``SCAN``.

    Uses ``SCAN`` instead of ``KEYS`` to avoid blocking Redis on large
    key-spaces.  Errors are logged and swallowed.
    """
    try:
        r = get_redis_pool()
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                r.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        logger.warning("cache_invalidate_pattern failed for pattern=%s: %s", pattern, e)
