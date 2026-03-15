"""Trigger worker — fires due triggers every 60 seconds."""
import logging
import time
from datetime import datetime, timezone, timedelta
from uuid import UUID

from dateutil.relativedelta import relativedelta

import psycopg

from app.db.connection import get_db_connection
from app.models.schemas import Trigger

logger = logging.getLogger(__name__)

import os

POLL_INTERVAL = int(os.environ.get("TRIGGER_POLL_INTERVAL", "60"))


def run_trigger_worker():
    """Main loop: poll for due triggers every 60 seconds.

    Kept for backward compatibility (single-process mode).
    For the separated worker, use ``run_trigger_worker_once`` instead.
    """
    logger.info("Trigger worker started")
    while True:
        run_trigger_worker_once()
        time.sleep(POLL_INTERVAL)


def run_trigger_worker_once():
    """Execute a single trigger-processing cycle (no sleep)."""
    fired = process_due_triggers()
    from app.tools.showings import expire_stale_holds
    expired = expire_stale_holds()
    reverted = revert_expired_statuses()
    if fired or expired or reverted:
        logger.info(
            f"Trigger cycle: {fired} fired, {expired} holds expired, "
            f"{reverted} statuses reverted"
        )


def process_due_triggers() -> int:
    """Find and fire all pending triggers that are due.

    Uses SELECT ... FOR UPDATE SKIP LOCKED to prevent double-firing when
    multiple worker instances run concurrently (C-1 fix). Each trigger is
    atomically claimed by setting status = 'in_progress' before processing.
    """
    now = datetime.now(timezone.utc)
    fired = 0

    # Claim triggers atomically: lock rows and mark in_progress in one transaction.
    # SKIP LOCKED ensures concurrent workers don't block each other or grab the same rows.
    with get_db_connection() as conn:
        rows = conn.execute(
            """UPDATE triggers
               SET status = 'in_progress'
               WHERE id IN (
                   SELECT id FROM triggers
                   WHERE (
                       (status = 'pending' AND autonomy_level != 'ask_agent' AND scheduled_at <= %s)
                       OR
                       (status = 'approved' AND scheduled_at <= %s)
                   )
                   ORDER BY scheduled_at
                   LIMIT 50
                   FOR UPDATE SKIP LOCKED
               )
               RETURNING *""",
            [now, now],
        ).fetchall()
        conn.commit()

    for row in rows:
        trigger = Trigger(**row)
        try:
            _fire_trigger(trigger)
            fired += 1
        except Exception as e:  # Broad catch: worker loop must survive transient errors
            logger.error(f"Failed to fire trigger {trigger.id}: {e}")
            _mark_trigger(trigger.id, "failed")

    return fired


def _fire_trigger(trigger: Trigger) -> None:
    """Execute a single trigger based on its action_type."""
    logger.info(
        f"Firing trigger {trigger.id}: {trigger.trigger_type} "
        f"({trigger.action_type}) for {trigger.entity_type}/{trigger.entity_id}"
    )

    if trigger.action_type == "notify_agent":
        _notify_agent(trigger)
    elif trigger.action_type == "send_message":
        _send_trigger_message(trigger)
    elif trigger.action_type == "both":
        _send_trigger_message(trigger)
        _notify_agent(trigger)
    elif trigger.action_type == "compile_report":
        _compile_report(trigger)
    else:
        logger.warning(f"Unknown action_type: {trigger.action_type}")

    # Mark as fired
    _mark_trigger(trigger.id, "fired")

    # Handle recurrence
    if trigger.recurrence:
        _create_next_recurrence(trigger)

    # Update usage metrics
    _increment_triggers_fired(trigger.agent_id)


def _notify_agent(trigger: Trigger) -> None:
    """Send a push notification to the agent."""
    try:
        from app.services.firebase_service import send_push_notification

        title = f"Trigger: {trigger.trigger_type}"
        body = trigger.message_template or f"{trigger.trigger_type} for {trigger.entity_type}"

        tier = "action_needed"
        if trigger.autonomy_level == "ask_agent":
            tier = "action_needed"
        elif trigger.trigger_type in ("deadline",):
            tier = "urgent"

        send_push_notification(
            agent_id=trigger.agent_id,
            tier=tier,
            title=title,
            body=body,
            contact_id=trigger.entity_id if trigger.entity_type == "contact" else None,
            listing_id=trigger.entity_id if trigger.entity_type == "listing" else None,
        )
    except Exception as e:  # Broad catch: Firebase SDK errors
        logger.error(f"Failed to notify agent for trigger {trigger.id}: {e}")


