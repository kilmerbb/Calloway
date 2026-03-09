import redis

from app.config import get_settings
from app.db.connection import get_db_connection


def get_db():
    """Dependency for database connection."""
    return get_db_connection()


def get_redis():
    """Dependency for Redis client."""
    settings = get_settings()
    return redis.from_url(settings.REDIS_URL, decode_responses=True)
