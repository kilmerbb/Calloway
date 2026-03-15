"""Per-agent configuration loading with Redis caching.

Uses the shared bounded connection pool from redis_pool.py rather than
maintaining a separate unbounded client, preventing Redis connection
exhaustion under load.
"""
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import AgentConfig
from app.services.redis_pool import get_redis_pool

CACHE_TTL = 300  # 5 minutes


def _agent_row_to_config(row: dict) -> AgentConfig:
    """Convert a database row dict to an AgentConfig model."""
    return AgentConfig(**row)


def get_agent_by_twilio_number(phone: str) -> AgentConfig | None:
    """Look up an agent by their Twilio phone number. Cached in Redis."""
    r = get_redis_pool()
    cache_key = f"agent:twilio:{phone}"

    cached = r.get(cache_key)
    if cached:
        return AgentConfig.model_validate_json(cached)

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM agents WHERE twilio_number = %s", [phone]
        ).fetchone()

    if row is None:
        return None

    agent = _agent_row_to_config(row)
    r.setex(cache_key, CACHE_TTL, agent.model_dump_json())
    return agent


def get_agent_by_id(agent_id: UUID) -> AgentConfig | None:
    """Look up an agent by ID. Cached in Redis."""
    r = get_redis_pool()
    cache_key = f"agent:id:{agent_id}"

    cached = r.get(cache_key)
    if cached:
        return AgentConfig.model_validate_json(cached)

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM agents WHERE id = %s", [str(agent_id)]
        ).fetchone()

    if row is None:
        return None

    agent = _agent_row_to_config(row)
    r.setex(cache_key, CACHE_TTL, agent.model_dump_json())
    return agent


def invalidate_agent_cache(agent_id: UUID, twilio_number: str | None = None) -> None:
    """Invalidate cached agent config after updates."""
    r = get_redis_pool()
    r.delete(f"agent:id:{agent_id}")
    if twilio_number:
        r.delete(f"agent:twilio:{twilio_number}")
