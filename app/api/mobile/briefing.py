"""Mobile API — Daily briefing and schedule endpoints."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.connection import get_async_db_connection
from .deps import get_current_agent
from .utils import get_agent_today_range

logger = logging.getLogger(__name__)

briefing_router = APIRouter(prefix="/api/v1/mobile/briefing", tags=["mobile-briefing"])
schedule_router = APIRouter(prefix="/api/v1/mobile/schedule", tags=["mobile-schedule"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ShowingSummary(BaseModel):
    id: str
    start_time: datetime
    end_time: datetime | None
    status: str
    contact_name: str | None
    listing_address: str | None


class ApprovalSummary(BaseModel):
    trigger_id: str
    trigger_type: str
    message_template: str | None
    scheduled_at: datetime | None
    contact_name: str | None


class FollowUpSummary(BaseModel):
    trigger_id: str
    trigger_type: str
    scheduled_at: datetime | None
    message_template: str | None
    contact_name: str | None


class LeadSummary(BaseModel):
    id: str
    name: str | None
    phone: str | None
    lead_source: str | None


class BriefingResponse(BaseModel):
    date: str
    timezone: str
    generated_at: datetime
    showings_today: list[ShowingSummary]
    pending_approvals: list[ApprovalSummary]
    follow_ups_due: list[FollowUpSummary]
    new_leads_since_yesterday: list[LeadSummary]
    messages_received_today: int
    active_transaction_count: int


class ScheduleEvent(BaseModel):
    type: str = "showing"
    id: str
    start_time: datetime
    end_time: datetime | None
    status: str
    contact_name: str | None
    contact_id: str | None
    listing_address: str | None
    listing_id: str | None


class ScheduleResponse(BaseModel):
    date: str
    timezone: str
    events: list[ScheduleEvent]


# ---------------------------------------------------------------------------
# Helpers — each acquires its own DB connection for asyncio.gather parallelism.
# Using separate connections allows all 6 briefing queries to run concurrently,
# reducing latency from sum-of-all to max-of-slowest.
# ---------------------------------------------------------------------------

async def _fetch_showings_today(agent_id: str, today_start: datetime, today_end: datetime) -> list[dict]:
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            """SELECT s.id, s.start_time, s.end_time, s.status,
                      c.name as contact_name, l.address as listing_address
               FROM showings s
               JOIN contacts c ON c.id = s.contact_id
               JOIN listings l ON l.id = s.listing_id
               WHERE s.agent_id = %s
                 AND s.start_time >= %s AND s.start_time < %s
                 AND s.status IN ('confirmed', 'hold')
               ORDER BY s.start_time""",
            [agent_id, today_start, today_end],
        )
        return await result.fetchall()


async def _fetch_pending_approvals(agent_id: str) -> list[dict]:
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            """SELECT t.id as trigger_id, t.trigger_type, t.message_template, t.scheduled_at,
                      c.name as contact_name
               FROM triggers t
               LEFT JOIN contacts c ON c.id = t.entity_id AND t.entity_type = 'contact'
               WHERE t.agent_id = %s
                 AND t.status = 'pending'
                 AND t.autonomy_level = 'ask_agent'
               ORDER BY t.scheduled_at
               LIMIT 100""",
            [agent_id],
        )
        return await result.fetchall()


async def _fetch_follow_ups_due(agent_id: str, today_start: datetime, today_end: datetime) -> list[dict]:
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            """SELECT t.id as trigger_id, t.trigger_type, t.scheduled_at, t.message_template,
                      c.name as contact_name
               FROM triggers t
               LEFT JOIN contacts c ON c.id = t.entity_id AND t.entity_type = 'contact'
               WHERE t.agent_id = %s
                 AND t.scheduled_at >= %s AND t.scheduled_at < %s
                 AND t.status = 'pending'
                 AND t.trigger_type IN ('gap_follow_up', 'proactive_follow_up')
               ORDER BY t.scheduled_at""",
            [agent_id, today_start, today_end],
        )
        return await result.fetchall()


async def _fetch_new_leads(agent_id: str, yesterday_start: datetime) -> list[dict]:
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            """SELECT id, name, phone, lead_source
               FROM contacts
               WHERE agent_id = %s AND created_at >= %s
               ORDER BY created_at DESC
               LIMIT 50""",
            [agent_id, yesterday_start],
        )
        return await result.fetchall()


async def _fetch_messages_received_today(agent_id: str, today_start: datetime) -> int:
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            """SELECT COUNT(*) as cnt
               FROM messages
               WHERE agent_id = %s AND created_at >= %s AND sender_type = 'contact'""",
            [agent_id, today_start],
        )
        row = await result.fetchone()
        return row["cnt"] if row else 0


async def _fetch_active_transaction_count(agent_id: str) -> int:
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            """SELECT COUNT(*) as cnt
               FROM transactions
               WHERE agent_id = %s
                 AND status NOT IN ('closed', 'withdrawn', 'expired', 'fell_through')""",
            [agent_id],
        )
        row = await result.fetchone()
        return row["cnt"] if row else 0


async def _get_agent_timezone(agent_id: str) -> str:
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            "SELECT timezone FROM agents WHERE id = %s",
            [agent_id],
        )
        row = await result.fetchone()
        if not row or not row.get("timezone"):
            return "America/New_York"
        return row["timezone"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@briefing_router.get("/today", response_model=BriefingResponse)
async def get_briefing_today(agent_id: str = Depends(get_current_agent)):
    """Return today's briefing for the authenticated agent."""
    timezone_str = await _get_agent_timezone(agent_id)
    today_start, today_end = get_agent_today_range(timezone_str)
    yesterday_start = today_start - timedelta(days=1)

    (
        showings,
        approvals,
        follow_ups,
        new_leads,
        msg_count,
        txn_count,
    ) = await asyncio.gather(
        _fetch_showings_today(agent_id, today_start, today_end),
        _fetch_pending_approvals(agent_id),
        _fetch_follow_ups_due(agent_id, today_start, today_end),
        _fetch_new_leads(agent_id, yesterday_start),
        _fetch_messages_received_today(agent_id, today_start),
        _fetch_active_transaction_count(agent_id),
    )

    now_utc = datetime.now(timezone.utc)
    try:
        agent_date = datetime.now(ZoneInfo(timezone_str)).strftime("%Y-%m-%d")
    except Exception:
        agent_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

    return BriefingResponse(
        date=agent_date,
        timezone=timezone_str,
        generated_at=now_utc,
        showings_today=[
            ShowingSummary(
                id=str(s["id"]),
                start_time=s["start_time"],
                end_time=s.get("end_time"),
                status=s["status"],
                contact_name=s.get("contact_name"),
                listing_address=s.get("listing_address"),
            )
            for s in showings
        ],
        pending_approvals=[
            ApprovalSummary(
                trigger_id=str(a["trigger_id"]),
                trigger_type=a["trigger_type"],
                message_template=a.get("message_template"),
                scheduled_at=a.get("scheduled_at"),
                contact_name=a.get("contact_name"),
            )
            for a in approvals
        ],
        follow_ups_due=[
            FollowUpSummary(
                trigger_id=str(f["trigger_id"]),
                trigger_type=f["trigger_type"],
                scheduled_at=f.get("scheduled_at"),
                message_template=f.get("message_template"),
                contact_name=f.get("contact_name"),
            )
            for f in follow_ups
        ],
        new_leads_since_yesterday=[
            LeadSummary(
                id=str(lead["id"]),
                name=lead.get("name"),
                phone=lead.get("phone"),
                lead_source=lead.get("lead_source"),
            )
            for lead in new_leads
        ],
        messages_received_today=msg_count,
        active_transaction_count=txn_count,
    )


