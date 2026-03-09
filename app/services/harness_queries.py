"""Harness query layer — trace storage, retrieval, and comparison."""
import json
import logging
from uuid import UUID

from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)

MAX_TRACES = 1000


def store_trace(trace, sender_phone: str, message_body: str) -> None:
    """Store a pipeline trace in the harness_traces table."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO harness_traces
                   (id, trace_json, agent_id, sender_phone, message_body,
                    intent_detected, model_used, total_duration_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    str(trace.trace_id),
                    json.dumps(trace.model_dump(mode="json"), default=str),
                    str(trace.agent_id),
                    sender_phone,
                    message_body,
                    trace.intent_detected,
                    trace.model_used,
                    trace.total_duration_ms,
                ],
            )
            # Enforce retention limit
            conn.execute(
                """DELETE FROM harness_traces
                   WHERE id IN (
                       SELECT id FROM harness_traces
                       ORDER BY created_at DESC
                       OFFSET %s
                   )""",
                [MAX_TRACES],
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to store trace: {e}")


def get_trace_history(
    agent_id: str | None = None,
    intent: str | None = None,
    model: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Get stored traces with optional filtering."""
    try:
        conditions = []
        params = []

        if agent_id:
            conditions.append("agent_id = %s")
            params.append(agent_id)
        if intent:
            conditions.append("intent_detected = %s")
            params.append(intent)
        if model:
            conditions.append("model_used = %s")
            params.append(model)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        with get_db_connection() as conn:
            rows = conn.execute(
                f"""SELECT id, agent_id, sender_phone, message_body,
                           intent_detected, model_used, total_duration_ms, created_at
                    FROM harness_traces
                    {where}
                    ORDER BY created_at DESC LIMIT %s""",
                params + [limit],
            ).fetchall()
        return rows or []
    except Exception as e:
        logger.error(f"Trace history query failed: {e}")
        return []


def get_trace_by_id(trace_id: str) -> dict | None:
    """Get a full trace by ID."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM harness_traces WHERE id = %s",
                [trace_id],
            ).fetchone()
        if row and row.get("trace_json"):
            if isinstance(row["trace_json"], str):
                row["trace_json"] = json.loads(row["trace_json"])
        return row
    except Exception as e:
        logger.error(f"Trace lookup failed: {e}")
        return None
