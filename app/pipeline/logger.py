"""Conversation and interaction logging.

Note: Most logging is handled inline in the dispatcher (Step 23).
This module provides the log_interaction tool and helper functions.
"""
import logging
from uuid import UUID

from app.db.connection import get_db_connection

import psycopg

logger = logging.getLogger(__name__)


def log_interaction(
    agent_id: UUID,
    contact_id: UUID,
    channel: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    """Log an interaction (tool #16). Used for manual logging."""
    try:
        with get_db_connection() as conn:
            conv = conn.execute(
                """SELECT id FROM conversations
                   WHERE agent_id = %s AND contact_id = %s
                   ORDER BY created_at DESC LIMIT 1""",
                [str(agent_id), str(contact_id)],
            ).fetchone()

            if not conv:
                conv = conn.execute(
                    """INSERT INTO conversations (agent_id, contact_id, channel, last_message_at)
                       VALUES (%s, %s, %s, now()) RETURNING id""",
                    [str(agent_id), str(contact_id), channel],
                ).fetchone()

            conn.execute(
                """INSERT INTO messages (agent_id, conversation_id, sender_type, body)
                   VALUES (%s, %s, 'system', %s)""",
                [str(agent_id), str(conv["id"]), content],
            )
            conn.commit()

        return {"logged": True}
    except psycopg.Error as e:
        logger.error(f"Failed to log interaction: {e}")
        return {"logged": False, "error": str(e)}


def log_tool_execution(
    agent_id: UUID,
    conversation_id: UUID | None,
    tool_name: str,
    input_json: dict,
    output_json: dict | None,
    status: str,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Log a tool execution to the tool_executions table."""
    import json
    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO tool_executions (agent_id, conversation_id, tool_name,
                    input_json, output_json, status, error_message, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    str(agent_id),
                    str(conversation_id) if conversation_id else None,
                    tool_name,
                    json.dumps(input_json),
                    json.dumps(output_json) if output_json else None,
                    status,
                    error_message,
                    latency_ms,
                ],
            )
            conn.commit()
    except psycopg.Error as e:
        logger.error(f"Failed to log tool execution: {e}")
