"""Console query layer — cross-tenant queries for operator visibility.

All queries bypass RLS by using the service key connection directly
(no set_agent_context). This is operator-level access.

Authorization guard: Every public function requires an active console auth
context (set via ``set_console_context``). Console routes set this context
after authenticating the operator session. Background workers that need
cross-tenant access should call ``set_console_context({"source": "worker",
"worker": "<worker-name>"})`` at the start of their run loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextvars import ContextVar
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import UUID

import psycopg
import redis

from app.db.connection import get_db_connection, get_async_db_connection
from app.services.cache import cache_get, cache_set, cache_invalidate
from app.models.responses import (
    ActivityEntry,
    AgentDetail,
    AgentSummary,
    ConversationDetail,
    ConversationRow,
    CostSummary,
    ErrorSummary,
    HealthOverview,
    SystemPulse,
    TriggerRow,
)

logger = logging.getLogger(__name__)


# ============================================================
# Authorization guard — context-var approach
# ============================================================

class AuthorizationError(Exception):
    """Raised when a console query function is called without auth context."""


_console_auth_context: ContextVar[dict | None] = ContextVar(
    "console_auth", default=None,
)


def set_console_context(user_info: dict) -> None:
    """Set the console auth context for the current task/request.

    Must be called by console route middleware after verifying the
    operator session, or by background workers before accessing
    cross-tenant queries.
    """
    _console_auth_context.set(user_info)


def clear_console_context() -> None:
    """Reset the console auth context (used after request completes)."""
    _console_auth_context.set(None)


def require_console_context() -> dict:
    """Return the current console auth context or raise.

    Returns the context dict so callers can inspect who is making the
    request if needed for audit logging.
    """
    ctx = _console_auth_context.get()
    if ctx is None:
        raise AuthorizationError(
            "Console query called without authentication context. "
            "Ensure the request is routed through an authenticated console endpoint."
        )
    return ctx


def console_authorized(func):
    """Decorator that gates an async function behind console auth context."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        require_console_context()
        return await func(*args, **kwargs)
    return wrapper


def _sync_console_authorized(func):
    """Decorator that gates a sync function behind console auth context."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        require_console_context()
        return func(*args, **kwargs)
    return wrapper


# ============================================================
# System Pulse (Dashboard)
# ============================================================

@console_authorized
async def get_system_pulse() -> SystemPulse:
    """Top-level system stats for the dashboard."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) as cnt FROM agents"
            )
            agents = await cur.fetchone()

            cur = await conn.execute(
                """SELECT COALESCE(SUM(messages_sent + messages_received), 0) as cnt
                   FROM usage_metrics WHERE date = CURRENT_DATE"""
            )
            msgs_today = await cur.fetchone()

            cur = await conn.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE created_at > now() - interval '24 hours'"""
            )
            msgs_24h = await cur.fetchone()

            cur = await conn.execute(
                """SELECT COUNT(*) as cnt FROM tool_executions
                   WHERE error_message IS NOT NULL
                   AND created_at > now() - interval '24 hours'"""
            )
            errors_24h = await cur.fetchone()

            cur = await conn.execute(
                """SELECT COALESCE(SUM(llm_cost_cents + sms_cost_cents + voice_cost_cents), 0) as cost
                   FROM usage_metrics WHERE date = CURRENT_DATE"""
            )
            cost_today = await cur.fetchone()

        return {
            "total_agents": agents["cnt"] if agents else 0,
            "messages_today": msgs_today["cnt"] if msgs_today else 0,
            "messages_24h": msgs_24h["cnt"] if msgs_24h else 0,
            "errors_24h": errors_24h["cnt"] if errors_24h else 0,
            "cost_today_dollars": round((cost_today["cost"] if cost_today else 0) / 100, 2),
        }
    except psycopg.Error as e:
        logger.error(f"System pulse query failed: {e}")
        return {
            "total_agents": 0, "messages_today": 0, "messages_24h": 0,
            "errors_24h": 0, "cost_today_dollars": 0,
        }


@console_authorized
async def get_recent_activity(limit: int = 20) -> list[ActivityEntry]:
    """Recent events across the system for the activity feed."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT m.created_at, m.sender_type, m.body,
                          a.name as agent_name, c.name as contact_name,
                          m.ai_generated, m.model_used
                   FROM messages m
                   JOIN conversations cv ON m.conversation_id = cv.id
                   JOIN agents a ON cv.agent_id = a.id
                   LEFT JOIN contacts c ON cv.contact_id = c.id
                   ORDER BY m.created_at DESC LIMIT %s""",
                [limit],
            )
            rows = await cur.fetchall()
        return rows or []
    except psycopg.Error as e:
        logger.error(f"Recent activity query failed: {e}")
        return []


@console_authorized
async def get_agents_needing_attention() -> dict:
    """Agents with errors or no recent activity."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT a.id, a.name, COUNT(te.id) as error_count
                   FROM agents a
                   JOIN tool_executions te ON te.agent_id = a.id
                   WHERE te.error_message IS NOT NULL
                   AND te.created_at > now() - interval '24 hours'
                   GROUP BY a.id, a.name
                   ORDER BY error_count DESC"""
            )
            error_agents = await cur.fetchall()

            cur = await conn.execute(
                """SELECT a.id, a.name, MAX(um.date) as last_active
                   FROM agents a
                   LEFT JOIN usage_metrics um ON um.agent_id = a.id
                   GROUP BY a.id, a.name
                   HAVING MAX(um.date) < CURRENT_DATE - 2
                   OR MAX(um.date) IS NULL"""
            )
            inactive_agents = await cur.fetchall()

        return {
            "error_agents": error_agents or [],
            "inactive_agents": inactive_agents or [],
        }
    except psycopg.Error as e:
        logger.error(f"Attention query failed: {e}")
        return {"error_agents": [], "inactive_agents": []}


# ============================================================
# Agents / Tenants
# ============================================================

@console_authorized
async def get_all_agents() -> list[AgentSummary]:
    """All agents with summary stats."""
    cache_key = "console:agents:all"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.debug("cache hit for %s", cache_key)
        return json.loads(cached)

    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT a.*,
                    COALESCE(c.cnt, 0) AS contact_count,
                    COALESCE(u.msgs, 0) AS messages_today,
                    u.last_dt AS last_active,
                    COALESCE(e.cnt, 0) AS errors_24h
                   FROM agents a
                   LEFT JOIN (
                       SELECT agent_id, COUNT(*) AS cnt
                       FROM contacts GROUP BY agent_id
                   ) c ON c.agent_id = a.id
                   LEFT JOIN (
                       SELECT agent_id,
                              COALESCE(SUM(CASE WHEN date = CURRENT_DATE THEN messages_sent ELSE 0 END), 0) AS msgs,
                              MAX(date) AS last_dt
                       FROM usage_metrics GROUP BY agent_id
                   ) u ON u.agent_id = a.id
                   LEFT JOIN (
                       SELECT agent_id, COUNT(*) AS cnt
                       FROM tool_executions
                       WHERE error_message IS NOT NULL
                         AND created_at > now() - interval '24 hours'
                       GROUP BY agent_id
                   ) e ON e.agent_id = a.id
                   ORDER BY a.name"""
            )
            rows = await cur.fetchall()
        result = rows or []
        cache_set(cache_key, json.dumps(result, default=str), ttl=60)
        return result
    except psycopg.Error as e:
        logger.error(f"Get all agents failed: {e}")
        return []


