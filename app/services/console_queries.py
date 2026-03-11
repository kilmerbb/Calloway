"""Console query layer — cross-tenant queries for operator visibility.

All queries bypass RLS by using the service key connection directly
(no set_agent_context). This is operator-level access.
"""
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)


# ============================================================
# System Pulse (Dashboard)
# ============================================================

def get_system_pulse() -> dict:
    """Top-level system stats for the dashboard."""
    try:
        with get_db_connection() as conn:
            agents = conn.execute(
                "SELECT COUNT(*) as cnt FROM agents"
            ).fetchone()

            msgs_today = conn.execute(
                """SELECT COALESCE(SUM(messages_sent + messages_received), 0) as cnt
                   FROM usage_metrics WHERE date = CURRENT_DATE"""
            ).fetchone()

            msgs_24h = conn.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE created_at > now() - interval '24 hours'"""
            ).fetchone()

            errors_24h = conn.execute(
                """SELECT COUNT(*) as cnt FROM tool_executions
                   WHERE error_message IS NOT NULL
                   AND created_at > now() - interval '24 hours'"""
            ).fetchone()

            cost_today = conn.execute(
                """SELECT COALESCE(SUM(llm_cost_cents + sms_cost_cents + voice_cost_cents), 0) as cost
                   FROM usage_metrics WHERE date = CURRENT_DATE"""
            ).fetchone()

        return {
            "total_agents": agents["cnt"] if agents else 0,
            "messages_today": msgs_today["cnt"] if msgs_today else 0,
            "messages_24h": msgs_24h["cnt"] if msgs_24h else 0,
            "errors_24h": errors_24h["cnt"] if errors_24h else 0,
            "cost_today_dollars": round((cost_today["cost"] if cost_today else 0) / 100, 2),
        }
    except Exception as e:
        logger.error(f"System pulse query failed: {e}")
        return {
            "total_agents": 0, "messages_today": 0, "messages_24h": 0,
            "errors_24h": 0, "cost_today_dollars": 0,
        }


def get_recent_activity(limit: int = 20) -> list[dict]:
    """Recent events across the system for the activity feed."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """SELECT m.created_at, m.sender_type, m.body,
                          a.name as agent_name, c.name as contact_name,
                          m.ai_generated, m.model_used
                   FROM messages m
                   JOIN conversations cv ON m.conversation_id = cv.id
                   JOIN agents a ON cv.agent_id = a.id
                   LEFT JOIN contacts c ON cv.contact_id = c.id
                   ORDER BY m.created_at DESC LIMIT %s""",
                [limit],
            ).fetchall()
        return rows or []
    except Exception as e:
        logger.error(f"Recent activity query failed: {e}")
        return []


def get_agents_needing_attention() -> list[dict]:
    """Agents with errors or no recent activity."""
    try:
        with get_db_connection() as conn:
            # Agents with errors in last 24h
            error_agents = conn.execute(
                """SELECT a.id, a.name, COUNT(te.id) as error_count
                   FROM agents a
                   JOIN tool_executions te ON te.agent_id = a.id
                   WHERE te.error_message IS NOT NULL
                   AND te.created_at > now() - interval '24 hours'
                   GROUP BY a.id, a.name
                   ORDER BY error_count DESC"""
            ).fetchall()

            # Agents with no activity in 48h+
            inactive_agents = conn.execute(
                """SELECT a.id, a.name, MAX(um.date) as last_active
                   FROM agents a
                   LEFT JOIN usage_metrics um ON um.agent_id = a.id
                   GROUP BY a.id, a.name
                   HAVING MAX(um.date) < CURRENT_DATE - 2
                   OR MAX(um.date) IS NULL"""
            ).fetchall()

        return {
            "error_agents": error_agents or [],
            "inactive_agents": inactive_agents or [],
        }
    except Exception as e:
        logger.error(f"Attention query failed: {e}")
        return {"error_agents": [], "inactive_agents": []}


# ============================================================
# Agents / Tenants
# ============================================================

def get_all_agents() -> list[dict]:
    """All agents with summary stats."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """SELECT a.*,
                    (SELECT COUNT(*) FROM contacts WHERE agent_id = a.id) as contact_count,
                    (SELECT COALESCE(SUM(messages_sent), 0) FROM usage_metrics
                     WHERE agent_id = a.id AND date = CURRENT_DATE) as messages_today,
                    (SELECT MAX(date) FROM usage_metrics WHERE agent_id = a.id) as last_active,
                    (SELECT COUNT(*) FROM tool_executions
                     WHERE agent_id = a.id AND error_message IS NOT NULL
                     AND created_at > now() - interval '24 hours') as errors_24h
                   FROM agents a ORDER BY a.name"""
            ).fetchall()
        return rows or []
    except Exception as e:
        logger.error(f"Get all agents failed: {e}")
        return []


def get_agent_detail(agent_id: str) -> dict | None:
    """Full agent record with all related data."""
    try:
        with get_db_connection() as conn:
            agent = conn.execute(
                "SELECT * FROM agents WHERE id = %s", [agent_id]
            ).fetchone()
            if not agent:
                return None

            contacts = conn.execute(
                """SELECT id, name, phone, role, lifecycle_stage, consent_status,
                          last_contact_at, silent_mode
                   FROM contacts WHERE agent_id = %s
                   ORDER BY last_contact_at DESC NULLS LAST""",
                [agent_id],
            ).fetchall()

            listings = conn.execute(
                """SELECT id, address, price, status, list_date
                   FROM listings WHERE agent_id = %s ORDER BY created_at DESC""",
                [agent_id],
            ).fetchall()

            recent_msgs = conn.execute(
                """SELECT m.body, m.sender_type, m.created_at, m.model_used,
                          c.name as contact_name
                   FROM messages m
                   JOIN conversations cv ON m.conversation_id = cv.id
                   LEFT JOIN contacts c ON cv.contact_id = c.id
                   WHERE m.agent_id = %s
                   ORDER BY m.created_at DESC LIMIT 50""",
                [agent_id],
            ).fetchall()

            triggers = conn.execute(
                """SELECT * FROM triggers
                   WHERE agent_id = %s AND status = 'pending'
                   ORDER BY scheduled_at LIMIT 10""",
                [agent_id],
            ).fetchall()

            cost_month = conn.execute(
                """SELECT COALESCE(SUM(llm_cost_cents), 0) as cost,
                          COALESCE(SUM(messages_sent), 0) as msgs
                   FROM usage_metrics
                   WHERE agent_id = %s
                   AND date >= date_trunc('month', CURRENT_DATE)""",
                [agent_id],
            ).fetchone()

            errors = conn.execute(
                """SELECT COUNT(*) as cnt FROM tool_executions
                   WHERE agent_id = %s AND error_message IS NOT NULL
                   AND created_at > now() - interval '24 hours'""",
                [agent_id],
            ).fetchone()

        return {
            "agent": agent,
            "contacts": contacts or [],
            "listings": listings or [],
            "recent_messages": recent_msgs or [],
            "pending_triggers": triggers or [],
            "cost_this_month_dollars": round((cost_month["cost"] if cost_month else 0) / 100, 2),
            "messages_this_month": cost_month["msgs"] if cost_month else 0,
            "errors_24h": errors["cnt"] if errors else 0,
        }
    except Exception as e:
        logger.error(f"Agent detail query failed: {e}")
        return None


# ============================================================
# Conversations
# ============================================================

def get_recent_conversations(
    agent_id: str | None = None,
    channel: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Recent conversations with filtering."""
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
            params.extend([f"%{search}%", f"%{search}%"])

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        with get_db_connection() as conn:
            rows = conn.execute(
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
                    LIMIT %s""",
                params + [limit],
            ).fetchall()
        return rows or []
    except Exception as e:
        logger.error(f"Conversations query failed: {e}")
        return []


def get_conversation_detail(conversation_id: str) -> dict | None:
    """Full conversation thread with messages and tool executions."""
    try:
        with get_db_connection() as conn:
            conv = conn.execute(
                """SELECT cv.*, a.name as agent_name, c.name as contact_name,
                          c.phone as contact_phone, c.role, c.lifecycle_stage,
                          c.id as contact_id
                   FROM conversations cv
                   JOIN agents a ON cv.agent_id = a.id
                   LEFT JOIN contacts c ON cv.contact_id = c.id
                   WHERE cv.id = %s""",
                [conversation_id],
            ).fetchone()
            if not conv:
                return None

            messages = conn.execute(
                """SELECT * FROM messages
                   WHERE conversation_id = %s
                   ORDER BY created_at""",
                [conversation_id],
            ).fetchall()

            tool_execs = conn.execute(
                """SELECT * FROM tool_executions
                   WHERE conversation_id = %s
                   ORDER BY created_at""",
                [conversation_id],
            ).fetchall()

            triggers = []
            if conv.get("contact_id"):
                triggers = conn.execute(
                    """SELECT * FROM triggers
                       WHERE agent_id = %s AND entity_id = %s AND status = 'pending'
                       ORDER BY scheduled_at""",
                    [str(conv["agent_id"]), str(conv["contact_id"])],
                ).fetchall() or []

        return {
            "conversation": conv,
            "messages": messages or [],
            "tool_executions": tool_execs or [],
            "triggers": triggers,
        }
    except Exception as e:
        logger.error(f"Conversation detail query failed: {e}")
        return None


# ============================================================
# Triggers
# ============================================================

def get_trigger_queue(
    status: str | None = None,
    agent_id: str | None = None,
) -> list[dict]:
    """All triggers with optional filtering."""
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

        with get_db_connection() as conn:
            rows = conn.execute(
                f"""SELECT t.*, a.name as agent_name
                    FROM triggers t
                    JOIN agents a ON t.agent_id = a.id
                    {where}
                    ORDER BY t.scheduled_at""",
                params,
            ).fetchall()
        return rows or []
    except Exception as e:
        logger.error(f"Trigger queue query failed: {e}")
        return []


def retry_trigger(trigger_id: str) -> None:
    """Reset a failed trigger to pending with scheduled_at = now."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                """UPDATE triggers SET status = 'pending', scheduled_at = now()
                   WHERE id = %s""",
                [trigger_id],
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Retry trigger failed: {e}")


def cancel_trigger(trigger_id: str) -> None:
    """Cancel a pending trigger."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE triggers SET status = 'cancelled' WHERE id = %s",
                [trigger_id],
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Cancel trigger failed: {e}")


def fire_trigger_now(trigger_id: str) -> None:
    """Set a trigger to fire immediately."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE triggers SET scheduled_at = now() WHERE id = %s AND status = 'pending'",
                [trigger_id],
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Fire trigger now failed: {e}")


# ============================================================
# Errors
# ============================================================

def get_recent_errors(
    limit: int = 100,
    agent_id: str | None = None,
) -> list[dict]:
    """Tool execution errors + error_log entries."""
    try:
        conditions = ["te.error_message IS NOT NULL"]
        params = []

        if agent_id:
            conditions.append("te.agent_id = %s")
            params.append(agent_id)

        where = "WHERE " + " AND ".join(conditions)

        with get_db_connection() as conn:
            rows = conn.execute(
                f"""SELECT te.*, a.name as agent_name
                    FROM tool_executions te
                    JOIN agents a ON te.agent_id = a.id
                    {where}
                    ORDER BY te.created_at DESC LIMIT %s""",
                params + [limit],
            ).fetchall()

            # Also check error_log if it exists
            error_log_rows = []
            try:
                error_log_rows = conn.execute(
                    """SELECT el.*, a.name as agent_name
                       FROM error_log el
                       LEFT JOIN agents a ON el.agent_id = a.id
                       ORDER BY el.created_at DESC LIMIT %s""",
                    [limit],
                ).fetchall() or []
            except Exception:
                pass  # Table may not exist yet

        return {
            "tool_errors": rows or [],
            "app_errors": error_log_rows,
        }
    except Exception as e:
        logger.error(f"Recent errors query failed: {e}")
        return {"tool_errors": [], "app_errors": []}


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
    except Exception as e:
        logger.error(f"Failed to log error: {e}")


# ============================================================
# Costs
# ============================================================

def get_cost_summary(days: int = 30) -> dict:
    """System-wide cost summary."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
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
            ).fetchone()

            daily = conn.execute(
                """SELECT date,
                    COALESCE(SUM(llm_cost_cents + sms_cost_cents + voice_cost_cents), 0) as cost,
                    COALESCE(SUM(messages_sent + messages_received), 0) as messages,
                    COALESCE(SUM(sms_cost_cents), 0) as sms_cost,
                    COALESCE(SUM(voice_cost_cents), 0) as voice_cost
                   FROM usage_metrics
                   WHERE date >= CURRENT_DATE - %s
                   GROUP BY date ORDER BY date""",
                [days],
            ).fetchall()

        total_cost = (row["total_llm_cost"] + row["total_sms_cost"] + row["total_voice_cost"]) if row else 0
        return {
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
    except Exception as e:
        logger.error(f"Cost summary query failed: {e}")
        return {
            "total_cost_dollars": 0, "llm_cost_dollars": 0,
            "sms_cost_dollars": 0, "voice_cost_dollars": 0,
            "total_sms_segments": 0, "total_messages": 0,
            "total_voice_minutes": 0, "total_showings": 0,
            "total_llm_calls": 0, "daily": [],
        }


def get_cost_by_agent(days: int = 30) -> list[dict]:
    """Per-agent cost breakdown."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
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
            ).fetchall()

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
        return result
    except Exception as e:
        logger.error(f"Cost by agent query failed: {e}")
        return []


def get_model_tier_breakdown(days: int = 30) -> dict:
    """Percentage of messages by model tier."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """SELECT
                    COALESCE(model_used, 'template') as model,
                    COUNT(*) as cnt
                   FROM messages
                   WHERE ai_generated = true
                   AND created_at > CURRENT_DATE - %s
                   GROUP BY model_used""",
                [days],
            ).fetchall()

        total = sum(r["cnt"] for r in (rows or []))
        breakdown = {}
        for r in (rows or []):
            model = r["model"] or "template"
            breakdown[model] = {
                "count": r["cnt"],
                "pct": round(r["cnt"] / max(total, 1) * 100, 1),
            }
        breakdown["_total"] = total
        return breakdown
    except Exception as e:
        logger.error(f"Model tier breakdown query failed: {e}")
        return {"_total": 0}


# ============================================================
# Health
# ============================================================

def get_health_overview() -> dict:
    """System health combining /health data with operational metrics."""
    services = {}

    # Database
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1")
        services["database"] = "green"
    except Exception:
        services["database"] = "red"

    # Redis
    try:
        import redis
        from app.config import get_settings
        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL, socket_timeout=2)
        r.ping()
        services["redis"] = "green"
    except Exception:
        services["redis"] = "red"

    # Check Anthropic (recent successful LLM call)
    try:
        with get_db_connection() as conn:
            recent_llm = conn.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE ai_generated = true AND model_used IS NOT NULL
                   AND created_at > now() - interval '1 hour'"""
            ).fetchone()
        services["anthropic"] = "green" if (recent_llm and recent_llm["cnt"] > 0) else "yellow"
    except Exception:
        services["anthropic"] = "red"

    # Check Twilio (recent sent message)
    try:
        with get_db_connection() as conn:
            recent_sms = conn.execute(
                """SELECT COUNT(*) as cnt FROM messages
                   WHERE sender_type = 'ai'
                   AND created_at > now() - interval '1 hour'"""
            ).fetchone()
        services["twilio"] = "green" if (recent_sms and recent_sms["cnt"] > 0) else "yellow"
    except Exception:
        services["twilio"] = "red"

    # Pipeline performance
    pipeline_stats = {}
    try:
        with get_db_connection() as conn:
            perf = conn.execute(
                """SELECT
                    AVG(latency_ms) as avg_latency,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95
                   FROM tool_executions
                   WHERE created_at > now() - interval '24 hours'
                   AND latency_ms IS NOT NULL"""
            ).fetchone()
            pipeline_stats = {
                "avg_latency_ms": round(perf["avg_latency"] or 0),
                "p50_ms": round(perf["p50"] or 0),
                "p95_ms": round(perf["p95"] or 0),
            }
    except Exception:
        pipeline_stats = {"avg_latency_ms": 0, "p50_ms": 0, "p95_ms": 0}

    return {
        "services": services,
        "pipeline": pipeline_stats,
    }


