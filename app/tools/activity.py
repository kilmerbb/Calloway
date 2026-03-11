"""Activity tools — unified activity feed across conversations, showings, triggers."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)


def get_recent_activity(agent_id: UUID, limit: int = 20) -> list[dict]:
    """Get a unified activity feed combining messages, showings, and triggers."""
    activities = []
    since = datetime.now(timezone.utc) - timedelta(days=7)

    with get_db_connection() as conn:
        # Recent messages
        messages = conn.execute(
            """SELECT m.created_at, m.body, m.sender_type, c.name as contact_name, cv.channel
               FROM messages m
               JOIN conversations cv ON cv.id = m.conversation_id
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.agent_id = %s AND m.created_at > %s
               ORDER BY m.created_at DESC LIMIT %s""",
            [str(agent_id), since, limit],
        ).fetchall()
        for m in messages:
            activities.append({
                "type": "message",
                "timestamp": m["created_at"],
                "description": f"{'Received from' if m['sender_type'] == 'client' else 'Sent to'} {m['contact_name'] or 'Unknown'}",
                "detail": (m["body"] or "")[:100],
                "channel": m["channel"],
            })

        # Recent showings
        showings = conn.execute(
            """SELECT s.start_time, s.status, c.name as contact_name, l.address
               FROM showings s
               JOIN contacts c ON c.id = s.contact_id
               JOIN listings l ON l.id = s.listing_id
               WHERE s.agent_id = %s AND s.created_at > %s
               ORDER BY s.created_at DESC LIMIT %s""",
            [str(agent_id), since, limit],
        ).fetchall()
        for s in showings:
            activities.append({
                "type": "showing",
                "timestamp": s["start_time"],
                "description": f"Showing: {s['contact_name']} at {s['address']}",
                "detail": f"Status: {s['status']}",
                "channel": None,
            })

        # Recent triggers fired
        triggers = conn.execute(
            """SELECT t.created_at, t.trigger_type, t.status, t.message_template,
                      c.name as contact_name
               FROM triggers t
               LEFT JOIN contacts c ON c.id = t.entity_id AND t.entity_type = 'contact'
               WHERE t.agent_id = %s AND t.status = 'fired' AND t.created_at > %s
               ORDER BY t.created_at DESC LIMIT %s""",
            [str(agent_id), since, limit],
        ).fetchall()
        for t in triggers:
            activities.append({
                "type": "trigger",
                "timestamp": t["created_at"],
                "description": f"Trigger fired: {t['trigger_type']}",
                "detail": t["message_template"][:100] if t["message_template"] else "",
                "channel": None,
            })

    # Sort by timestamp descending
    activities.sort(key=lambda x: x["timestamp"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return activities[:limit]


def get_activity_summary(agent_id: UUID) -> dict:
    """Get an activity summary for today."""
    with get_db_connection() as conn:
        messages = conn.execute(
            """SELECT COUNT(*) as cnt FROM messages m
               JOIN conversations cv ON cv.id = m.conversation_id
               WHERE cv.agent_id = %s AND m.created_at >= CURRENT_DATE""",
            [str(agent_id)],
        ).fetchone()

        showings = conn.execute(
            """SELECT COUNT(*) as cnt FROM showings
               WHERE agent_id = %s AND start_time::date = CURRENT_DATE""",
            [str(agent_id)],
        ).fetchone()

        triggers = conn.execute(
            """SELECT COUNT(*) as cnt FROM triggers
               WHERE agent_id = %s AND status = 'fired'
               AND created_at >= CURRENT_DATE""",
            [str(agent_id)],
        ).fetchone()

    return {
        "messages_today": messages["cnt"] if messages else 0,
        "showings_today": showings["cnt"] if showings else 0,
        "triggers_fired_today": triggers["cnt"] if triggers else 0,
    }