@console_authorized
async def get_agent_options() -> list[dict]:
    """Lightweight agent list (id + name only) for dropdown filters."""
    cache_key = "console:agents:options"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.debug("cache hit for %s", cache_key)
        return json.loads(cached)

    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                "SELECT id, name FROM agents ORDER BY name"
            )
            rows = await cur.fetchall()
        result = [dict(r) for r in rows] if rows else []
        cache_set(cache_key, json.dumps(result, default=str), ttl=300)
        return result
    except psycopg.Error as e:
        logger.error(f"Get agent options failed: {e}")
        return []


@console_authorized
async def get_agent_basic(agent_id: str) -> dict | None:
    """Lightweight agent record — just the agent row for edit forms."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM agents WHERE id = %s", [agent_id]
            )
            agent = await cur.fetchone()
            return dict(agent) if agent else None
    except psycopg.Error as e:
        logger.error(f"Agent basic query failed: {e}")
        return None


@console_authorized
async def get_agent_detail(agent_id: str) -> AgentDetail | None:
    """Full agent record with all related data.

    Step 1: fetch agent (gate check).
    Step 2: run remaining queries in parallel via asyncio.gather(),
    grouped into 3 pairs to limit connection usage.
    """
    # Step 1: gate check — fetch agent record
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM agents WHERE id = %s", [agent_id]
            )
            agent = await cur.fetchone()
            if not agent:
                return None
    except psycopg.Error as e:
        logger.error(f"Agent detail gate-check failed: {e}")
        return None

    # Step 2: parallel queries grouped into 3 pairs
    async def _fetch_contacts_and_listings():
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT id, name, phone, email, role, lifecycle_stage,
                          consent_status, last_contact_at, silent_mode,
                          interaction_count
                   FROM contacts WHERE agent_id = %s
                   ORDER BY last_contact_at DESC NULLS LAST
                   LIMIT 25""",
                [agent_id],
            )
            contacts = await cur.fetchall()

            cur = await conn.execute(
                """SELECT id, address, price, status, beds, baths, sqft,
                          list_date
                   FROM listings WHERE agent_id = %s
                   ORDER BY created_at DESC
                   LIMIT 25""",
                [agent_id],
            )
            listings = await cur.fetchall()
        return contacts or [], listings or []

    async def _fetch_messages_and_triggers():
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT m.body, m.sender_type, m.created_at, m.model_used,
                          c.name as contact_name
                   FROM messages m
                   JOIN conversations cv ON m.conversation_id = cv.id
                   LEFT JOIN contacts c ON cv.contact_id = c.id
                   WHERE m.agent_id = %s
                   ORDER BY m.created_at DESC LIMIT 50""",
                [agent_id],
            )
            recent_msgs = await cur.fetchall()

            cur = await conn.execute(
                """SELECT * FROM triggers
                   WHERE agent_id = %s AND status = 'pending'
                   ORDER BY scheduled_at LIMIT 10""",
                [agent_id],
            )
            triggers = await cur.fetchall()
        return recent_msgs or [], triggers or []

    async def _fetch_costs_and_errors():
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT COALESCE(SUM(llm_cost_cents), 0) as cost,
                          COALESCE(SUM(messages_sent), 0) as msgs
                   FROM usage_metrics
                   WHERE agent_id = %s
                   AND date >= date_trunc('month', CURRENT_DATE)""",
                [agent_id],
            )
            cost_month = await cur.fetchone()

            cur = await conn.execute(
                """SELECT COUNT(*) as cnt FROM tool_executions
                   WHERE agent_id = %s AND error_message IS NOT NULL
                   AND created_at > now() - interval '24 hours'""",
                [agent_id],
            )
            errors = await cur.fetchone()
        return cost_month, errors

    results = await asyncio.gather(
        _fetch_contacts_and_listings(),
        _fetch_messages_and_triggers(),
        _fetch_costs_and_errors(),
        return_exceptions=True,
    )

    # Unpack with safe defaults if any group raised
    if isinstance(results[0], Exception):
        logger.error(f"Agent detail contacts/listings query failed: {results[0]}")
        contacts, listings = [], []
    else:
        contacts, listings = results[0]

    if isinstance(results[1], Exception):
        logger.error(f"Agent detail messages/triggers query failed: {results[1]}")
        recent_msgs, triggers = [], []
    else:
        recent_msgs, triggers = results[1]

    if isinstance(results[2], Exception):
        logger.error(f"Agent detail costs/errors query failed: {results[2]}")
        cost_month, errors = None, None
    else:
        cost_month, errors = results[2]

    return {
        "agent": agent,
        "contacts": contacts,
        "listings": listings,
        "recent_messages": recent_msgs,
        "pending_triggers": triggers,
        "cost_this_month_dollars": round((cost_month["cost"] if cost_month else 0) / 100, 2),
        "messages_this_month": cost_month["msgs"] if cost_month else 0,
        "errors_24h": errors["cnt"] if errors else 0,
    }


# ============================================================
# Conversations
# ============================================================

@console_authorized
async def get_recent_conversations(
    agent_id: str | None = None,
    channel: str | None = None,
    search: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> list[ConversationRow]:
    """Recent conversations with filtering and pagination."""
    limit = min(limit, 100)  # Safety cap
    try:
        conditions = []
        params = []

        if agent_id:
            conditions.append("cv.agent_id = %s")
            params.append(agent_id)
        if channel:
            conditions.append("cv.channel = %s")
            params.append(channel)
        if search:
            conditions.append("(c.name ILIKE %s OR c.phone ILIKE %s)")
            search_escaped = search.replace("%", "\\%").replace("_", "\\_")
            params.extend([f"%{search_escaped}%", f"%{search_escaped}%"])

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                f"""SELECT cv.id, cv.channel, cv.last_message_at,
                          a.name as agent_name, c.name as contact_name, c.phone,
                          (SELECT COUNT(*) FROM messages WHERE conversation_id = cv.id) as msg_count,
                          (SELECT body FROM messages WHERE conversation_id = cv.id
                           ORDER BY created_at DESC LIMIT 1) as last_message
                    FROM conversations cv
                    JOIN agents a ON cv.agent_id = a.id
                    LEFT JOIN contacts c ON cv.contact_id = c.id
                    {where}
                    ORDER BY cv.last_message_at DESC NULLS LAST
                    LIMIT %s OFFSET %s""",
                params + [limit, offset],
            )
            rows = await cur.fetchall()
        return rows or []
    except psycopg.Error as e:
        logger.error(f"Conversations query failed: {e}")
        return []


