import logging
import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db.connection import get_async_db_connection

from .deps import get_current_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mobile/contacts", tags=["mobile-contacts"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ContactSummary(BaseModel):
    id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    role: str | None = None
    lifecycle_stage: str | None = None
    lead_source: str | None = None
    last_contact_at: datetime | None = None
    created_at: datetime | None = None


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int


class ContactListResponse(BaseModel):
    data: list[ContactSummary]
    pagination: PaginationMeta


class LeadPreferences(BaseModel):
    areas: list[str] | str | None = None
    timeline: str | None = None
    preapproved: bool | None = None
    property_type: str | None = None
    bedrooms_min: int | None = None
    bathrooms_min: float | None = None
    price_min: float | None = None
    price_max: float | None = None


class ContactDetail(BaseModel):
    id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    role: str | None = None
    lifecycle_stage: str | None = None
    lead_source: str | None = None
    notes: str | None = None
    last_contact_at: datetime | None = None
    language_detected: str | None = None
    interaction_count: int | None = None
    created_at: datetime | None = None


class ConversationSummary(BaseModel):
    id: str
    channel: str | None = None
    stage: str | None = None
    last_message_at: datetime | None = None
    last_message_preview: str | None = None


class ShowingSummary(BaseModel):
    id: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    status: str | None = None
    listing_address: str | None = None


