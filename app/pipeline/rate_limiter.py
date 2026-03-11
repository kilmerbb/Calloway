"""Rate limiting — per-contact, per-agent cost cap, unknown number throttle."""
import logging
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import NormalizedEvent, Contact, AgentConfig

logger = logging.getLogger(__name__)

# Rate limit thresholds
HOURLY_MESSAGE_LIMIT = 30
DAILY_MESSAGE_LIMIT = 100
DAILY_COST_CAP_CENTS = 1500  # $15/day
UNKNOWN_DAILY_LIMIT = 10


def check_rate_limits(
    event: NormalizedEvent, contact: Contact | None, agent: AgentConfig
) -> dict | None:
    """
    Check all rate limit layers. Returns a dict with {action, response_text}
    if rate limited, or None to continue.
    """
    phone = event.sender_phone

    # Layer 1: Per-contact message rate limit
    if contact:
        limit_result = _check_contact_rate(phone)
        if limit_result:
            return limit_result

    # Layer 3: Unknown number throttle
    if contact is None:
        unknown_result = _check_unknown_rate(phone, agent)
        if unknown_result:
            return unknown_result

    return None


def check_cost_cap(agent_id: UUID) -> bool:
    """
    Layer 2: Per-agent daily cost cap.
    Returns True if cost cap is exceeded (should fall back to templates).
    """
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(llm_cost_cents), 0) as cost
                   FROM usage_metrics
                   WHERE agent_id = %s AND date = CURRENT_DATE""",
                [str(agent_id)],
            ).fetchone()

        cost = row["cost"] if row else 0
        if cost >= DAILY_COST_CAP_CENTS:
            logger.warning(
                f"Agent {agent_id} hit daily cost cap: {cost} cents >= {DAILY_COST_CAP_CENTS}"
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Cost cap check failed: {e}")
        return False


def _get_redis():
    """Get a Redis client from the shared pool."""
    from app.services.redis_pool import get_redis_pool
    return get_redis_pool()


def _check_contact_rate(phone: str) -> dict | None:
    """Check per-contact hourly and daily rate limits using Redis."""
    try:
        r = _get_redis()

        hour_key = f"rate:{phone}:hour"
        day_key = f"rate:{phone}:day"

        hour_count = r.incr(hour_key)
        if hour_count == 1:
            r.expire(hour_key, 3600)

        day_count = r.incr(day_key)
        if day_count == 1:
            r.expire(day_key, 86400)

        if hour_count > HOURLY_MESSAGE_LIMIT or day_count > DAILY_MESSAGE_LIMIT:
            logger.warning(f"Rate limit hit for {phone}: {hour_count}/hr, {day_count}/day")
            return {
                "action": "rate_limited",
                "response_text": (
                    "I'm getting a lot of messages! Let me catch up "
                    "and get back to you shortly."
                ),
                "notify_agent": True,
                "notification": {
                    "tier": "informational",
                    "title": "Rate limit triggered",
                    "body": f"Contact {phone} exceeded message rate limit.",
                },
            }
        return None

    except Exception as e:
        # Redis unavailable — fail open
        logger.debug(f"Rate limit check skipped (Redis unavailable): {e}")
        return None


def _check_unknown_rate(phone: str, agent: AgentConfig) -> dict | None:
    """Check unknown number daily rate limit."""
    try:
        r = _get_redis()

        key = f"unknown:{phone}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 86400)

        if count > UNKNOWN_DAILY_LIMIT:
            logger.warning(f"Unknown number rate limit hit for {phone}")
            return {
                "action": "unknown_throttled",
                "response_text": (
                    f"Thanks for your interest! Let me have {agent.name} "
                    f"follow up with you directly."
                ),
                "notify_agent": True,
                "notification": {
                    "tier": "action_needed",
                    "title": f"Unknown number throttled: {phone}",
                    "body": f"Unknown number {phone} sent {count}+ messages today.",
                },
            }
        return None

    except Exception as e:
        logger.debug(f"Unknown rate limit check skipped (Redis unavailable): {e}")
        return None