@console_authorized
async def get_conversation_detail(conversation_id: str) -> ConversationDetail | None:
    """Full conversation thread with messages and tool executions."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT cv.*, a.name as agent_name, c.name as contact_name,
                          c.phone as contact_phone, c.role, c.lifecycle_stage,
                          c.id as contact_id
                   FROM conversations cv
                   JOIN agents a ON cv.agent_id = a.id
                   LEFT JOIN contacts c ON cv.contact_id = c.id
                   WHERE cv.id = %s""",
                [conversation_id],
            )
            conv = await cur.fetchone()
            if not conv:
                return None

            cur = await conn.execute(
                """SELECT * FROM messages
                   WHERE conversation_id = %s
                   ORDER BY created_at""",
                [conversation_id],
            )
            messages = await cur.fetchall()

            cur = await conn.execute(
                """SELECT * FROM tool_executions
                   WHERE conversation_id = %s
                   ORDER BY created_at""",
                [conversation_id],
            )
            tool_execs = await cur.fetchall()

            triggers = []
            if conv.get("contact_id"):
                cur = await conn.execute(
                    """SELECT * FROM triggers
                       WHERE agent_id = %s AND entity_id = %s AND status = 'pending'
                       ORDER BY scheduled_at""",
                    [str(conv["agent_id"]), str(conv["contact_id"])],
                )
                triggers = await cur.fetchall() or []

        return {
            "conversation": conv,
            "messages": messages or [],
            "tool_executions": tool_execs or [],
            "triggers": triggers,
        }
    except psycopg.Error as e:
        logger.error(f"Conversation detail query failed: {e}")
        return None


# ============================================================
# Triggers
# ============================================================

@console_authorized
async def get_trigger_queue(
    status: str | None = None,
    agent_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TriggerRow]:
    """Triggers with optional filtering and pagination."""
    # Safety cap to prevent unbounded queries
    limit = min(limit, 500)

    try:
        conditions = []
        params = []

        if status:
            conditions.append("t.status = %s")
            params.append(status)
        if agent_id:
            conditions.append("t.agent_id = %s")
            params.append(agent_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                f"""SELECT t.*, a.name as agent_name
                    FROM triggers t
                    JOIN agents a ON t.agent_id = a.id
                    {where}
                    ORDER BY t.scheduled_at
                    LIMIT %s OFFSET %s""",
                params + [limit, offset],
            )
            rows = await cur.fetchall()
        return rows or []
    except psycopg.Error as e:
        logger.error(f"Trigger queue query failed: {e}")
        return []


@console_authorized
async def retry_trigger(trigger_id: str) -> None:
    """Reset a failed trigger to pending with scheduled_at = now."""
    try:
        async with get_async_db_connection() as conn:
            await conn.execute(
                """UPDATE triggers SET status = 'pending', scheduled_at = now()
                   WHERE id = %s""",
                [trigger_id],
            )
            await conn.commit()
    except psycopg.Error as e:
        logger.error(f"Retry trigger failed: {e}")


@console_authorized
async def cancel_trigger(trigger_id: str) -> None:
    """Cancel a pending trigger."""
    try:
        async with get_async_db_connection() as conn:
            await conn.execute(
                "UPDATE triggers SET status = 'cancelled' WHERE id = %s",
                [trigger_id],
            )
            await conn.commit()
    except psycopg.Error as e:
        logger.error(f"Cancel trigger failed: {e}")


@console_authorized
async def fire_trigger_now(trigger_id: str) -> None:
    """Set a trigger to fire immediately."""
    try:
        async with get_async_db_connection() as conn:
            await conn.execute(
                "UPDATE triggers SET scheduled_at = now() WHERE id = %s AND status = 'pending'",
                [trigger_id],
            )
            await conn.commit()
    except psycopg.Error as e:
        logger.error(f"Fire trigger now failed: {e}")


# ============================================================
# Errors
# ============================================================

@console_authorized
async def get_recent_errors(
    limit: int = 100,
    agent_id: str | None = None,
) -> ErrorSummary:
    """Tool execution errors + error_log entries."""
    try:
        conditions = ["te.error_message IS NOT NULL"]
        params = []

        if agent_id:
            conditions.append("te.agent_id = %s")
            params.append(agent_id)

        where = "WHERE " + " AND ".join(conditions)

        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                f"""SELECT te.*, a.name as agent_name
                    FROM tool_executions te
                    JOIN agents a ON te.agent_id = a.id
                    {where}
                    ORDER BY te.created_at DESC LIMIT %s""",
                params + [limit],
            )
            rows = await cur.fetchall()

            # Also check error_log if it exists
            error_log_rows = []
            try:
                cur = await conn.execute(
                    """SELECT el.*, a.name as agent_name
                       FROM error_log el
                       LEFT JOIN agents a ON el.agent_id = a.id
                       ORDER BY el.created_at DESC LIMIT %s""",
                    [limit],
                )
                error_log_rows = await cur.fetchall() or []
            except psycopg.Error:
                pass  # Table may not exist yet

        return {
            "tool_errors": rows or [],
            "app_errors": error_log_rows,
        }
    except psycopg.Error as e:
        logger.error(f"Recent errors query failed: {e}")
        return {"tool_errors": [], "app_errors": []}


