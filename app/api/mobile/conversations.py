"""Mobile API — Conversation endpoints."""

import logging
import math
from datetime import datetime, timezone, timedelta

import nh3
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.db.connection import get_async_db_connection
from .deps import get_current_agent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/mobile/conversations", tags=["mobile-conversations"]
)

VALID_STAGES = {"open", "closed", "snoozed"}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int


class ConversationItem(BaseModel):
    id: str
    contact_id: str
    channel: str | None
    stage: str | None
    last_message_at: datetime | None
    contact_name: str | None
    contact_phone: str | None
    last_message_body: str | None
    unread_count: int
    has_pending_draft: bool


class ConversationListResponse(BaseModel):
    data: list[ConversationItem]
    pagination: PaginationMeta


class MessageItem(BaseModel):
    id: str
    sender_type: str | None
    body: str | None
    ai_generated: bool | None
    delivery_status: str | None
    failure_reason: str | None
    created_at: datetime | None


class MessageListResponse(BaseModel):
    data: list[MessageItem]
    pagination: PaginationMeta


class TriggerApproveResponse(BaseModel):
    status: str
    trigger_id: str
    message_preview: str | None


class TriggerEditRequest(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def body_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("body must not be empty")
        if len(v) > 1600:
            raise ValueError("body must not exceed 1600 characters")
        return v


class TriggerEditResponse(BaseModel):
    status: str
    trigger_id: str
    body: str


class TriggerRejectResponse(BaseModel):
    status: str
    trigger_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_trigger_for_agent(trigger_id: str, agent_id: str) -> dict:
    """Fetch a trigger and verify ownership + pending status.

    Raises HTTPException on any validation failure.
    """
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            """SELECT id, agent_id, status, autonomy_level, scheduled_at,
                      message_template
               FROM triggers WHERE id = %s::uuid""",
            [trigger_id],
        )
        trigger = await result.fetchone()

    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    if str(trigger["agent_id"]) != agent_id:
        raise HTTPException(status_code=404, detail="Trigger not found")

    if trigger["status"] != "pending":
        raise HTTPException(
            status_code=409, detail="Trigger is no longer pending"
        )

    if trigger["autonomy_level"] != "ask_agent":
        raise HTTPException(
            status_code=422, detail="Trigger is not an ask_agent type"
        )

    return trigger


