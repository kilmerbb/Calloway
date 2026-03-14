"""Google Calendar + Contacts wrapper."""
import json
import logging
from datetime import datetime, timedelta, timezone, date, time
from uuid import UUID

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.db.connection import get_db_connection
from app.models.schemas import AgentConfig

logger = logging.getLogger(__name__)


def get_oauth_credentials(agent: AgentConfig) -> Credentials | None:
    """Load and refresh Google OAuth credentials for an agent."""
    if not agent.google_oauth:
        return None

    try:
        creds = Credentials(
            token=agent.google_oauth.get("access_token"),
            refresh_token=agent.google_oauth.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=agent.google_oauth.get("client_id", ""),
            client_secret=agent.google_oauth.get("client_secret", ""),
        )

        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            # Update stored tokens
            with get_db_connection() as conn:
                conn.execute(
                    """UPDATE agents SET google_oauth = google_oauth || %s WHERE id = %s""",
                    [json.dumps({"access_token": creds.token}), str(agent.id)],
                )
                conn.commit()

        return creds
    except Exception as e:  # Broad catch: Google OAuth refresh + DB update
        logger.error(f"Failed to get Google credentials: {e}")
        return None


def check_availability(
    agent: AgentConfig, target_date: date
) -> dict:
    """
    Check agent's calendar availability for a given date.
    Returns {date, available_slots, busy_slots}.
    """
    creds = get_oauth_credentials(agent)
    if not creds:
        # Return default available slots from scheduling_prefs
        return _default_availability(agent, target_date)

    try:
        service = build("calendar", "v3", credentials=creds)

        # Build time range for the day
        start = datetime.combine(target_date, time(0, 0), tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "items": [{"id": "primary"}],
        }

        result = service.freebusy().query(body=body).execute()
        busy_slots = result.get("calendars", {}).get("primary", {}).get("busy", [])

        # Parse showing hours from agent prefs
        showing_hours = agent.scheduling_prefs.get("showing_hours", "Mon-Sat 9am-5pm")
        buffer_mins = agent.scheduling_prefs.get("buffer_mins", 30)

        available = _calculate_available_slots(
            target_date, busy_slots, showing_hours, buffer_mins
        )

        return {
            "date": str(target_date),
            "available_slots": available,
            "busy_slots": busy_slots,
        }

    except Exception as e:  # Broad catch: Google Calendar API errors
        logger.error(f"Calendar check failed: {e}")
        return _default_availability(agent, target_date)


def create_event(
    agent: AgentConfig,
    title: str,
    start: datetime,
    end: datetime,
    location: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a Google Calendar event."""
    creds = get_oauth_credentials(agent)
    if not creds:
        return {"event_id": f"mock_{start.isoformat()}", "status": "created_offline"}

    try:
        service = build("calendar", "v3", credentials=creds)

        event_body = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": agent.timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": agent.timezone},
        }
        if location:
            event_body["location"] = location
        if description:
            event_body["description"] = description

        event = service.events().insert(calendarId="primary", body=event_body).execute()
        return {"event_id": event.get("id"), "status": "created"}

    except Exception as e:  # Broad catch: Google Calendar API errors
        logger.error(f"Failed to create calendar event: {e}")
        return {"event_id": None, "status": "error", "error": str(e)}


def _default_availability(agent: AgentConfig, target_date: date) -> dict:
    """Generate default availability from agent preferences."""
    buffer = agent.scheduling_prefs.get("buffer_mins", 30)
    days_off = agent.scheduling_prefs.get("days_off", ["Sun", "Mon"])

    day_name = target_date.strftime("%a")
    if day_name in days_off:
        return {"date": str(target_date), "available_slots": [], "busy_slots": []}

    # Default 9am-5pm with buffer between slots
    slots = []
    hour = 9
    while hour < 17:
        slot_start = datetime.combine(target_date, time(hour, 0))
        slot_end = slot_start + timedelta(hours=1)
        slots.append({
            "start": slot_start.isoformat(),
            "end": slot_end.isoformat(),
        })
        hour += 1

    return {"date": str(target_date), "available_slots": slots, "busy_slots": []}


def _calculate_available_slots(
    target_date: date,
    busy_slots: list[dict],
    showing_hours: str,
    buffer_mins: int,
) -> list[dict]:
    """Calculate available time slots given busy periods."""
    # Simple: generate hourly slots between 9-5, remove busy ones
    slots = []
    for hour in range(9, 17):
        slot_start = datetime.combine(target_date, time(hour, 0), tzinfo=timezone.utc)
        slot_end = slot_start + timedelta(hours=1)

        is_busy = False
        for busy in busy_slots:
            busy_start = datetime.fromisoformat(busy["start"].replace("Z", "+00:00"))
            busy_end = datetime.fromisoformat(busy["end"].replace("Z", "+00:00"))
            # Add buffer
            busy_start -= timedelta(minutes=buffer_mins)
            busy_end += timedelta(minutes=buffer_mins)

            if slot_start < busy_end and slot_end > busy_start:
                is_busy = True
                break

        if not is_busy:
            slots.append({
                "start": slot_start.isoformat(),
                "end": slot_end.isoformat(),
            })

    return slots