@_sync_console_authorized
def log_error(
    module: str, severity: str, message: str,
    agent_id: str | None = None,
    stack_trace: str | None = None,
    context: dict | None = None,
) -> None:
    """Log an application error to the error_log table."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO error_log (agent_id, module, severity, message,
                   stack_trace, context_json)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [agent_id, module, severity, message, stack_trace,
                 json.dumps(context) if context else None],
            )
            conn.commit()
    except psycopg.Error as e:
        logger.error(f"Failed to log error: {e}")


# ============================================================
# Costs
# ============================================================

@console_authorized
async def get_cost_summary(days: int = 30) -> CostSummary:
    """System-wide cost summary (cached 300s)."""
    cache_key = f"console:costs:summary:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.debug("cache hit for %s", cache_key)
        return json.loads(cached)

    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT
                    COALESCE(SUM(llm_cost_cents), 0) as total_llm_cost,
                    COALESCE(SUM(sms_cost_cents), 0) as total_sms_cost,
                    COALESCE(SUM(voice_cost_cents), 0) as total_voice_cost,
                    COALESCE(SUM(sms_segments_sent), 0) as total_sms_segments,
                    COALESCE(SUM(messages_sent + messages_received), 0) as total_messages,
                    COALESCE(SUM(voice_minutes), 0) as total_voice,
                    COALESCE(SUM(showings_booked), 0) as total_showings,
                    COALESCE(SUM(llm_calls), 0) as total_llm_calls
                   FROM usage_metrics
                   WHERE date >= CURRENT_DATE - %s""",
                [days],
            )
            row = await cur.fetchone()

            cur = await conn.execute(
                """SELECT date,
                    COALESCE(SUM(llm_cost_cents + sms_cost_cents + voice_cost_cents), 0) as cost,
                    COALESCE(SUM(messages_sent + messages_received), 0) as messages,
                    COALESCE(SUM(sms_cost_cents), 0) as sms_cost,
                    COALESCE(SUM(voice_cost_cents), 0) as voice_cost
                   FROM usage_metrics
                   WHERE date >= CURRENT_DATE - %s
                   GROUP BY date ORDER BY date""",
                [days],
            )
            daily = await cur.fetchall()

        total_cost = (row["total_llm_cost"] + row["total_sms_cost"] + row["total_voice_cost"]) if row else 0
        result = {
            "total_cost_dollars": round(total_cost / 100, 2),
            "llm_cost_dollars": round((row["total_llm_cost"] if row else 0) / 100, 2),
            "sms_cost_dollars": round((row["total_sms_cost"] if row else 0) / 100, 2),
            "voice_cost_dollars": round((row["total_voice_cost"] if row else 0) / 100, 2),
            "total_sms_segments": row["total_sms_segments"] if row else 0,
            "total_messages": row["total_messages"] if row else 0,
            "total_voice_minutes": float(row["total_voice"] if row else 0),
            "total_showings": row["total_showings"] if row else 0,
            "total_llm_calls": row["total_llm_calls"] if row else 0,
            "daily": daily or [],
        }
        cache_set(cache_key, json.dumps(result, default=str), ttl=300)
        return result
    except psycopg.Error as e:
        logger.error(f"Cost summary query failed: {e}")
        return {
            "total_cost_dollars": 0, "llm_cost_dollars": 0,
            "sms_cost_dollars": 0, "voice_cost_dollars": 0,
            "total_sms_segments": 0, "total_messages": 0,
            "total_voice_minutes": 0, "total_showings": 0,
            "total_llm_calls": 0, "daily": [],
        }


@console_authorized
async def get_cost_by_agent(days: int = 30) -> list[dict]:
    """Per-agent cost breakdown (cached 300s)."""
    cache_key = f"console:costs:by_agent:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.debug("cache hit for %s", cache_key)
        return json.loads(cached)

    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT a.name,
                    COALESCE(SUM(um.messages_sent + um.messages_received), 0) as messages,
                    COALESCE(SUM(um.llm_calls), 0) as llm_calls,
                    COALESCE(SUM(um.llm_tokens_used), 0) as tokens,
                    COALESCE(SUM(um.llm_cost_cents), 0) as llm_cost_cents,
                    COALESCE(SUM(um.sms_cost_cents), 0) as sms_cost_cents,
                    COALESCE(SUM(um.voice_cost_cents), 0) as voice_cost_cents,
                    COALESCE(SUM(um.sms_segments_sent), 0) as sms_segments,
                    COALESCE(SUM(um.voice_minutes), 0) as voice_minutes
                   FROM agents a
                   LEFT JOIN usage_metrics um ON um.agent_id = a.id
                     AND um.date >= CURRENT_DATE - %s
                   GROUP BY a.id, a.name
                   ORDER BY llm_cost_cents + sms_cost_cents + voice_cost_cents DESC""",
                [days],
            )
            rows = await cur.fetchall()

        result = []
        for r in (rows or []):
            msgs = r["messages"] or 0
            total_cost = (r["llm_cost_cents"] or 0) + (r["sms_cost_cents"] or 0) + (r["voice_cost_cents"] or 0)
            result.append({
                **r,
                "cost_dollars": round(total_cost / 100, 2),
                "llm_cost_dollars": round((r["llm_cost_cents"] or 0) / 100, 2),
                "sms_cost_dollars": round((r["sms_cost_cents"] or 0) / 100, 2),
                "voice_cost_dollars": round((r["voice_cost_cents"] or 0) / 100, 2),
                "cost_per_message": round(total_cost / max(msgs, 1) / 100, 4),
            })
        cache_set(cache_key, json.dumps(result, default=str), ttl=300)
        return result
    except psycopg.Error as e:
        logger.error(f"Cost by agent query failed: {e}")
        return []


@console_authorized
async def get_model_tier_breakdown(days: int = 30) -> dict:
    """Percentage of messages by model tier (cached 300s)."""
    cache_key = f"console:costs:model_tier:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        logger.debug("cache hit for %s", cache_key)
        return json.loads(cached)

    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT
                    COALESCE(model_used, 'template') as model,
                    COUNT(*) as cnt
                   FROM messages
                   WHERE ai_generated = true
                   AND created_at > CURRENT_DATE - %s
                   GROUP BY model_used""",
                [days],
            )
            rows = await cur.fetchall()

        total = sum(r["cnt"] for r in (rows or []))
        breakdown = {}
        for r in (rows or []):
            model = r["model"] or "template"
            breakdown[model] = {
                "count": r["cnt"],
                "pct": round(r["cnt"] / max(total, 1) * 100, 1),
            }
        breakdown["_total"] = total
        cache_set(cache_key, json.dumps(breakdown, default=str), ttl=300)
        return breakdown
    except psycopg.Error as e:
        logger.error(f"Model tier breakdown query failed: {e}")
        return {"_total": 0}


# ============================================================
# Health
# ============================================================