def _check_trigger_expiry(trigger: dict) -> None:
    """Raise 410 if trigger scheduled_at is older than 24 hours."""
    scheduled_at = trigger["scheduled_at"]
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    if scheduled_at < cutoff:
        raise HTTPException(status_code=410, detail="Trigger has expired")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    agent_id: str = Depends(get_current_agent),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    stage: str | None = Query(None),
):
    """MOB-CONV-001: List conversations for the authenticated agent."""
    if stage is not None and stage not in VALID_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid stage '{stage}'. Must be one of: {', '.join(sorted(VALID_STAGES))}",
        )

    offset = (page - 1) * per_page

    # Build the optional stage filter
    stage_clause = ""
    params: list = [agent_id]
    if stage is not None:
        stage_clause = "AND cv.stage = %s"
        params.append(stage)

    data_query = f"""
        SELECT
            cv.id, cv.contact_id, cv.channel, cv.stage, cv.last_message_at,
            COALESCE(c.name, c.phone) as contact_name,
            c.phone as contact_phone,
            lm.body_preview as last_message_body,
            COALESCE(unread.cnt, 0) as unread_count,
            EXISTS(
                SELECT 1 FROM triggers t
                WHERE t.entity_id = cv.contact_id
                AND t.entity_type = 'contact'
                AND t.status = 'pending'
                AND t.autonomy_level = 'ask_agent'
                AND t.agent_id = cv.agent_id
            ) as has_pending_draft
        FROM conversations cv
        LEFT JOIN contacts c ON c.id = cv.contact_id
        LEFT JOIN LATERAL (
            SELECT LEFT(body, 150) as body_preview
            FROM messages
            WHERE conversation_id = cv.id
            ORDER BY created_at DESC
            LIMIT 1
        ) lm ON true
        LEFT JOIN LATERAL (
            SELECT COUNT(*) as cnt
            FROM messages
            WHERE conversation_id = cv.id
            AND created_at > COALESCE(cv.last_read_at, '1970-01-01'::timestamptz)
            AND sender_type IN ('client', 'ai')
        ) unread ON true
        WHERE cv.agent_id = %s
        {stage_clause}
        ORDER BY cv.last_message_at DESC NULLS LAST
        LIMIT %s OFFSET %s
    """

    count_query = f"""
        SELECT COUNT(*) as total
        FROM conversations cv
        WHERE cv.agent_id = %s
        {stage_clause}
    """

    # For the data query: agent_id is first param (already in params list via
    # the WHERE clause). We need a *separate* params list because the data
    # query uses agent_id as the first %s (from the params list we built),
    # then limit + offset at the end.
    #
    # But wait — the query already has %s for cv.agent_id in WHERE.  The
    # params list was started with agent_id.  So we re-build correctly:
    data_params: list = [agent_id]
    count_params: list = [agent_id]
    if stage is not None:
        data_params.append(stage)
        count_params.append(stage)
    data_params.extend([per_page, offset])

    async with get_async_db_connection() as conn:
        result = await conn.execute(data_query, data_params)
        rows = await result.fetchall()

        result = await conn.execute(count_query, count_params)
        count_row = await result.fetchone()

    total = count_row["total"] if count_row else 0
    pages = math.ceil(total / per_page) if total > 0 else 0

    data = []
    for row in rows:
        body = row.get("last_message_body")
        if body:
            body = nh3.clean(body, tags=set())
        data.append(
            ConversationItem(
                id=str(row["id"]),
                contact_id=str(row["contact_id"]),
                channel=row.get("channel"),
                stage=row.get("stage"),
                last_message_at=row.get("last_message_at"),
                contact_name=row.get("contact_name"),
                contact_phone=row.get("contact_phone"),
                last_message_body=body,
                unread_count=int(row.get("unread_count", 0)),
                has_pending_draft=bool(row.get("has_pending_draft", False)),
            )
        )

    return ConversationListResponse(
        data=data,
        pagination=PaginationMeta(
            total=total, page=page, per_page=per_page, pages=pages
        ),
    )


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def list_messages(
    conversation_id: str,
    agent_id: str = Depends(get_current_agent),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    before: str | None = Query(None),
):
    """MOB-CONV-002: List messages for a conversation."""
    # Verify conversation belongs to agent
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            "SELECT id FROM conversations WHERE id = %s::uuid AND agent_id = %s",
            [conversation_id, agent_id],
        )
        conv = await result.fetchone()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if before:
        # Cursor-based pagination (reverse chronological)
        data_query = """
            SELECT id, sender_type, body, ai_generated, delivery_status,
                   CASE WHEN delivery_status IN ('failed', 'undelivered')
                        THEN failure_reason END as failure_reason,
                   created_at
            FROM messages
            WHERE conversation_id = %s::uuid
              AND created_at < (SELECT created_at FROM messages WHERE id = %s::uuid)
            ORDER BY created_at DESC
            LIMIT %s
        """
        data_params = [conversation_id, before, per_page]

        count_query = """
            SELECT COUNT(*) as total
            FROM messages
            WHERE conversation_id = %s::uuid
        """
        count_params = [conversation_id]

        async with get_async_db_connection() as conn:
            result = await conn.execute(data_query, data_params)
            rows = await result.fetchall()

            result = await conn.execute(count_query, count_params)
            count_row = await result.fetchone()

        total = count_row["total"] if count_row else 0
        # For cursor pagination, pages is an approximation
        pages = math.ceil(total / per_page) if total > 0 else 0
    else:
        # Offset-based pagination (chronological)
        offset = (page - 1) * per_page
        data_query = """
            SELECT id, sender_type, body, ai_generated, delivery_status,
                   CASE WHEN delivery_status IN ('failed', 'undelivered')
                        THEN failure_reason END as failure_reason,
                   created_at
            FROM messages
            WHERE conversation_id = %s::uuid
            ORDER BY created_at ASC
            LIMIT %s OFFSET %s
        """
        data_params = [conversation_id, per_page, offset]

        count_query = """
            SELECT COUNT(*) as total
            FROM messages
            WHERE conversation_id = %s::uuid
        """
        count_params = [conversation_id]

        async with get_async_db_connection() as conn:
            result = await conn.execute(data_query, data_params)
            rows = await result.fetchall()

            result = await conn.execute(count_query, count_params)
            count_row = await result.fetchone()

        total = count_row["total"] if count_row else 0
        pages = math.ceil(total / per_page) if total > 0 else 0

    # Side effect: mark conversation as read
    async with get_async_db_connection() as conn:
        await conn.execute(
            "UPDATE conversations SET last_read_at = %s WHERE id = %s::uuid",
            [datetime.now(timezone.utc), conversation_id],
        )
        await conn.commit()

    data = [
        MessageItem(
            id=str(row["id"]),
            sender_type=row.get("sender_type"),
            body=row.get("body"),
            ai_generated=row.get("ai_generated"),
            delivery_status=row.get("delivery_status"),
            failure_reason=row.get("failure_reason"),
            created_at=row.get("created_at"),
        )
        for row in rows
    ]

    return MessageListResponse(
        data=data,
        pagination=PaginationMeta(
            total=total, page=page, per_page=per_page, pages=pages
        ),
    )


