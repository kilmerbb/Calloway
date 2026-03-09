"""Calendar tools wrapping Google Calendar service for LLM tool use."""
from datetime import date, datetime, timedelta
from uuid import UUID

from app.models.schemas import AgentConfig
from app.services.google_service import check_availability, create_event
from app.services.agent_config import get_agent_by_id


def check_calendar(agent_id: UUID, target_date: date, time_range: str | None = None) -> dict:
    """Check calendar availability. LLM-callable tool."""
    agent = get_agent_by_id(agent_id)
    if not agent:
        return {"error": "Agent not found"}
    return check_availability(agent, target_date)


def create_calendar_event(
    agent_id: UUID,
    title: str,
    start: datetime,
    end: datetime,
    location: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a calendar event. LLM-callable tool."""
    agent = get_agent_by_id(agent_id)
    if not agent:
        return {"error": "Agent not found"}
    return create_event(agent, title, start, end, location, description)