@console_authorized
async def get_health_overview() -> HealthOverview:
    """System health combining /health data with operational metrics."""

    async def _check_database() -> tuple[str, str]:
        try:
            async with get_async_db_connection() as conn:
                await conn.execute("SELECT 1")
            return ("database", "green")
        except psycopg.Error:
            return ("database", "red")

    async def _check_redis() -> tuple[str, str]:
        try:
            import redis
            from app.config import get_settings
            settings = get_settings()
            r = redis.from_url(settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
            r.ping()
            return ("redis", "green")
        except Exception:
            return ("redis", "red")

    async def _check_anthropic() -> tuple[str, str]:
        try:
            async with get_async_db_connection() as conn:
                cur = await conn.execute(
                    """SELECT COUNT(*) as cnt FROM messages
                       WHERE ai_generated = true AND model_used IS NOT NULL
                       AND created_at > now() - interval '1 hour'"""
                )
                recent_llm = await cur.fetchone()
            return ("anthropic", "green" if (recent_llm and recent_llm["cnt"] > 0) else "yellow")
        except psycopg.Error:
            return ("anthropic", "red")

    async def _check_twilio() -> tuple[str, str]:
        try:
            async with get_async_db_connection() as conn:
                cur = await conn.execute(
                    """SELECT COUNT(*) as cnt FROM messages
                       WHERE sender_type = 'ai'
                       AND created_at > now() - interval '1 hour'"""
                )
                recent_sms = await cur.fetchone()
            return ("twilio", "green" if (recent_sms and recent_sms["cnt"] > 0) else "yellow")
        except psycopg.Error:
            return ("twilio", "red")

    async def _check_pipeline() -> dict:
        try:
            async with get_async_db_connection() as conn:
                cur = await conn.execute(
                    """SELECT
                        AVG(latency_ms) as avg_latency,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
                       FROM tool_executions
                       WHERE created_at > now() - interval '24 hours'
                       AND latency_ms IS NOT NULL"""
                )
                perf = await cur.fetchone()
                return {
                    "avg_latency_ms": round(perf["avg_latency"] or 0),
                    "p50_ms": round(perf["p50"] or 0),
                    "p95_ms": round(perf["p95"] or 0),
                }
        except psycopg.Error:
            return {"avg_latency_ms": 0, "p50_ms": 0, "p95_ms": 0}

    # Run all checks concurrently
    db_result, redis_result, anthropic_result, twilio_result, pipeline_stats = (
        await asyncio.gather(
            _check_database(), _check_redis(), _check_anthropic(),
            _check_twilio(), _check_pipeline(),
        )
    )

    services = dict([db_result, redis_result, anthropic_result, twilio_result])

    return {
        "services": services,
        "pipeline": pipeline_stats,
    }


@console_authorized
async def get_health_status_color() -> str:
    """Quick health check returning green/yellow/red."""
    try:
        async with get_async_db_connection() as conn:
            await conn.execute("SELECT 1")
        return "green"
    except psycopg.Error:
        return "red"


# ============================================================
# Tenant Management (Phase 2) — sync-only functions
# ============================================================

@_sync_console_authorized
def create_agent_from_wizard(form_data: dict) -> dict:
    """Create a new agent from the onboarding wizard, including listings and contacts."""
    required = ["name", "email", "phone", "twilio_number"]
    for field in required:
        if not form_data.get(field):
            raise ValueError(f"Missing required field: {field}")

    try:
        with get_db_connection() as conn:
            # Check Twilio number uniqueness
            existing = conn.execute(
                "SELECT id FROM agents WHERE twilio_number = %s",
                [form_data["twilio_number"]],
            ).fetchone()
            if existing:
                raise ValueError(f"Twilio number {form_data['twilio_number']} is already assigned.")

            # Build enriched profiles from wizard data
            style_profile = {
                "tone": form_data.get("tone", "professional"),
                "emoji": form_data.get("emoji", "no") == "yes",
                "greeting_style": form_data.get("greeting_style", ""),
                "signoff_style": form_data.get("signoff_style", ""),
                "notes": form_data.get("style_notes", ""),
            }
            autonomy_rules = {
                "level": form_data.get("autonomy_level", "supervised"),
                "escalate_pricing": form_data.get("escalate_pricing") == "yes",
                "escalate_legal": form_data.get("escalate_legal") == "yes",
                "escalate_unhappy": form_data.get("escalate_unhappy") == "yes",
                "escalate_personal": form_data.get("escalate_personal") == "yes",
                "escalate_new_lead": form_data.get("escalate_new_lead") == "yes",
                "notification_method": form_data.get("notification_method", "sms"),
                "notification_frequency": form_data.get("notification_frequency", "batched"),
            }
            scheduling_prefs = {
                "default_duration": int(form_data.get("showing_duration", 60)),
                "buffer_minutes": int(form_data.get("buffer_minutes", 30)),
                "earliest_showing": form_data.get("earliest_showing", "09:00"),
                "latest_showing": form_data.get("latest_showing", "18:00"),
                "after_hours_mode": form_data.get("after_hours_mode", "acknowledge"),
            }

            # Create agent
            row = conn.execute(
                """INSERT INTO agents (name, email, phone, twilio_number, brokerage,
                   market, timezone, style_profile, autonomy_rules, scheduling_prefs,
                   listing_rules, briefing_time, google_review_link, system_prompt)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                [
                    form_data["name"], form_data["email"], form_data["phone"],
                    form_data["twilio_number"], form_data.get("brokerage"),
                    form_data.get("market"), form_data.get("timezone", "America/New_York"),
                    json.dumps(style_profile), json.dumps(autonomy_rules),
                    json.dumps(scheduling_prefs),
                    json.dumps({"dom_alert_days": [30, 60, 90]}),
                    form_data.get("briefing_time", "07:30"),
                    form_data.get("google_review_link"),
                    form_data.get("system_prompt") or None,
                ],
            ).fetchone()
            agent_id = str(row["id"])

            # Insert listings
            listings_added = 0
            idx = 0
            while True:
                addr = form_data.get(f"listing_address_{idx}")
                if addr is None:
                    break
                if addr.strip():
                    price_str = (form_data.get(f"listing_price_{idx}") or "0").replace("$", "").replace(",", "").strip()
                    try:
                        price = int(float(price_str)) if price_str else 0
                    except ValueError:
                        price = 0
                    beds_str = (form_data.get(f"listing_beds_{idx}") or "").strip()
                    baths_str = (form_data.get(f"listing_baths_{idx}") or "").strip()
                    sqft_str = (form_data.get(f"listing_sqft_{idx}") or "").replace(",", "").strip()

                    conn.execute(
                        """INSERT INTO listings (agent_id, address, price, beds, baths, sqft,
                           showing_instructions, lockbox, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        [
                            agent_id, addr.strip(), price,
                            int(beds_str) if beds_str else None,
                            float(baths_str) if baths_str else None,
                            int(sqft_str) if sqft_str else None,
                            form_data.get(f"listing_showing_{idx}") or None,
                            form_data.get(f"listing_lockbox_{idx}") or None,
                            form_data.get(f"listing_status_{idx}", "active"),
                        ],
                    )
                    listings_added += 1
                idx += 1

            # Insert contacts
            contacts_added = 0
            idx = 0
            while True:
                name = form_data.get(f"client_name_{idx}")
                if name is None:
                    break
                if name.strip():
                    conn.execute(
                        """INSERT INTO contacts (agent_id, name, phone, email, role,
                           lifecycle_stage, notes, consent_status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')""",
                        [
                            agent_id, name.strip(),
                            form_data.get(f"client_phone_{idx}") or "",
                            form_data.get(f"client_email_{idx}") or None,
                            form_data.get(f"client_role_{idx}", "lead"),
                            form_data.get(f"client_stage_{idx}", "new_lead"),
                            form_data.get(f"client_notes_{idx}") or None,
                        ],
                    )
                    contacts_added += 1
                idx += 1

            conn.commit()

        # Build checklist
        checklist = [
            {"label": "Account created", "done": True, "hint": None},
            {"label": "Twilio number linked", "done": True, "hint": form_data["twilio_number"]},
            {"label": "Communication style configured", "done": True, "hint": f'{form_data.get("tone", "professional")} tone'},
            {"label": "Scheduling preferences set", "done": True, "hint": f'{form_data.get("showing_duration", 60)} min showings'},
            {"label": "Autonomy rules configured", "done": True, "hint": f'{form_data.get("autonomy_level", "supervised")} mode'},
            {"label": f"Listings added ({listings_added})", "done": listings_added > 0, "hint": "Add from tenant detail page" if not listings_added else None},
            {"label": f"Clients imported ({contacts_added})", "done": contacts_added > 0, "hint": "Import from tenant detail page" if not contacts_added else None},
            {"label": "Connect Google Calendar", "done": False, "hint": "OAuth from tenant detail page"},
            {"label": "Configure Vapi voice agent", "done": False, "hint": "Set up voice coverage"},
            {"label": "Send test message", "done": False, "hint": "Verify Twilio channel works"},
        ]

        cache_invalidate("console:agents:all")
        cache_invalidate("console:agents:options")

        logger.info(f"Wizard onboarded agent: {form_data['name']} ({agent_id}) — {listings_added} listings, {contacts_added} contacts")
        return {
            "agent_id": agent_id,
            "agent_name": form_data["name"],
            "checklist": checklist,
        }

    except ValueError:
        raise
    except psycopg.Error as e:
        raise ValueError(f"Failed to create agent: {e}")


@_sync_console_authorized
def create_agent_tenant(form_data: dict) -> str:
    """Create a new agent from console form data."""
    required = ["name", "email", "phone", "twilio_number"]
    for field in required:
        if not form_data.get(field):
            raise ValueError(f"Missing required field: {field}")

    try:
        with get_db_connection() as conn:
            # Check Twilio number uniqueness
            existing = conn.execute(
                "SELECT id FROM agents WHERE twilio_number = %s",
                [form_data["twilio_number"]],
            ).fetchone()
            if existing:
                raise ValueError(f"Twilio number {form_data['twilio_number']} is already assigned.")

            style_profile = {
                "tone": form_data.get("tone", "professional"),
                "emoji": form_data.get("emoji", "no") == "yes",
            }
            autonomy_rules = {
                "level": form_data.get("autonomy_level", "supervised"),
            }
            scheduling_prefs = {
                "buffer_minutes": int(form_data.get("buffer_minutes", 30)),
            }

            row = conn.execute(
                """INSERT INTO agents (name, email, phone, twilio_number, brokerage,
                   market, timezone, style_profile, autonomy_rules, scheduling_prefs,
                   briefing_time, google_review_link, system_prompt)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                [
                    form_data["name"], form_data["email"], form_data["phone"],
                    form_data["twilio_number"], form_data.get("brokerage"),
                    form_data.get("market"), form_data.get("timezone", "America/New_York"),
                    json.dumps(style_profile), json.dumps(autonomy_rules),
                    json.dumps(scheduling_prefs),
                    form_data.get("briefing_time", "07:30"),
                    form_data.get("google_review_link"),
                    form_data.get("system_prompt"),
                ],
            ).fetchone()
            conn.commit()
            cache_invalidate("console:agents:all")
            cache_invalidate("console:agents:options")
            return str(row["id"])
    except ValueError:
        raise
    except psycopg.Error as e:
        raise ValueError(f"Failed to create agent: {e}")


@_sync_console_authorized
def update_agent_tenant(agent_id: str, form_data: dict) -> None:
    """Update an existing agent's configuration."""
    try:
        style_profile = {
            "tone": form_data.get("tone", "professional"),
            "emoji": form_data.get("emoji", "no") == "yes",
        }
        autonomy_rules = {
            "level": form_data.get("autonomy_level", "supervised"),
        }

        with get_db_connection() as conn:
            conn.execute(
                """UPDATE agents SET
                    name = %s, email = %s, phone = %s, brokerage = %s,
                    market = %s, timezone = %s, style_profile = %s,
                    autonomy_rules = %s, briefing_time = %s,
                    google_review_link = %s, system_prompt = %s,
                    updated_at = now()
                   WHERE id = %s""",
                [
                    form_data.get("name"), form_data.get("email"),
                    form_data.get("phone"), form_data.get("brokerage"),
                    form_data.get("market"), form_data.get("timezone", "America/New_York"),
                    json.dumps(style_profile), json.dumps(autonomy_rules),
                    form_data.get("briefing_time", "07:30"),
                    form_data.get("google_review_link"),
                    form_data.get("system_prompt"),
                    agent_id,
                ],
            )
            conn.commit()

        # Invalidate Redis cache
        cache_invalidate("console:agents:all")
        cache_invalidate("console:agents:options")
        try:
            from app.services.agent_config import invalidate_agent_cache
            invalidate_agent_cache(UUID(agent_id))
        except redis.RedisError:
            pass
    except psycopg.Error as e:
        raise ValueError(f"Failed to update agent: {e}")


@console_authorized
async def deactivate_agent(agent_id: str) -> None:
    """Deactivate a tenant — stops triggers, doesn't delete data."""
    try:
        async with get_async_db_connection() as conn:
            await conn.execute(
                "UPDATE agents SET current_status = 'deactivated' WHERE id = %s",
                [agent_id],
            )
            await conn.execute(
                """UPDATE triggers SET status = 'cancelled'
                   WHERE agent_id = %s AND status = 'pending'""",
                [agent_id],
            )
            await conn.commit()
        cache_invalidate("console:agents:all")
        cache_invalidate("console:agents:options")
    except psycopg.Error as e:
        logger.error(f"Deactivate agent failed: {e}")


@_sync_console_authorized
def send_test_sms(agent_id: str) -> None:
    """Send a test SMS to the agent's phone."""
    try:
        with get_db_connection() as conn:
            agent = conn.execute(
                "SELECT phone, twilio_number, name FROM agents WHERE id = %s",
                [agent_id],
            ).fetchone()

        if agent:
            from app.services.twilio_service import send_sms
            send_sms(
                to=agent["phone"],
                from_=agent["twilio_number"],
                body=f"Test message from {agent['name']}'s AI assistant. System is working!",
                agent_id=UUID(agent_id),
            )
    except psycopg.Error as e:
        raise RuntimeError(f"Test SMS failed: {e}")


@_sync_console_authorized
def run_manual_scan(agent_id: str) -> None:
    """Manually run the daily scanner for an agent."""
    try:
        from app.worker.daily_scanner import scan_agent
        from app.services.agent_config import get_agent_by_id
        agent = get_agent_by_id(UUID(agent_id))
        if agent:
            scan_agent(agent)
    except (psycopg.Error, Exception) as e:  # Broad catch: scanner can throw non-DB errors
        logger.error(f"Manual scan failed: {e}")


# ============================================================
# Messages Tab (Customer Detail — Conversations by Contact)
# ============================================================

@console_authorized
async def get_conversations_by_contact(
    agent_id: str,
    limit: int = 25,
    offset: int = 0,
) -> list[dict]:
    """Conversations grouped by contact for the Messages tab.

    For NULL contact_id, groups under 'Unknown Contact'.
    Returns: contact name, phone, channel, message count, last message
    preview, last message timestamp. Ordered by most recent activity.
    """
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """WITH latest_msg AS (
                       SELECT DISTINCT ON (cv.contact_id)
                              cv.contact_id,
                              m.body AS last_message_preview
                       FROM messages m
                       JOIN conversations cv ON m.conversation_id = cv.id
                       WHERE cv.agent_id = %s
                       ORDER BY cv.contact_id, m.created_at DESC
                   )
                   SELECT
                       COALESCE(c.id::text, 'unknown') AS contact_id,
                       COALESCE(c.name, 'Unknown Contact') AS contact_name,
                       COALESCE(c.phone, '') AS phone,
                       array_agg(DISTINCT cv.channel) AS channels,
                       SUM(sub.msg_count)::int AS message_count,
                       MAX(sub.last_msg_at) AS last_message_at,
                       lm.last_message_preview
                   FROM conversations cv
                   LEFT JOIN contacts c ON cv.contact_id = c.id
                   JOIN LATERAL (
                       SELECT COUNT(*) AS msg_count, MAX(m.created_at) AS last_msg_at
                       FROM messages m WHERE m.conversation_id = cv.id
                   ) sub ON true
                   LEFT JOIN latest_msg lm ON lm.contact_id IS NOT DISTINCT FROM c.id
                   WHERE cv.agent_id = %s
                     AND sub.msg_count > 0
                   GROUP BY c.id, c.name, c.phone, lm.last_message_preview
                   ORDER BY MAX(sub.last_msg_at) DESC NULLS LAST
                   LIMIT %s OFFSET %s""",
                [agent_id, agent_id, limit, offset],
            )
            rows = await cur.fetchall()
        return rows or []
    except psycopg.Error as e:
        logger.error(f"Conversations by contact query failed: {e}")
        return []


@console_authorized
async def get_conversation_thread(
    agent_id: str,
    contact_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Full conversation thread for a contact with tool execution details.

    Returns messages and correlated tool executions (within 5 seconds of
    message timestamp).
    """
    try:
        async with get_async_db_connection() as conn:
            # Handle 'unknown' placeholder for NULL contact_id
            if contact_id == "unknown":
                contact_filter = "cv.contact_id IS NULL"
                params_msgs = [agent_id, limit, offset]
                params_tools = [agent_id]
            else:
                contact_filter = "cv.contact_id = %s"
                params_msgs = [contact_id, agent_id, limit, offset]
                params_tools = [contact_id, agent_id]

            # Messages
            if contact_id == "unknown":
                msg_sql = f"""
                    SELECT m.id, m.sender_type, m.body, m.created_at, m.model_used,
                           m.delivery_status, m.failure_reason, m.intent, m.tokens_used,
                           cv.channel, cv.id AS conversation_id
                    FROM messages m
                    JOIN conversations cv ON m.conversation_id = cv.id
                    WHERE cv.contact_id IS NULL AND cv.agent_id = %s
                    ORDER BY m.created_at DESC
                    LIMIT %s OFFSET %s"""
            else:
                msg_sql = f"""
                    SELECT m.id, m.sender_type, m.body, m.created_at, m.model_used,
                           m.delivery_status, m.failure_reason, m.intent, m.tokens_used,
                           cv.channel, cv.id AS conversation_id
                    FROM messages m
                    JOIN conversations cv ON m.conversation_id = cv.id
                    WHERE cv.contact_id = %s AND cv.agent_id = %s
                    ORDER BY m.created_at DESC
                    LIMIT %s OFFSET %s"""

            cur = await conn.execute(msg_sql, params_msgs)
            messages = await cur.fetchall()

            # Tool executions — bounded to the message time window
            tool_execs = []
            if messages:
                timestamps = [m["created_at"] for m in messages if m["created_at"]]
                if timestamps:
                    earliest = min(timestamps) - timedelta(seconds=5)
                    latest = max(timestamps) + timedelta(seconds=5)

                    if contact_id == "unknown":
                        tool_sql = """
                            SELECT te.id, te.tool_name, te.input_json, te.output_json,
                                   te.status, te.error_message, te.latency_ms, te.created_at,
                                   te.conversation_id
                            FROM tool_executions te
                            JOIN conversations cv ON te.conversation_id = cv.id
                            WHERE cv.contact_id IS NULL AND cv.agent_id = %s
                              AND te.created_at >= %s AND te.created_at <= %s
                            ORDER BY te.created_at"""
                        tool_params = [agent_id, earliest, latest]
                    else:
                        tool_sql = """
                            SELECT te.id, te.tool_name, te.input_json, te.output_json,
                                   te.status, te.error_message, te.latency_ms, te.created_at,
                                   te.conversation_id
                            FROM tool_executions te
                            JOIN conversations cv ON te.conversation_id = cv.id
                            WHERE cv.contact_id = %s AND cv.agent_id = %s
                              AND te.created_at >= %s AND te.created_at <= %s
                            ORDER BY te.created_at"""
                        tool_params = [contact_id, agent_id, earliest, latest]

                    cur = await conn.execute(tool_sql, tool_params)
                    tool_execs = await cur.fetchall()

        # Correlate tool executions to messages using O(n log n) bisect approach

        messages_list = list(messages) if messages else []
        for msg in messages_list:
            msg["tool_executions"] = []

        if tool_execs and messages_list:
            # Group AI/system messages by conversation_id, sorted by timestamp
            conv_msgs: dict[str, list] = defaultdict(list)
            for msg in messages_list:
                if msg["sender_type"] in ("ai", "system") and msg["created_at"]:
                    conv_msgs[msg["conversation_id"]].append(msg)

            # Sort each group by timestamp for binary search
            conv_timestamps: dict[str, list[float]] = {}
            for conv_id, msgs in conv_msgs.items():
                msgs.sort(key=lambda m: m["created_at"])
                conv_timestamps[conv_id] = [
                    m["created_at"].timestamp() for m in msgs
                ]

            for te in tool_execs:
                conv_id = te["conversation_id"]
                if conv_id not in conv_msgs:
                    continue
                te_ts = te["created_at"].timestamp()
                ts_list = conv_timestamps[conv_id]
                msg_list = conv_msgs[conv_id]

                # Binary search for closest message within 5-second window
                idx = bisect_left(ts_list, te_ts)
                best_msg = None
                best_delta = None

                # Check the candidate at idx and idx-1 (the two nearest)
                for candidate_idx in (idx - 1, idx):
                    if 0 <= candidate_idx < len(ts_list):
                        delta = abs(ts_list[candidate_idx] - te_ts)
                        if delta <= 5 and (best_delta is None or delta < best_delta):
                            best_delta = delta
                            best_msg = msg_list[candidate_idx]

                if best_msg is not None:
                    best_msg["tool_executions"].append(te)

        return {
            "messages": messages_list,
            "total_tool_executions": len(tool_execs) if tool_execs else 0,
        }
    except psycopg.Error as e:
        logger.error(f"Conversation thread query failed: {e}")
        return {"messages": [], "total_tool_executions": 0}


# ============================================================
# Knowledge Base Tab (Customer Detail)
# ============================================================

@console_authorized
async def get_knowledge_base_items(agent_id: str) -> list[dict]:
    """All embeddings for an agent grouped by source_type/source_id.

    Returns: source_id, title, source_type, chunk count, indexed date,
    expires_at, and computed status (active/expiring_soon/expired).
    """
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT source_type,
                       source_id,
                       MAX(title) AS title,
                       COUNT(*) AS chunk_count,
                       MIN(created_at) AS indexed_date,
                       MAX(expires_at) AS expires_at,
                       CASE
                           WHEN MAX(expires_at) IS NULL THEN 'active'
                           WHEN MAX(expires_at) < now() THEN 'expired'
                           WHEN MAX(expires_at) < now() + interval '7 days' THEN 'expiring_soon'
                           ELSE 'active'
                       END AS status
                   FROM embeddings
                   WHERE agent_id = %s
                   GROUP BY source_type, source_id
                   ORDER BY source_type, MAX(updated_at) DESC""",
                [agent_id],
            )
            rows = await cur.fetchall()
        return rows or []
    except psycopg.Error as e:
        logger.error(f"Knowledge base items query failed: {e}")
        return []


@console_authorized
async def get_kb_settings(agent_id: str) -> dict:
    """Return the agent's KB expiration policy and default TTL."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                "SELECT kb_expiration_policy, kb_default_ttl_days FROM agents WHERE id = %s",
                [agent_id],
            )
            row = await cur.fetchone()
        if row:
            return {
                "kb_expiration_policy": row["kb_expiration_policy"] or "remind_only",
                "kb_default_ttl_days": row["kb_default_ttl_days"],
            }
        return {"kb_expiration_policy": "remind_only", "kb_default_ttl_days": None}
    except psycopg.Error as e:
        logger.error(f"KB settings query failed: {e}")
        return {"kb_expiration_policy": "remind_only", "kb_default_ttl_days": None}


@console_authorized
async def update_kb_settings(
    agent_id: str, policy: str, default_ttl: int | None = None,
) -> None:
    """Update the agent's KB expiration policy and default TTL."""
    if policy not in ("auto_remove", "remind_only"):
        raise ValueError(f"Invalid KB policy: {policy}")
    try:
        async with get_async_db_connection() as conn:
            await conn.execute(
                """UPDATE agents
                   SET kb_expiration_policy = %s, kb_default_ttl_days = %s
                   WHERE id = %s""",
                [policy, default_ttl, agent_id],
            )
            await conn.commit()
    except psycopg.Error as e:
        logger.error(f"KB settings update failed: {e}")
        raise


@console_authorized
async def remove_kb_item(agent_id: str, source_type: str, source_id: str) -> int:
    """Delete all embedding chunks for a given source. Returns count deleted."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """DELETE FROM embeddings
                   WHERE agent_id = %s AND source_type = %s AND source_id = %s
                   RETURNING id""",
                [agent_id, source_type, source_id],
            )
            deleted = await cur.fetchall()
            await conn.commit()
        return len(deleted) if deleted else 0
    except psycopg.Error as e:
        logger.error(f"KB item removal failed: {e}")
        raise


@console_authorized
async def set_kb_item_expiration(
    agent_id: str, source_type: str, source_id: str, expires_at: str | None,
) -> None:
    """Set or clear the expiration date for all chunks of a KB source item."""
    try:
        async with get_async_db_connection() as conn:
            await conn.execute(
                """UPDATE embeddings SET expires_at = %s
                   WHERE agent_id = %s AND source_type = %s AND source_id = %s""",
                [expires_at, agent_id, source_type, source_id],
            )
            await conn.commit()
    except psycopg.Error as e:
        logger.error(f"KB item expiration update failed: {e}")
        raise


# ============================================================
# Message Queue Monitoring (DLQ)
# ============================================================

@_sync_console_authorized
def get_dead_letter_count() -> int:
    """Return the number of messages in the Redis dead-letter queue stream."""
    try:
        from app.services.redis_pool import get_redis_pool
        r = get_redis_pool()
        length = r.xlen("calloway:dlq")
        return int(length)
    except psycopg.Error as e:
        logger.error("Failed to read DLQ length from Redis: %s", e)
        return -1


@_sync_console_authorized
def get_stream_info() -> dict:
    """Return basic info about the inbound stream and DLQ for monitoring."""
    try:
        from app.services.redis_pool import get_redis_pool
        r = get_redis_pool()
        inbound_len = r.xlen("calloway:inbound")
        dlq_len = r.xlen("calloway:dlq")
        return {
            "inbound_stream_length": int(inbound_len),
            "dlq_length": int(dlq_len),
        }
    except psycopg.Error as e:
        logger.error("Failed to read stream info from Redis: %s", e)
        return {"inbound_stream_length": -1, "dlq_length": -1}


# ============================================================
# Paginated Contacts & Listings (PERF-008)
# ============================================================

@console_authorized
async def get_agent_contacts_paginated(
    agent_id: str, limit: int = 25, offset: int = 0,
) -> list[dict]:
    """Paginated contacts for a single agent."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT id, name, phone, email, role, lifecycle_stage,
                          consent_status, last_contact_at, silent_mode,
                          interaction_count
                   FROM contacts WHERE agent_id = %s
                   ORDER BY last_contact_at DESC NULLS LAST
                   LIMIT %s OFFSET %s""",
                [agent_id, limit, offset],
            )
            rows = await cur.fetchall()
        return rows or []
    except psycopg.Error as e:
        logger.error(f"Agent contacts paginated query failed: {e}")
        return []


@console_authorized
async def get_agent_listings_paginated(
    agent_id: str, limit: int = 25, offset: int = 0,
) -> list[dict]:
    """Paginated listings for a single agent."""
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                """SELECT id, address, price, status, beds, baths, sqft,
                          list_date
                   FROM listings WHERE agent_id = %s
                   ORDER BY created_at DESC
                   LIMIT %s OFFSET %s""",
                [agent_id, limit, offset],
            )
            rows = await cur.fetchall()
        return rows or []
    except psycopg.Error as e:
        logger.error(f"Agent listings paginated query failed: {e}")
        return []


# ============================================================
# Sync wrappers — for callers that cannot use async (harness, tests)
# ============================================================

def sync_get_all_agents() -> list[dict]:
    """Sync wrapper around get_all_agents() for non-async callers."""
    return asyncio.run(get_all_agents())
