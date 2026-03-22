"""Mobile API — JSON endpoints for the SwiftUI iOS app.

All endpoints are prefixed with /api/mobile/ and require JWT authentication
(except auth endpoints). Every database query uses RLS via set_agent_context.

New DB columns assumed (not migrated here):
  - agents.password_hash TEXT  -- bcrypt hash for mobile login
  - messages.read_by_agent BOOLEAN DEFAULT false  -- for unread tracking
"""
import json
import logging
from datetime import datetime, timezone, timedelta, date
from uuid import UUID

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings
from app.db.connection import get_db_connection, set_agent_context
from app.models.schemas import AgentConfig
from app.models.mobile_schemas import (
    LoginRequest,
    LoginResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    AgentProfile,
    BriefingResponse,
    BriefingShowing,
    BriefingTrigger,
    BriefingGap,
    BriefingNewLead,
    BriefingDomAlert,
    ScheduleEvent,
    ScheduleResponse,
    ShowingDetailResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationDetail,
    MessageItem,
    MessageListResponse,
    SendMessageRequest,
    SendMessageResponse,
    UnreadCountResponse,
    CreateListingRequest,
    UpdateListingRequest,
    ListingListItem,
    ListingListResponse,
    ListingResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mobile", tags=["mobile"])
security = HTTPBearer()

ACCESS_TOKEN_TTL = timedelta(hours=24)
REFRESH_TOKEN_TTL = timedelta(days=30)


# ============================================================
# JWT Helpers
# ============================================================

def _create_access_token(agent_id: UUID) -> str:
    settings = get_settings()
    payload = {
        "sub": str(agent_id),
        "type": "access",
        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_TTL,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.MOBILE_JWT_SECRET, algorithm="HS256")


def _create_refresh_token(agent_id: UUID) -> str:
    settings = get_settings()
    payload = {
        "sub": str(agent_id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.MOBILE_JWT_SECRET, algorithm="HS256")


def _decode_token(token: str, expected_type: str = "access") -> dict:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.MOBILE_JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail=f"Expected {expected_type} token")

    return payload


# ============================================================
# Auth Dependency
# ============================================================

def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AgentConfig:
    """FastAPI dependency — extract agent from Bearer JWT token."""
    payload = _decode_token(credentials.credentials, expected_type="access")
    agent_id = payload.get("sub")
    if not agent_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        agent_uuid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid agent ID in token")

    # Query agent — no RLS needed, agents table doesn't have RLS
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM agents WHERE id = %s", [str(agent_uuid)]
        ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Agent not found")

    return AgentConfig(**row)


# ============================================================
# Auth Endpoints
# ============================================================

@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Authenticate agent with email + password, return JWT tokens."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM agents WHERE email = %s", [req.email]
        ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # password_hash column assumed to exist on agents table (bcrypt)
    stored_hash = row.get("password_hash")
    if not stored_hash:
        raise HTTPException(
            status_code=401,
            detail="Mobile login not configured for this account",
        )

    if not bcrypt.checkpw(req.password.encode("utf-8"), stored_hash.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    agent = AgentConfig(**row)
    access_token = _create_access_token(agent.id)
    refresh_token = _create_refresh_token(agent.id)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        agent=AgentProfile(
            id=agent.id,
            name=agent.name,
            email=agent.email,
            phone=agent.phone,
            brokerage=agent.brokerage,
            market=agent.market,
            timezone=agent.timezone,
        ),
    )


@router.post("/auth/refresh", response_model=TokenRefreshResponse)
def refresh_token(req: TokenRefreshRequest):
    """Exchange a refresh token for a new access token."""
    payload = _decode_token(req.refresh_token, expected_type="refresh")
    agent_id = UUID(payload["sub"])

    # Verify agent still exists
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id FROM agents WHERE id = %s", [str(agent_id)]
        ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Agent not found")

    new_access = _create_access_token(agent_id)
    return TokenRefreshResponse(
        access_token=new_access,
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
    )


# ============================================================
# Briefing
# ============================================================

@router.get("/briefing", response_model=BriefingResponse)
def get_briefing(agent: AgentConfig = Depends(get_current_agent)):
    """Morning briefing with time-of-day-aware greeting and summary bullets."""
    from app.worker.daily_scanner import compile_morning_briefing

    briefing = compile_morning_briefing(agent)

    # Time-of-day greeting
    try:
        from zoneinfo import ZoneInfo
        agent_now = datetime.now(ZoneInfo(agent.timezone))
    except Exception:
        agent_now = datetime.now(timezone.utc)

    hour = agent_now.hour
    if hour < 12:
        greeting = f"Good morning, {agent.name}"
    elif hour < 17:
        greeting = f"Good afternoon, {agent.name}"
    else:
        greeting = f"Good evening, {agent.name}"

    # Summary bullets from briefing data
    bullets = []
    n_showings = len(briefing.get("showings_today", []))
    n_triggers = len(briefing.get("triggers_today", []))
    n_leads = len(briefing.get("new_leads", []))
    n_gaps = len(briefing.get("gaps", []))
    n_dom = len(briefing.get("dom_alerts", []))

    if n_showings:
        bullets.append(f"You have {n_showings} showing{'s' if n_showings != 1 else ''} today")
    else:
        bullets.append("No showings scheduled today")
    if n_triggers:
        bullets.append(f"{n_triggers} automated task{'s' if n_triggers != 1 else ''} queued")
    if n_leads:
        bullets.append(f"{n_leads} new lead{'s' if n_leads != 1 else ''} in the last 24 hours")
    if n_gaps:
        bullets.append(f"{n_gaps} client{'s' if n_gaps != 1 else ''} need follow-up")
    if n_dom:
        bullets.append(f"{n_dom} listing{'s' if n_dom != 1 else ''} hitting DOM milestones")

    # Recent assistant activity summary
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        recent_tools = conn.execute(
            """SELECT tool_name, COUNT(*) as cnt
               FROM tool_executions
               WHERE created_at > now() - interval '24 hours'
               GROUP BY tool_name
               ORDER BY cnt DESC LIMIT 5"""
        ).fetchall()

    if recent_tools:
        tool_summary = ", ".join(f"{t['tool_name']} ({t['cnt']})" for t in recent_tools)
        bullets.append(f"Assistant actions (24h): {tool_summary}")

    return BriefingResponse(
        greeting=greeting,
        date=briefing.get("date", datetime.now(timezone.utc).strftime("%A, %B %d")),
        summary_bullets=bullets,
        showings_today=[BriefingShowing(**s) for s in briefing.get("showings_today", [])],
        triggers_today=[BriefingTrigger(**t) for t in briefing.get("triggers_today", [])],
        gaps=[BriefingGap(**g) for g in briefing.get("gaps", [])],
        new_leads=[BriefingNewLead(**l) for l in briefing.get("new_leads", [])],
        dom_alerts=[BriefingDomAlert(**a) for a in briefing.get("dom_alerts", [])],
    )


# ============================================================
# Schedule
# ============================================================

@router.get("/schedule", response_model=ScheduleResponse)
def get_schedule(
    date_param: date | None = Query(None, alias="date"),
    agent: AgentConfig = Depends(get_current_agent),
):
    """Get schedule events (showings + triggers) for a given date."""
    target_date = date_param or date.today()
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    events: list[ScheduleEvent] = []

    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)

        # Showings
        showings = conn.execute(
            """SELECT s.id, s.start_time, s.end_time, s.status,
                      c.name as contact_name, l.address as listing_address
               FROM showings s
               JOIN contacts c ON s.contact_id = c.id
               JOIN listings l ON s.listing_id = l.id
               WHERE s.start_time BETWEEN %s AND %s
               AND s.status IN ('confirmed', 'hold')
               ORDER BY s.start_time""",
            [day_start, day_end],
        ).fetchall()

        for s in showings:
            events.append(ScheduleEvent(
                id=s["id"],
                type="showing",
                title=f"Showing: {s['listing_address']}",
                subtitle=s["contact_name"],
                start_time=s["start_time"],
                end_time=s["end_time"],
                status=s["status"],
                location=s["listing_address"],
                contact_name=s["contact_name"],
                listing_address=s["listing_address"],
            ))

        # Triggers
        triggers = conn.execute(
            """SELECT id, trigger_type, message_template, scheduled_at, status
               FROM triggers
               WHERE scheduled_at BETWEEN %s AND %s
               AND status = 'pending'
               ORDER BY scheduled_at""",
            [day_start, day_end],
        ).fetchall()

        for t in triggers:
            events.append(ScheduleEvent(
                id=t["id"],
                type="trigger",
                title=t["trigger_type"].replace("_", " ").title(),
                subtitle=t["message_template"],
                start_time=t["scheduled_at"],
                status=t["status"],
            ))

    # Sort combined events by start time
    events.sort(key=lambda e: e.start_time)

    return ScheduleResponse(
        date=target_date.isoformat(),
        events=events,
        total_count=len(events),
    )