@schedule_router.get("/today", response_model=ScheduleResponse)
async def get_schedule_today(agent_id: str = Depends(get_current_agent)):
    """Return today's schedule (showings) for the authenticated agent."""
    timezone_str = await _get_agent_timezone(agent_id)
    today_start, today_end = get_agent_today_range(timezone_str)

    async with get_async_db_connection() as conn:
        result = await conn.execute(
            """SELECT s.id, s.start_time, s.end_time, s.status,
                      c.name as contact_name, c.id as contact_id,
                      l.address as listing_address, l.id as listing_id
               FROM showings s
               JOIN contacts c ON s.contact_id = c.id
               JOIN listings l ON s.listing_id = l.id
               WHERE s.agent_id = %s
                 AND s.start_time >= %s AND s.start_time < %s
                 AND s.status NOT IN ('cancelled')
               ORDER BY s.start_time""",
            [agent_id, today_start, today_end],
        )
        rows = await result.fetchall()

    try:
        agent_date = datetime.now(ZoneInfo(timezone_str)).strftime("%Y-%m-%d")
    except Exception:
        agent_date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

    return ScheduleResponse(
        date=agent_date,
        timezone=timezone_str,
        events=[
            ScheduleEvent(
                type="showing",
                id=str(r["id"]),
                start_time=r["start_time"],
                end_time=r.get("end_time"),
                status=r["status"],
                contact_name=r.get("contact_name"),
                contact_id=str(r["contact_id"]) if r.get("contact_id") else None,
                listing_address=r.get("listing_address"),
                listing_id=str(r["listing_id"]) if r.get("listing_id") else None,
            )
            for r in rows
        ],
    )
