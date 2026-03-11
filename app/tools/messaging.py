"""Messaging tools — message history, search, and metrics."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)


def get_conversation_history(
    agent_id: UUID,
    contact_id: UUID,
    limit: int = 20,
) -> list[dict]:
    """Get recent conversation messages for a contact."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT m.*, c.name as contact_name
               FROM messages m
               JOIN conversations cv ON cv.id = m.conversation_id
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.agent_id = %s AND cv.contact_id = %s
               ORDER BY m.created_at DESC
               LIMIT %s""",
            [str(agent_id), str(contact_id), limit],
        ).fetchall()
    return [dict(r) for r in rows]


def get_unread_count(agent_id: UUID) -> int:
    """Count messages received today that the agent hasn't responded to."""
    with get_db_connection() as conn:
        result = conn.execute(
            """SELECT COUNT(DISTINCT cv.id) as cnt
               FROM conversations cv
               JOIN messages m ON m.conversation_id = cv.id
               WHERE cv.agent_id = %s
               AND m.sender_type = 'client'
               AND m.created_at >= CURRENT_DATE
               AND cv.id NOT IN (
                   SELECT conversation_id FROM messages
                   WHERE sender_type = 'ai' AND created_at >= CURRENT_DATE
               )""",
            [str(agent_id)],
        ).fetchone()
    return result["cnt"] if result else 0


def search_messages(
    agent_id: UUID,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """Search message bodies for a query string."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT m.*, cv.contact_id, c.name as contact_name
               FROM messages m
               JOIN conversations cv ON cv.id = m.conversation_id
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.agent_id = %s
               AND m.body ILIKE %s
               ORDER BY m.created_at DESC
               LIMIT %s""",
            [str(agent_id), f"%{query}%", limit],
        ).fetchall()
    return [dict(r) for r in rows]


def get_message_stats(agent_id: UUID, days: int = 7) -> dict:
    """Get message statistics for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with get_db_connection() as conn:
        result = conn.execute(
            """SELECT
                COUNT(*) FILTER (WHERE sender_type = 'client') as received,
                COUNT(*) FILTER (WHERE sender_type = 'ai') as sent,
                COUNT(*) FILTER (WHERE ai_generated = true) as ai_generated,
                COUNT(*) FILTER (WHERE delivery_status = 'delivered') as delivered,
                COUNT(*) FILTER (WHERE delivery_status = 'failed') as failed
               FROM messages m
               JOIN conversations cv ON cv.id = m.conversation_id
               WHERE cv.agent_id = %s AND m.created_at > %s""",
            [str(agent_id), since],
        ).fetchone()
    return dict(result) if result else {
        "received": 0, "sent": 0, "ai_generated": 0, "delivered": 0, "failed": 0,
    }
