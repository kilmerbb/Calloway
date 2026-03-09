"""Showing tools — hold, confirm, expire, cancel."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import Showing

logger = logging.getLogger(__name__)

HOLD_DURATION_MINUTES = 30


def create_showing_hold(
    agent_id: UUID, contact_id: UUID, listing_id: UUID, desired_time: datetime
) -> dict:
    """
    Create a showing hold with 30-minute expiry.
    Does NOT create a calendar event yet.
    """
    end_time = desired_time + timedelta(hours=1)
    hold_expires = datetime.now(timezone.utc) + timedelta(minutes=HOLD_DURATION_MINUTES)

    with get_db_connection() as conn:
        row = conn.execute(
            """INSERT INTO showings (agent_id, contact_id, listing_id, start_time, end_time,
                status, hold_expires_at)
               VALUES (%s, %s, %s, %s, %s, 'hold', %s)
               RETURNING *""",
            [str(agent_id), str(contact_id), str(listing_id),
             desired_time, end_time, hold_expires],
        ).fetchone()
        conn.commit()

    showing = Showing(**row)
    logger.info(f"Created showing hold: {showing.id}")
    return {
        "hold_id": str(showing.id),
        "expires_at": hold_expires.isoformat(),
        "status": "hold",
        "start_time": desired_time.isoformat(),
    }


def confirm_showing(hold_id: UUID) -> dict:
    """
    Confirm a showing hold. Creates Google Calendar event.
    CRITICAL: only call this after client confirms.
    """
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM showings WHERE id = %s", [str(hold_id)]
        ).fetchone()

    if not row:
        return {"error": "Showing not found"}

    showing = Showing(**row)

    if showing.status != "hold":
        return {"error": f"Showing is {showing.status}, not hold"}

    # Check if hold expired
    if showing.hold_expires_at:
        expires = showing.hold_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE showings SET status = 'cancelled' WHERE id = %s",
                    [str(hold_id)],
                )
                conn.commit()
            return {"error": "Hold has expired"}

    # Create calendar event (lazy imports to avoid cryptography import at module level)
    from app.services.agent_config import get_agent_by_id
    from app.services.google_service import create_event
    from app.tools.listings import get_listing

    agent = get_agent_by_id(showing.agent_id)
    listing = get_listing(showing.agent_id, listing_id=showing.listing_id)

    location = listing.address if listing else "TBD"
    description = ""
    if listing:
        description = f"Showing: {listing.address}\n"
        if listing.lockbox:
            description += f"Lockbox: {listing.lockbox}\n"
        if listing.showing_instructions:
            description += f"Instructions: {listing.showing_instructions}\n"

    event_result = create_event(
        agent, title=f"Showing: {location}",
        start=showing.start_time, end=showing.end_time,
        location=location, description=description,
    )

    calendar_event_id = event_result.get("event_id")

    # Update showing
    with get_db_connection() as conn:
        conn.execute(
            """UPDATE showings SET status = 'confirmed', calendar_event_id = %s,
               hold_expires_at = NULL WHERE id = %s""",
            [calendar_event_id, str(hold_id)],
        )

        # Increment usage_metrics.showings_booked
        conn.execute(
            """INSERT INTO usage_metrics (agent_id, date, showings_booked)
               VALUES (%s, CURRENT_DATE, 1)
               ON CONFLICT (agent_id, date)
               DO UPDATE SET showings_booked = usage_metrics.showings_booked + 1""",
            [str(showing.agent_id)],
        )
        conn.commit()

    logger.info(f"Confirmed showing: {hold_id}")
    return {
        "status": "confirmed",
        "calendar_event_id": calendar_event_id,
        "start_time": showing.start_time.isoformat(),
        "location": location,
    }


def cancel_showing(showing_id: UUID) -> dict:
    """Cancel a showing."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE showings SET status = 'cancelled' WHERE id = %s",
            [str(showing_id)],
        )
        conn.commit()
    return {"status": "cancelled"}


def expire_stale_holds() -> int:
    """Cancel all holds past their expiry. Called by trigger worker."""
    with get_db_connection() as conn:
        result = conn.execute(
            """UPDATE showings SET status = 'cancelled'
               WHERE status = 'hold'
               AND hold_expires_at IS NOT NULL
               AND hold_expires_at < now()
               RETURNING id""",
        ).fetchall()
        conn.commit()

    count = len(result)
    if count:
        logger.info(f"Expired {count} stale showing holds")
    return count
