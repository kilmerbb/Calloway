"""Trigger tools — create, get, cascade creation."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import Trigger

logger = logging.getLogger(__name__)


def create_trigger(
    agent_id: UUID,
    entity_type: str,
    entity_id: UUID,
    trigger_type: str,
    scheduled_at: datetime,
    action_type: str,
    recurrence: str | None = None,
    message_template: str | None = None,
    autonomy_level: str = "ask_agent",
    notes: str | None = None,
) -> Trigger:
    """Create a trigger, checking for duplicates first."""
    # Deduplication check
    with get_db_connection() as conn:
        existing = conn.execute(
            """SELECT id FROM triggers
               WHERE agent_id = %s AND entity_id = %s AND trigger_type = %s
               AND DATE(scheduled_at) = DATE(%s) AND status = 'pending'""",
            [str(agent_id), str(entity_id), trigger_type, scheduled_at],
        ).fetchone()

        if existing:
            logger.info(f"Duplicate trigger skipped: {trigger_type} for {entity_id}")
            row = conn.execute(
                "SELECT * FROM triggers WHERE id = %s", [str(existing["id"])]
            ).fetchone()
            return Trigger(**row)

        row = conn.execute(
            """INSERT INTO triggers (agent_id, entity_type, entity_id, trigger_type,
                scheduled_at, action_type, recurrence, message_template,
                autonomy_level, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            [str(agent_id), entity_type, str(entity_id), trigger_type,
             scheduled_at, action_type, recurrence, message_template,
             autonomy_level, notes],
        ).fetchone()
        conn.commit()

    return Trigger(**row)


def get_triggers(
    agent_id: UUID,
    contact_id: UUID | None = None,
    listing_id: UUID | None = None,
    date_range: tuple | None = None,
    status: str = "pending",
) -> list[Trigger]:
    """Get triggers with optional filters."""
    conditions = ["agent_id = %s", "status = %s"]
    params: list = [str(agent_id), status]

    if contact_id:
        conditions.append("entity_id = %s")
        params.append(str(contact_id))

    if listing_id:
        conditions.append("entity_id = %s")
        params.append(str(listing_id))

    if date_range:
        conditions.append("scheduled_at BETWEEN %s AND %s")
        params.extend([date_range[0], date_range[1]])

    where = " AND ".join(conditions)

    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM triggers WHERE {where} ORDER BY scheduled_at LIMIT 50",
            params,
        ).fetchall()

    return [Trigger(**r) for r in rows]


def create_trigger_cascade(
    agent_id: UUID,
    cascade_type: str,
    entity_id: UUID,
    base_date: datetime,
    params: dict | None = None,
) -> list[Trigger]:
    """Create multiple triggers from a single command."""
    triggers = []

    if cascade_type == "transaction_deadlines":
        # From one deadline date → 4 triggers per deadline
        deadlines = params.get("deadlines", {}) if params else {}

        for name, date_str in deadlines.items():
            try:
                deadline = datetime.fromisoformat(date_str) if isinstance(date_str, str) else date_str
            except (ValueError, TypeError):
                continue

            # 3 days before
            triggers.append(create_trigger(
                agent_id, "contact", entity_id, "deadline",
                deadline - timedelta(days=3), "both",
                message_template=f"{name} deadline is in 3 days.",
                autonomy_level="auto",
            ))
            # 1 day before
            triggers.append(create_trigger(
                agent_id, "contact", entity_id, "deadline",
                deadline - timedelta(days=1), "both",
                message_template=f"{name} deadline is tomorrow.",
                autonomy_level="auto",
            ))
            # Day of
            triggers.append(create_trigger(
                agent_id, "contact", entity_id, "deadline",
                deadline, "notify_agent",
                message_template=f"{name} deadline is today.",
                autonomy_level="auto",
            ))
            # Day after
            triggers.append(create_trigger(
                agent_id, "contact", entity_id, "deadline",
                deadline + timedelta(days=1), "notify_agent",
                message_template=f"{name} deadline was yesterday. Confirm completion.",
                autonomy_level="ask_agent",
            ))

    elif cascade_type == "open_house":
        listing_id = entity_id
        # 2 days before: promote
        triggers.append(create_trigger(
            agent_id, "listing", listing_id, "open_house",
            base_date - timedelta(days=2), "send_message",
            message_template="open_house_promotion",
            autonomy_level="auto",
            notes="Promote to matching buyers",
        ))
        # Morning of: reminders
        morning = base_date.replace(hour=8, minute=0)
        triggers.append(create_trigger(
            agent_id, "listing", listing_id, "reminder",
            morning, "send_message",
            message_template="open_house_reminder",
            autonomy_level="auto",
        ))
        # Day after: request attendee list
        triggers.append(create_trigger(
            agent_id, "listing", listing_id, "open_house",
            base_date + timedelta(days=1), "notify_agent",
            message_template="Send attendee names and numbers",
            autonomy_level="ask_agent",
        ))
        # 2 days after: follow up attendees
        triggers.append(create_trigger(
            agent_id, "listing", listing_id, "follow_up",
            base_date + timedelta(days=2), "send_message",
            message_template="open_house_follow_up",
            autonomy_level="auto",
        ))
        # 3 days after: report to seller
        triggers.append(create_trigger(
            agent_id, "listing", listing_id, "seller_report",
            base_date + timedelta(days=3), "compile_report",
            autonomy_level="auto",
        ))

    elif cascade_type == "post_close":
        contact_id = entity_id
        # Day 7: review request
        triggers.append(create_trigger(
            agent_id, "contact", contact_id, "review_request",
            base_date + timedelta(days=7), "send_message",
            message_template="review_request",
            autonomy_level="auto",
        ))
        # Day 30: check-in
        triggers.append(create_trigger(
            agent_id, "contact", contact_id, "post_close",
            base_date + timedelta(days=30), "send_message",
            message_template="How's the new place? Need contractor recommendations?",
            autonomy_level="auto",
        ))
        # 6 months: homeversary
        triggers.append(create_trigger(
            agent_id, "contact", contact_id, "anniversary",
            base_date + timedelta(days=180), "send_message",
            message_template="Happy 6-month homeversary!",
            autonomy_level="auto",
        ))
        # 1 year: anniversary
        triggers.append(create_trigger(
            agent_id, "contact", contact_id, "anniversary",
            base_date + timedelta(days=365), "send_message",
            message_template="Happy first homeversary!",
            autonomy_level="auto",
            recurrence="annually",
        ))
        # 2 years: recurring
        triggers.append(create_trigger(
            agent_id, "contact", contact_id, "anniversary",
            base_date + timedelta(days=730), "send_message",
            message_template="Happy homeversary! Here's a neighborhood market update.",
            autonomy_level="auto",
            recurrence="annually",
        ))

    return triggers