def _send_trigger_message(trigger: Trigger) -> None:
    """Send a message to the contact/listing entity."""
    if trigger.entity_type != "contact":
        logger.info(f"Skipping message for non-contact entity: {trigger.entity_type}")
        return

    try:
        from app.tools.contacts import lookup_contact
        from app.services.agent_config import get_agent_by_id
        from app.services.twilio_service import send_client_message

        agent = get_agent_by_id(trigger.agent_id)
        if not agent:
            logger.error(f"Agent {trigger.agent_id} not found for trigger {trigger.id}")
            return

        # Look up contact
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM contacts WHERE id = %s",
                [str(trigger.entity_id)],
            ).fetchone()

        if not row:
            logger.error(f"Contact {trigger.entity_id} not found for trigger {trigger.id}")
            return

        message = trigger.message_template or f"Reminder from {agent.name}"

        if trigger.autonomy_level == "auto":
            # Send directly
            send_client_message(
                agent_id=trigger.agent_id,
                contact_id=trigger.entity_id,
                message=message,
                from_number=agent.twilio_number,
                to_number=row["phone"],
            )
            logger.info(f"Sent trigger message to {row['name']}: {message[:50]}")
        else:
            # Just notify the agent with the suggested message
            _notify_agent(trigger)

    except Exception as e:  # Broad catch: mixed DB + Twilio call
        logger.error(f"Failed to send trigger message for {trigger.id}: {e}")


def _compile_report(trigger: Trigger) -> None:
    """Compile and send a report. Delegates to specific report builders."""
    logger.info(f"Report compilation triggered: {trigger.trigger_type} for {trigger.entity_id}")
    # Report compilation is expanded in Step 34 (seller_report)
    _notify_agent(trigger)


def _mark_trigger(trigger_id: UUID, status: str) -> None:
    """Update trigger status."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE triggers SET status = %s WHERE id = %s",
            [status, str(trigger_id)],
        )
        conn.commit()


def _create_next_recurrence(trigger: Trigger) -> None:
    """Create the next occurrence for a recurring trigger."""
    if trigger.recurrence == "annually":
        next_at = trigger.scheduled_at + relativedelta(years=1)
    elif trigger.recurrence == "monthly":
        next_at = trigger.scheduled_at + relativedelta(months=1)
    elif trigger.recurrence == "weekly":
        next_at = trigger.scheduled_at + timedelta(days=7)
    elif trigger.recurrence == "daily":
        next_at = trigger.scheduled_at + timedelta(days=1)
    else:
        logger.warning(f"Unknown recurrence: {trigger.recurrence}")
        return

    with get_db_connection() as conn:
        conn.execute(
            """INSERT INTO triggers (agent_id, entity_type, entity_id, trigger_type,
                scheduled_at, action_type, recurrence, message_template,
                autonomy_level, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                str(trigger.agent_id), trigger.entity_type,
                str(trigger.entity_id), trigger.trigger_type,
                next_at, trigger.action_type, trigger.recurrence,
                trigger.message_template, trigger.autonomy_level, trigger.notes,
            ],
        )
        conn.commit()

    logger.info(f"Created next recurrence for trigger {trigger.id}: {next_at}")


def _increment_triggers_fired(agent_id: UUID) -> None:
    """Increment the triggers_fired counter in usage_metrics."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO usage_metrics (agent_id, date, triggers_fired)
                   VALUES (%s, CURRENT_DATE, 1)
                   ON CONFLICT (agent_id, date)
                   DO UPDATE SET triggers_fired = usage_metrics.triggers_fired + 1""",
                [str(agent_id)],
            )
            conn.commit()
    except psycopg.Error as e:
        logger.error(f"Failed to update triggers_fired metric: {e}")


def revert_expired_statuses() -> int:
    """Revert agents whose status_until has passed."""
    now = datetime.now(timezone.utc)
    with get_db_connection() as conn:
        result = conn.execute(
            """UPDATE agents SET current_status = 'available', status_until = NULL
               WHERE status_until IS NOT NULL AND status_until < %s
               RETURNING id""",
            [now],
        ).fetchall()
        conn.commit()

    count = len(result)
    if count:
        logger.info(f"Reverted {count} agent(s) to available status")
    return count