def get_health_status_color() -> str:
    """Quick health check returning green/yellow/red."""
    try:
        with get_db_connection() as conn:
            conn.execute("SELECT 1")
        return "green"
    except Exception:
        return "red"


# ============================================================
# Tenant Management (Phase 2)
# ============================================================

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

        logger.info(f"Wizard onboarded agent: {form_data['name']} ({agent_id}) — {listings_added} listings, {contacts_added} contacts")
        return {
            "agent_id": agent_id,
            "agent_name": form_data["name"],
            "checklist": checklist,
        }

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to create agent: {e}")


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
            return str(row["id"])
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to create agent: {e}")


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
        try:
            from app.services.agent_config import invalidate_agent_cache
            invalidate_agent_cache(UUID(agent_id))
        except Exception:
            pass
    except Exception as e:
        raise ValueError(f"Failed to update agent: {e}")


def deactivate_agent(agent_id: str) -> None:
    """Deactivate a tenant — stops triggers, doesn't delete data."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE agents SET current_status = 'deactivated' WHERE id = %s",
                [agent_id],
            )
            conn.execute(
                """UPDATE triggers SET status = 'cancelled'
                   WHERE agent_id = %s AND status = 'pending'""",
                [agent_id],
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Deactivate agent failed: {e}")


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
    except Exception as e:
        raise RuntimeError(f"Test SMS failed: {e}")


def run_manual_scan(agent_id: str) -> None:
    """Manually run the daily scanner for an agent."""
    try:
        from app.worker.daily_scanner import scan_agent
        from app.services.agent_config import get_agent_by_id
        agent = get_agent_by_id(UUID(agent_id))
        if agent:
            scan_agent(agent)
    except Exception as e:
        logger.error(f"Manual scan failed: {e}")