class ContactDetailResponse(BaseModel):
    contact: ContactDetail
    lead_preferences: LeadPreferences | None = None
    recent_conversations: list[ConversationSummary]
    upcoming_showings: list[ShowingSummary]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: dict, keys: list[str]) -> dict:
    """Extract only the specified keys from a row dict, converting UUIDs to str."""
    result = {}
    for k in keys:
        val = row.get(k)
        if val is not None and hasattr(val, "hex") and hasattr(val, "int"):
            # UUID-like object
            val = str(val)
        result[k] = val
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    search: str | None = Query(None),
    role: str | None = Query(None),
    lead_source: str | None = Query(None),
    lifecycle_stage: str | None = Query(None),
    agent_id: str = Depends(get_current_agent),
):
    # Validate search length
    if search is not None and len(search) < 2:
        raise HTTPException(
            status_code=422,
            detail="Search term must be at least 2 characters",
        )

    # Build dynamic WHERE clause
    conditions = ["agent_id = %s"]
    params: list = [agent_id]

    if role is not None:
        conditions.append("role = %s")
        params.append(role)

    if lead_source is not None:
        conditions.append("lead_source = %s")
        params.append(lead_source)

    if lifecycle_stage is not None:
        conditions.append("lifecycle_stage = %s")
        params.append(lifecycle_stage)

    if search is not None:
        like_pattern = f"%{search}%"
        conditions.append("(name ILIKE %s OR phone ILIKE %s OR email ILIKE %s)")
        params.extend([like_pattern, like_pattern, like_pattern])

    where_clause = " AND ".join(conditions)

    offset = (page - 1) * per_page

    data_query = f"""
        SELECT id, name, phone, email, role, lifecycle_stage, lead_source,
               last_contact_at, created_at
        FROM contacts
        WHERE {where_clause}
        ORDER BY last_contact_at DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    count_query = f"SELECT COUNT(*) as total FROM contacts WHERE {where_clause}"

    data_params = params + [per_page, offset]

    async with get_async_db_connection() as conn:
        # Count query
        result = await conn.execute(count_query, params)
        count_row = await result.fetchone()
        total = count_row["total"] if count_row else 0

        # Data query
        result = await conn.execute(data_query, data_params)
        rows = await result.fetchall()

    contacts = [
        ContactSummary(
            **_row_to_dict(
                row,
                [
                    "id",
                    "name",
                    "phone",
                    "email",
                    "role",
                    "lifecycle_stage",
                    "lead_source",
                    "last_contact_at",
                    "created_at",
                ],
            )
        )
        for row in rows
    ]

    pages = math.ceil(total / per_page) if total > 0 else 0

    return ContactListResponse(
        data=contacts,
        pagination=PaginationMeta(
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
        ),
    )


@router.get("/{contact_id}", response_model=ContactDetailResponse)
async def get_contact(
    contact_id: str,
    agent_id: str = Depends(get_current_agent),
):
    async with get_async_db_connection() as conn:
        # Query 1: Contact + lead preferences
        result = await conn.execute(
            """
            SELECT c.id, c.name, c.phone, c.email, c.role, c.lifecycle_stage, c.lead_source,
                   c.notes, c.last_contact_at, c.language_detected, c.interaction_count, c.created_at,
                   lp.areas, lp.timeline, lp.preapproved, lp.property_type, lp.bedrooms_min,
                   lp.bathrooms_min, lp.price_min, lp.price_max
            FROM contacts c
            LEFT JOIN lead_preferences lp ON lp.contact_id = c.id
            WHERE c.id = %s AND c.agent_id = %s
            """,
            [contact_id, agent_id],
        )
        contact_row = await result.fetchone()

        if not contact_row:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Query 2: Recent conversations (last 5)
        result = await conn.execute(
            """
            SELECT cv.id, cv.channel, cv.stage, cv.last_message_at,
                   LEFT((SELECT body FROM messages WHERE conversation_id = cv.id
                         ORDER BY created_at DESC LIMIT 1), 50) as last_message_preview
            FROM conversations cv
            WHERE cv.contact_id = %s AND cv.agent_id = %s
            ORDER BY cv.last_message_at DESC NULLS LAST
            LIMIT 5
            """,
            [contact_id, agent_id],
        )
        conversation_rows = await result.fetchall()

        # Query 3: Upcoming showings
        result = await conn.execute(
            """
            SELECT s.id, s.start_time, s.end_time, s.status, l.address as listing_address
            FROM showings s
            JOIN listings l ON l.id = s.listing_id
            WHERE s.contact_id = %s AND s.agent_id = %s
            AND s.status IN ('confirmed', 'hold')
            AND s.start_time > now()
            ORDER BY s.start_time
            LIMIT 10
            """,
            [contact_id, agent_id],
        )
        showing_rows = await result.fetchall()

    # Build contact detail
    contact = ContactDetail(
        **_row_to_dict(
            contact_row,
            [
                "id",
                "name",
                "phone",
                "email",
                "role",
                "lifecycle_stage",
                "lead_source",
                "notes",
                "last_contact_at",
                "language_detected",
                "interaction_count",
                "created_at",
            ],
        )
    )

    # Build lead preferences (None if all preference fields are null)
    pref_fields = [
        "areas",
        "timeline",
        "preapproved",
        "property_type",
        "bedrooms_min",
        "bathrooms_min",
        "price_min",
        "price_max",
    ]
    has_preferences = any(contact_row.get(f) is not None for f in pref_fields)
    lead_preferences = None
    if has_preferences:
        pref_data = {}
        for f in pref_fields:
            val = contact_row.get(f)
            # Convert Decimal to float for numeric fields
            if val is not None and hasattr(val, "as_tuple"):
                val = float(val)
            pref_data[f] = val
        lead_preferences = LeadPreferences(**pref_data)

    # Build conversations
    conversations = [
        ConversationSummary(
            **_row_to_dict(
                row,
                ["id", "channel", "stage", "last_message_at", "last_message_preview"],
            )
        )
        for row in conversation_rows
    ]

    # Build showings
    showings = [
        ShowingSummary(
            **_row_to_dict(
                row,
                ["id", "start_time", "end_time", "status", "listing_address"],
            )
        )
        for row in showing_rows
    ]

    return ContactDetailResponse(
        contact=contact,
        lead_preferences=lead_preferences,
        recent_conversations=conversations,
        upcoming_showings=showings,
    )