@router.get("/schedule/{event_id}", response_model=ShowingDetailResponse)
def get_schedule_event(event_id: UUID, agent: AgentConfig = Depends(get_current_agent)):
    """Get showing detail by ID."""
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        row = conn.execute(
            """SELECT s.*,
                      c.name as contact_name, c.phone as contact_phone,
                      l.address as listing_address, l.price as listing_price,
                      l.lockbox, l.showing_instructions
               FROM showings s
               JOIN contacts c ON s.contact_id = c.id
               JOIN listings l ON s.listing_id = l.id
               WHERE s.id = %s""",
            [str(event_id)],
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Showing not found")

    return ShowingDetailResponse(
        id=row["id"],
        contact_name=row["contact_name"],
        contact_phone=row["contact_phone"],
        listing_address=row["listing_address"],
        listing_price=row["listing_price"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        status=row["status"],
        lockbox=row["lockbox"],
        showing_instructions=row["showing_instructions"],
        feedback=row["feedback"],
        calendar_event_id=row["calendar_event_id"],
        created_at=row["created_at"],
    )


# ============================================================
# Conversations
# ============================================================

@router.get("/conversations/unread-count", response_model=UnreadCountResponse)
def get_unread_count(agent: AgentConfig = Depends(get_current_agent)):
    """Total unread message count across all conversations (for tab badge).

    Unread = messages with sender_type != 'agent' and read_by_agent = false.
    NOTE: requires messages.read_by_agent column (BOOLEAN DEFAULT false).
    """
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM messages
               WHERE sender_type != 'agent'
               AND COALESCE(read_by_agent, false) = false"""
        ).fetchone()

    return UnreadCountResponse(unread_count=row["cnt"] if row else 0)


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    filter: str = Query("all", regex="^(all|unread|bot_handled)$"),
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    agent: AgentConfig = Depends(get_current_agent),
):
    """List conversations with filters, search, and pagination."""
    offset = (page - 1) * page_size

    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)

        # Base query with subqueries for last message and unread count
        conditions = []
        params: list = []

        if filter == "unread":
            conditions.append(
                """EXISTS (
                    SELECT 1 FROM messages m2
                    WHERE m2.conversation_id = cv.id
                    AND m2.sender_type != 'agent'
                    AND COALESCE(m2.read_by_agent, false) = false
                )"""
            )
        elif filter == "bot_handled":
            conditions.append("cv.active_handler = 'bot'")

        if search:
            conditions.append(
                "(LOWER(co.name) LIKE LOWER(%s) OR LOWER(co.phone) LIKE LOWER(%s))"
            )
            search_term = f"%{search}%"
            params.extend([search_term, search_term])

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        # Count total
        count_row = conn.execute(
            f"""SELECT COUNT(*) as cnt
                FROM conversations cv
                LEFT JOIN contacts co ON cv.contact_id = co.id
                WHERE {where_clause}""",
            params,
        ).fetchone()
        total_count = count_row["cnt"] if count_row else 0

        # Fetch page
        rows = conn.execute(
            f"""SELECT cv.id, cv.contact_id, cv.channel, cv.stage, cv.active_handler,
                       cv.last_message_at,
                       COALESCE(co.name, 'Unknown') as contact_name,
                       co.phone as contact_phone,
                       (SELECT body FROM messages m
                        WHERE m.conversation_id = cv.id
                        ORDER BY m.created_at DESC LIMIT 1) as last_message_body,
                       (SELECT sender_type FROM messages m
                        WHERE m.conversation_id = cv.id
                        ORDER BY m.created_at DESC LIMIT 1) as last_message_sender,
                       (SELECT COUNT(*) FROM messages m2
                        WHERE m2.conversation_id = cv.id
                        AND m2.sender_type != 'agent'
                        AND COALESCE(m2.read_by_agent, false) = false) as unread_count
                FROM conversations cv
                LEFT JOIN contacts co ON cv.contact_id = co.id
                WHERE {where_clause}
                ORDER BY cv.last_message_at DESC NULLS LAST
                LIMIT %s OFFSET %s""",
            params + [page_size, offset],
        ).fetchall()

    conversations = [
        ConversationListItem(
            id=r["id"],
            contact_id=r["contact_id"],
            contact_name=r["contact_name"],
            contact_phone=r["contact_phone"],
            channel=r["channel"],
            last_message_body=r["last_message_body"],
            last_message_at=r["last_message_at"],
            last_message_sender=r["last_message_sender"],
            unread_count=r["unread_count"],
            active_handler=r["active_handler"],
            stage=r["stage"],
        )
        for r in rows
    ]

    return ConversationListResponse(
        conversations=conversations,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: UUID,
    agent: AgentConfig = Depends(get_current_agent),
):
    """Get conversation detail with contact info."""
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        row = conn.execute(
            """SELECT cv.*,
                      COALESCE(co.name, 'Unknown') as contact_name,
                      co.phone as contact_phone,
                      co.email as contact_email,
                      co.role as contact_role,
                      co.lifecycle_stage as contact_lifecycle_stage
               FROM conversations cv
               LEFT JOIN contacts co ON cv.contact_id = co.id
               WHERE cv.id = %s""",
            [str(conversation_id)],
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Mark messages as read
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        conn.execute(
            """UPDATE messages SET read_by_agent = true
               WHERE conversation_id = %s
               AND sender_type != 'agent'
               AND COALESCE(read_by_agent, false) = false""",
            [str(conversation_id)],
        )
        conn.commit()

    return ConversationDetail(
        id=row["id"],
        contact_id=row["contact_id"],
        contact_name=row["contact_name"],
        contact_phone=row["contact_phone"],
        contact_email=row["contact_email"],
        contact_role=row["contact_role"],
        contact_lifecycle_stage=row["contact_lifecycle_stage"],
        channel=row["channel"],
        stage=row["stage"],
        active_handler=row["active_handler"],
        last_message_at=row["last_message_at"],
        created_at=row["created_at"],
    )


@router.get(
    "/conversations/{conversation_id}/messages", response_model=MessageListResponse
)
def get_messages(
    conversation_id: UUID,
    cursor: str | None = Query(None, description="ISO timestamp cursor for pagination"),
    limit: int = Query(50, ge=1, le=100),
    agent: AgentConfig = Depends(get_current_agent),
):
    """Paginated messages for a conversation using cursor-based pagination.

    Returns messages in reverse chronological order (newest first).
    Pass the `cursor` value from the response to get the next (older) page.
    """
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)

        # Verify conversation exists for this agent
        conv = conn.execute(
            "SELECT id FROM conversations WHERE id = %s",
            [str(conversation_id)],
        ).fetchone()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        params: list = [str(conversation_id), limit + 1]  # fetch one extra to check has_more
        cursor_clause = ""
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
                cursor_clause = "AND m.created_at < %s"
                params = [str(conversation_id), cursor_dt, limit + 1]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor format")

        rows = conn.execute(
            f"""SELECT m.id, m.sender_type, m.body, m.ai_generated,
                       m.model_used, m.intent, m.created_at
                FROM messages m
                WHERE m.conversation_id = %s
                {cursor_clause}
                ORDER BY m.created_at DESC
                LIMIT %s""",
            params,
        ).fetchall()

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    messages = [
        MessageItem(
            id=r["id"],
            sender_type=r["sender_type"],
            body=r["body"],
            ai_generated=r["ai_generated"],
            model_used=r["model_used"],
            intent=r["intent"],
            created_at=r["created_at"],
        )
        for r in rows
    ]

    next_cursor = None
    if has_more and rows:
        next_cursor = rows[-1]["created_at"].isoformat()

    return MessageListResponse(
        messages=messages,
        cursor=next_cursor,
        has_more=has_more,
    )


@router.post(
    "/conversations/{conversation_id}/messages", response_model=SendMessageResponse
)
def send_message(
    conversation_id: UUID,
    req: SendMessageRequest,
    agent: AgentConfig = Depends(get_current_agent),
):
    """Send a message in a conversation. Sets active_handler to 'agent' and sends via Twilio."""
    from app.services.twilio_service import send_client_message

    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)

        # Get conversation + contact
        conv = conn.execute(
            """SELECT cv.*, co.phone as contact_phone
               FROM conversations cv
               LEFT JOIN contacts co ON cv.contact_id = co.id
               WHERE cv.id = %s""",
            [str(conversation_id)],
        ).fetchone()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    contact_id = conv.get("contact_id")
    contact_phone = conv.get("contact_phone")

    if not contact_phone:
        raise HTTPException(status_code=400, detail="No phone number for this contact")

    # Set active_handler to 'agent' (human takeover)
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        conn.execute(
            """UPDATE conversations
               SET active_handler = 'agent', last_message_at = now()
               WHERE id = %s""",
            [str(conversation_id)],
        )

        # Insert the agent's message
        msg_row = conn.execute(
            """INSERT INTO messages
               (agent_id, conversation_id, sender_type, body, ai_generated)
               VALUES (%s, %s, 'agent', %s, false)
               RETURNING id""",
            [str(agent.id), str(conversation_id), req.body],
        ).fetchone()
        conn.commit()

    # Send via Twilio
    twilio_result = send_client_message(
        agent_id=agent.id,
        contact_id=contact_id,
        message=req.body,
        from_number=agent.twilio_number,
        to_number=contact_phone,
    )

    return SendMessageResponse(
        message_id=msg_row["id"] if msg_row else None,
        status=twilio_result.get("status", "sent"),
        twilio_sid=twilio_result.get("sid"),
    )


# ============================================================
# Listings
# ============================================================

@router.get("/listings", response_model=ListingListResponse)
def list_listings(
    status: str | None = Query(None, description="Filter by status (active, pending, sold, etc.)"),
    agent: AgentConfig = Depends(get_current_agent),
):
    """Get agent's listings, optionally filtered by status."""
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)

        params: list = []
        status_clause = ""
        if status:
            status_clause = "AND status = %s"
            params.append(status)

        rows = conn.execute(
            f"""SELECT id, address, price, beds, baths, sqft, status,
                       list_date, created_at
                FROM listings
                WHERE TRUE {status_clause}
                ORDER BY created_at DESC""",
            params,
        ).fetchall()

    now_date = date.today()
    listings = []
    for r in rows:
        dom = None
        if r.get("list_date"):
            dom = (now_date - r["list_date"]).days

        listings.append(ListingListItem(
            id=r["id"],
            address=r["address"],
            price=r["price"],
            beds=r["beds"],
            baths=r["baths"],
            sqft=r["sqft"],
            status=r["status"],
            list_date=r["list_date"],
            dom=dom,
            created_at=r["created_at"],
        ))

    return ListingListResponse(
        listings=listings,
        total_count=len(listings),
    )


@router.post("/listings", response_model=ListingResponse, status_code=201)
def create_listing(
    req: CreateListingRequest,
    agent: AgentConfig = Depends(get_current_agent),
):
    """Create a new listing from structured form data."""
    features_json = json.dumps(req.features)
    access_rules = json.dumps({"type": "vacant", "approval_required": False})

    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        row = conn.execute(
            """INSERT INTO listings
               (agent_id, address, price, beds, baths, sqft, hoa,
                features, showing_instructions, lockbox, access_rules,
                list_date, status, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       CURRENT_DATE, 'active', %s)
               RETURNING *""",
            [
                str(agent.id), req.address, req.price,
                req.beds, req.baths, req.sqft, req.hoa,
                features_json, req.showing_instructions, req.lockbox,
                access_rules, req.notes,
            ],
        ).fetchone()
        conn.commit()

    if not row:
        raise HTTPException(status_code=500, detail="Failed to create listing")

    return _listing_row_to_response(row)


@router.get("/listings/{listing_id}", response_model=ListingResponse)
def get_listing_detail(
    listing_id: UUID,
    agent: AgentConfig = Depends(get_current_agent),
):
    """Get listing detail by ID."""
    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        row = conn.execute(
            "SELECT * FROM listings WHERE id = %s",
            [str(listing_id)],
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Listing not found")

    return _listing_row_to_response(row)


@router.put("/listings/{listing_id}", response_model=ListingResponse)
def update_listing(
    listing_id: UUID,
    req: UpdateListingRequest,
    agent: AgentConfig = Depends(get_current_agent),
):
    """Update an existing listing."""
    # Build dynamic update from non-None fields
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "features" in updates and isinstance(updates["features"], list):
        updates["features"] = json.dumps(updates["features"])

    set_clauses = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values())
    values.append(str(listing_id))

    with get_db_connection() as conn:
        set_agent_context(conn, agent.id)
        row = conn.execute(
            f"""UPDATE listings SET {set_clauses}, last_updated_at = now()
                WHERE id = %s
                RETURNING *""",
            values,
        ).fetchone()
        conn.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Listing not found")

    return _listing_row_to_response(row)


# ============================================================
# Helpers
# ============================================================

def _listing_row_to_response(row: dict) -> ListingResponse:
    """Convert a listings DB row to a ListingResponse."""
    features = row.get("features") or []
    if isinstance(features, str):
        try:
            features = json.loads(features)
        except (json.JSONDecodeError, TypeError):
            features = []

    access_rules = row.get("access_rules") or {}
    if isinstance(access_rules, str):
        try:
            access_rules = json.loads(access_rules)
        except (json.JSONDecodeError, TypeError):
            access_rules = {}

    open_house_dates = row.get("open_house_dates") or []
    if isinstance(open_house_dates, str):
        try:
            open_house_dates = json.loads(open_house_dates)
        except (json.JSONDecodeError, TypeError):
            open_house_dates = []

    dom = None
    if row.get("list_date"):
        dom = (date.today() - row["list_date"]).days

    freshness_warning = None
    if row.get("last_updated_at"):
        last_updated = row["last_updated_at"]
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - last_updated
        if age > timedelta(days=7):
            freshness_warning = f"Last updated {age.days} days ago. Data may be stale."

    return ListingResponse(
        id=row["id"],
        address=row["address"],
        price=row["price"],
        beds=row.get("beds"),
        baths=row.get("baths"),
        sqft=row.get("sqft"),
        hoa=row.get("hoa"),
        features=features,
        showing_instructions=row.get("showing_instructions"),
        lockbox=row.get("lockbox"),
        access_rules=access_rules,
        open_house_dates=open_house_dates,
        list_date=row.get("list_date"),
        status=row.get("status", "active"),
        notes=row.get("notes"),
        dom=dom,
        freshness_warning=freshness_warning,
        last_updated_at=row.get("last_updated_at"),
        created_at=row.get("created_at"),
    )
