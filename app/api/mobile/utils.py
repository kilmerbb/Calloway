"""Mobile API — Shared utility functions."""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)


def get_agent_today_range(timezone_str: str) -> tuple[datetime, datetime]:
    """Compute today's start/end in agent's local timezone, returned as UTC datetimes."""
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        logger.warning("Invalid timezone %s, falling back to America/New_York", timezone_str)
        tz = ZoneInfo("America/New_York")

    now_local = datetime.now(tz)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end_local = today_start_local + timedelta(days=1)

    # Convert to UTC for DB queries
    today_start_utc = today_start_local.astimezone(timezone.utc)
    today_end_utc = today_end_local.astimezone(timezone.utc)

    return today_start_utc, today_end_utc
