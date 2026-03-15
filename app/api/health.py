"""Health check endpoints — basic and detailed."""
import hmac
import logging
from fastapi import APIRouter, HTTPException, Request

from app.db.connection import get_db_connection
from app.config import get_settings

import psycopg

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


# --- Auth helper for metrics ---

def _require_metrics_auth(request: Request) -> None:
    """Require authentication for metrics endpoint.

    Accepts either:
    - Console session cookie (for dashboard access)
    - Authorization: Bearer <CONSOLE_SESSION_SECRET> header (for monitoring tools)

    In development without secrets configured, allows access with a warning.
    """
    settings = get_settings()

    # Check for auth header first (monitoring tools)
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and settings.CONSOLE_SESSION_SECRET:
        if hmac.compare_digest(auth[7:], settings.CONSOLE_SESSION_SECRET):
            return

    # Check for console session cookie
    from app.api.console_auth import check_session
    session = check_session(request)
    if session:
        return

    # Development fallback — allow access when no real secrets are configured
    if settings.ENVIRONMENT == "development":
        logger.warning("Metrics accessed without auth in development mode")
        return

    raise HTTPException(status_code=401, detail="Authentication required")


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
    except psycopg.Error as e:
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
    except (redis.RedisError, ConnectionError) as e:
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
    except Exception as e:  # Broad catch: config check
        checks["anthropic"] = f"error: {str(e)[:100]}"

    return checks


@router.get("/health/metrics")
async def health_metrics(request: Request):
    """Quick operational metrics — requires authentication."""
    # SEC-H5: Metrics expose cross-tenant aggregate data; require auth
    _require_metrics_auth(request)
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
    except psycopg.Error as e:
        return {"error": str(e)[:200]}
