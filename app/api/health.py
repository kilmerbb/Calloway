"""Health check endpoints — basic and detailed."""
import logging
from fastapi import APIRouter

from app.db.connection import get_db_connection
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Basic health check — always fast."""
    return {"status": "ok"}


@router.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check — tests DB, Redis, external services."""
    checks = {
        "status": "ok",
        "database": "unknown",
        "redis": "unknown",
        "anthropic": "unknown",
    }

    # Database check
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"
        checks["status"] = "degraded"

    # Redis check
    try:
        settings = get_settings()
        if settings.REDIS_URL:
            import redis
            r = redis.from_url(settings.REDIS_URL, socket_timeout=2)
            r.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_configured"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:100]}"
        # Redis is optional, don't degrade

    # Anthropic check (just verify API key is set)
    try:
        settings = get_settings()
        if settings.ANTHROPIC_API_KEY:
            checks["anthropic"] = "configured"
        else:
            checks["anthropic"] = "not_configured"
            checks["status"] = "degraded"
    except Exception as e:
        checks["anthropic"] = f"error: {str(e)[:100]}"

    return checks


@router.get("/health/metrics")
async def health_metrics():
    """Quick operational metrics."""
    try:
        with get_db_connection() as conn:
            agents = conn.execute("SELECT COUNT(*) as cnt FROM agents").fetchone()
            contacts = conn.execute("SELECT COUNT(*) as cnt FROM contacts").fetchone()
            messages_today = conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE created_at >= CURRENT_DATE"
            ).fetchone()
            pending_triggers = conn.execute(
                "SELECT COUNT(*) as cnt FROM triggers WHERE status = 'pending'"
            ).fetchone()

        return {
            "agents": agents["cnt"] if agents else 0,
            "contacts": contacts["cnt"] if contacts else 0,
            "messages_today": messages_today["cnt"] if messages_today else 0,
            "pending_triggers": pending_triggers["cnt"] if pending_triggers else 0,
        }
    except Exception as e:
        return {"error": str(e)[:200]}