@router.post("/triggers/{trigger_id}/approve", response_model=TriggerApproveResponse)
async def approve_trigger(
    trigger_id: str,
    agent_id: str = Depends(get_current_agent),
):
    """MOB-CONV-003: Approve a pending ask_agent trigger."""
    trigger = await _get_trigger_for_agent(trigger_id, agent_id)
    _check_trigger_expiry(trigger)

    async with get_async_db_connection() as conn:
        await conn.execute(
            "UPDATE triggers SET status = 'approved' WHERE id = %s::uuid",
            [trigger_id],
        )
        await conn.commit()

    preview = trigger.get("message_template") or ""
    return TriggerApproveResponse(
        status="approved",
        trigger_id=str(trigger["id"]),
        message_preview=preview[:150] if preview else None,
    )


@router.put("/triggers/{trigger_id}/edit", response_model=TriggerEditResponse)
async def edit_trigger(
    trigger_id: str,
    body: TriggerEditRequest,
    agent_id: str = Depends(get_current_agent),
):
    """MOB-CONV-004: Edit the message body of a pending ask_agent trigger."""
    trigger = await _get_trigger_for_agent(trigger_id, agent_id)
    _check_trigger_expiry(trigger)

    async with get_async_db_connection() as conn:
        await conn.execute(
            "UPDATE triggers SET message_template = %s WHERE id = %s::uuid",
            [body.body, trigger_id],
        )
        await conn.commit()

    return TriggerEditResponse(
        status="updated",
        trigger_id=trigger_id,
        body=body.body,
    )


@router.post("/triggers/{trigger_id}/reject", response_model=TriggerRejectResponse)
async def reject_trigger(
    trigger_id: str,
    agent_id: str = Depends(get_current_agent),
):
    """MOB-CONV-005: Reject a pending ask_agent trigger."""
    trigger = await _get_trigger_for_agent(trigger_id, agent_id)
    _check_trigger_expiry(trigger)

    async with get_async_db_connection() as conn:
        await conn.execute(
            "UPDATE triggers SET status = 'cancelled' WHERE id = %s::uuid",
            [trigger_id],
        )
        await conn.commit()

    return TriggerRejectResponse(
        status="rejected",
        trigger_id=str(trigger["id"]),
    )
