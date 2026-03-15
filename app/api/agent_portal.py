"""Agent Portal — mobile-first dashboard for real estate agents."""
import html
import logging
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import get_settings
from app.api.console_auth import generate_csrf_token, validate_csrf_token
from app.services.redis_pool import get_redis_pool
from app.tools.sql_utils import escape_ilike

import psycopg
import redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent-portal"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "agent"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

SESSION_COOKIE = "agent_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days

LOGIN_CODE_TTL = 300  # 5 minutes

# ── Agent login rate limiting ─────────────────────────────────
# Separate from console login rate limits to prevent cross-contamination.
# Uses a distinct Redis key prefix so agent portal and console login
# attempts are tracked independently.

_AGENT_LOGIN_MAX_ATTEMPTS = 5
_AGENT_LOGIN_WINDOW = 900  # 15 minutes


def _check_agent_login_rate(ip: str) -> tuple[bool, int]:
    """Check if IP is rate-limited for agent portal login.

    Returns (allowed, retry_after_seconds). Fails open when Redis is
    unavailable — a temporary Redis outage should not lock all agents out.
    """
    try:
        r = get_redis_pool()
        key = f"agent_login:{ip}"
        attempts = r.get(key)
        if attempts and int(attempts) >= _AGENT_LOGIN_MAX_ATTEMPTS:
            ttl = r.ttl(key)
            return False, max(ttl, 60)
        return True, 0
    except redis.RedisError:
        logger.warning("Redis unavailable for agent login rate limiting — failing open")
        return True, 0


def _record_agent_login_fail(ip: str) -> None:
    """Increment the failed agent login counter for an IP.

    TTL is only set on key creation to prevent attackers from extending
    the lockout window with repeated failed attempts.
    """
    try:
        r = get_redis_pool()
        key = f"agent_login:{ip}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, _AGENT_LOGIN_WINDOW)
    except redis.RedisError:
        logger.warning("Redis unavailable — agent login failed attempt not recorded")


def _reset_agent_login_rate(ip: str) -> None:
    """Clear the failed agent login counter after successful login."""
    try:
        r = get_redis_pool()
        r.delete(f"agent_login:{ip}")
    except redis.RedisError:
        pass


# Fallback in-memory store for when Redis is unavailable
_login_codes: dict[str, dict] = {}


def _store_login_code(phone: str, code: str) -> None:
    """Store a login code in Redis, falling back to in-memory dict."""
    try:
        r = get_redis_pool()
        r.setex(f"login_code:{phone}", LOGIN_CODE_TTL, code)
    except redis.RedisError as e:
        logger.warning("Redis unavailable for login code storage, using in-memory fallback: %s", e)
        _login_codes[phone] = {
            "code": code,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=LOGIN_CODE_TTL),
        }


def _get_login_code(phone: str) -> str | None:
    """Retrieve a login code from Redis, falling back to in-memory dict."""
    try:
        r = get_redis_pool()
        value = r.get(f"login_code:{phone}")
        if value is not None:
            return value.decode() if isinstance(value, bytes) else value
        return None
    except redis.RedisError as e:
        logger.warning("Redis unavailable for login code retrieval, using in-memory fallback: %s", e)
        stored = _login_codes.get(phone)
        if not stored:
            return None
        if datetime.now(timezone.utc) > stored["expires_at"]:
            del _login_codes[phone]
            return None
        return stored["code"]


def _delete_login_code(phone: str) -> None:
    """Delete a login code from Redis, falling back to in-memory dict."""
    try:
        r = get_redis_pool()
        r.delete(f"login_code:{phone}")
    except redis.RedisError as e:
        logger.warning("Redis unavailable for login code deletion, using in-memory fallback: %s", e)
        _login_codes.pop(phone, None)


def _get_serializer() -> URLSafeTimedSerializer:
    """Build the session serializer for agent portal cookies.

    Prefers a dedicated AGENT_PORTAL_SESSION_SECRET when configured;
    falls back to the derived console secret + "-agent" suffix for
    backward compatibility with existing sessions during rollout.
    """
    settings = get_settings()
    secret = settings.AGENT_PORTAL_SESSION_SECRET or (settings.CONSOLE_SESSION_SECRET + "-agent")
    return URLSafeTimedSerializer(secret)


def _create_session(response: Response, agent_id: str) -> None:
    s = _get_serializer()
    token = s.dumps({"agent_id": agent_id})
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=SESSION_MAX_AGE,
        httponly=True, samesite="lax",
        secure=get_settings().ENVIRONMENT != "development",
    )


def _get_agent_id(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = _get_serializer().loads(token, max_age=SESSION_MAX_AGE)
        return data.get("agent_id")
    except (BadSignature, SignatureExpired):
        return None


def _require_agent(request: Request) -> tuple[str, RedirectResponse | None]:
    agent_id = _get_agent_id(request)
    if not agent_id:
        return "", RedirectResponse("/agent/login", status_code=303)
    return agent_id, None


def _render(request: Request, template: str, **ctx):
    tmp = Response()
    csrf = generate_csrf_token(request, tmp)
    ctx["csrf_token"] = csrf
    resp = templates.TemplateResponse(request, template, ctx)
    for header_value in tmp.headers.getlist("set-cookie"):
        resp.headers.append("set-cookie", header_value)
    return resp


def _check_csrf(request: Request, csrf_token: str | None) -> Response | None:
    """Return 403 if CSRF token is invalid, else None."""
    if not validate_csrf_token(request, csrf_token):
        return Response("CSRF validation failed", status_code=403)
    return None


def _get_agent(agent_id: str):
    from app.services.agent_config import get_agent_by_id
    return get_agent_by_id(UUID(agent_id))


# ── Authentication ────────────────────────────────────────────

def generate_login_code(phone: str) -> str:
    """Generate a 6-digit login code for the given phone."""
    code = f"{secrets.randbelow(1000000):06d}"
    _store_login_code(phone, code)
    return code


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "login.html", error=None, message=None)


@router.post("/login")
async def login_submit(request: Request, phone: str = Form(...), code: str = Form("")):
    from app.db.connection import get_async_db_connection

    phone = phone.strip()

    # Look up agent by phone number
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            "SELECT id, phone FROM agents WHERE phone = %s",
            [phone],
        )
        agent = await result.fetchone()

    if not agent:
        return _render(request, "login.html",
            error="No agent account found for this phone number.", message=None)

    if not code:
        # Generate and send a code
        login_code = generate_login_code(phone)
        # In development, show the code directly; in production, send via SMS
        settings = get_settings()
        if settings.ENVIRONMENT == "development":
            return _render(request, "login.html",
                error=None, message=f"Development mode — your code is: {login_code}")
        else:
            try:
                from app.services.twilio_service import send_sms
                # Find agent's Twilio number to send from
                async with get_async_db_connection() as conn:
                    result = await conn.execute(
                        "SELECT twilio_number FROM agents WHERE phone = %s",
                        [phone],
                    )
                    agent_full = await result.fetchone()
                if agent_full:
                    send_sms(
                        to=phone, from_=agent_full["twilio_number"],
                        body=f"Your Calloway login code is: {login_code}",
                        agent_id=agent["id"],
                    )
            except Exception as e:  # Broad catch: mixed Twilio + DB call
                logger.error(f"Failed to send login code: {e}")
            return _render(request, "login.html",
                error=None, message="A verification code has been sent to your phone.")

    # Verify code — rate-limited to prevent brute-forcing the 6-digit code
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = _check_agent_login_rate(client_ip)
    if not allowed:
        return _render(request, "login.html",
            error=f"Too many failed attempts. Please try again in {retry_after // 60} minutes.",
            message=None)

    stored_code = _get_login_code(phone)
    if not stored_code:
        return _render(request, "login.html",
            error="No code found or code expired. Please request a new one.", message=None)

    if stored_code != code.strip():
        _record_agent_login_fail(client_ip)
        return _render(request, "login.html",
            error="Invalid code. Please try again.", message=None)

    # Success — clean up rate limit counter and create session
    _reset_agent_login_rate(client_ip)
    _delete_login_code(phone)
    response = RedirectResponse("/agent/dashboard", status_code=303)
    _create_session(response, str(agent["id"]))
    return response


@router.post("/logout")
async def logout(request: Request):
    """POST-only logout to prevent CSRF via link prefetching or image tags."""
    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err
    response = RedirectResponse("/agent/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── Dashboard ─────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        # Today's stats
        cur = await conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE agent_id = %s AND created_at >= CURRENT_DATE",
            [agent_id],
        )
        messages_today = (await cur.fetchone())["cnt"]

        cur = await conn.execute(
            "SELECT COUNT(*) as cnt FROM showings WHERE agent_id = %s AND start_time::date = CURRENT_DATE",
            [agent_id],
        )
        showings_today = (await cur.fetchone())["cnt"]

        cur = await conn.execute(
            "SELECT COUNT(*) as cnt FROM contacts WHERE agent_id = %s AND lifecycle_stage NOT IN ('closed', 'inactive')",
            [agent_id],
        )
        active_contacts = (await cur.fetchone())["cnt"]

        # Pending approvals (triggers needing agent approval)
        cur = await conn.execute(
            """SELECT t.*, c.name as contact_name
               FROM triggers t
               LEFT JOIN contacts c ON c.id = t.entity_id AND t.entity_type = 'contact'
               WHERE t.agent_id = %s AND t.status = 'pending' AND t.autonomy_level = 'ask_agent'
               ORDER BY t.scheduled_at
               LIMIT 10""",
            [agent_id],
        )
        pending_triggers = await cur.fetchall()

        # Upcoming showings
        cur = await conn.execute(
            """SELECT s.*, l.address as listing_address, c.name as contact_name
               FROM showings s
               JOIN listings l ON l.id = s.listing_id
               JOIN contacts c ON c.id = s.contact_id
               WHERE s.agent_id = %s AND s.start_time > now() AND s.status IN ('confirmed', 'hold')
               ORDER BY s.start_time
               LIMIT 5""",
            [agent_id],
        )
        upcoming = await cur.fetchall()

        # Recent conversations
        cur = await conn.execute(
            """SELECT cv.*, c.name as contact_name,
                      (SELECT body FROM messages WHERE conversation_id = cv.id ORDER BY created_at DESC LIMIT 1) as last_message
               FROM conversations cv
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.agent_id = %s
               ORDER BY cv.last_message_at DESC NULLS LAST
               LIMIT 8""",
            [agent_id],
        )
        conversations = await cur.fetchall()

        # Active listings
        cur = await conn.execute(
            "SELECT * FROM listings WHERE agent_id = %s AND status = 'active' ORDER BY created_at DESC",
            [agent_id],
        )
        listings = await cur.fetchall()

        # Active transactions
        cur = await conn.execute(
            "SELECT COUNT(*) as cnt FROM transactions WHERE agent_id = %s AND status NOT IN ('closed', 'withdrawn', 'expired')",
            [agent_id],
        )
        active_transactions = (await cur.fetchone())["cnt"]

    stats = {
        "messages_today": messages_today,
        "showings_today": showings_today,
        "pending_approvals": len(pending_triggers),
        "active_contacts": active_contacts,
        "active_transactions": active_transactions,
    }

    return _render(request, "dashboard.html",
        page_title="Dashboard", active_nav="dashboard", agent=agent,
        stats=stats, pending_approvals=pending_triggers,
        upcoming_showings=upcoming, recent_conversations=conversations,
        active_listings=listings,
    )


# ── Contacts ──────────────────────────────────────────────────

@router.get("/contacts", response_class=HTMLResponse)
async def contacts_list(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    search = request.query_params.get("search", "")
    role_filter = request.query_params.get("role", "")
    source_filter = request.query_params.get("source", "")

    from app.db.connection import get_async_db_connection

    query = "SELECT * FROM contacts WHERE agent_id = %s"
    params = [agent_id]

    if role_filter:
        query += " AND role = %s"
        params.append(role_filter)

    if source_filter:
        query += " AND lead_source = %s"
        params.append(source_filter)

    if search:
        query += " AND (name ILIKE %s OR phone ILIKE %s OR email ILIKE %s)"
        escaped = f"%{escape_ilike(search)}%"
        params.extend([escaped, escaped, escaped])

    # Pagination — default 50 per page, capped at 200
    page = max(1, int(request.query_params.get("page", "1")))
    per_page = min(200, max(1, int(request.query_params.get("per_page", "50"))))
    offset = (page - 1) * per_page

    query += " ORDER BY last_contact_at DESC NULLS LAST"
    count_query = query.replace("SELECT * FROM", "SELECT count(*) FROM", 1)
    query += " LIMIT %s OFFSET %s"
    params_with_pagination = params + [per_page, offset]

    async with get_async_db_connection() as conn:
        cur = await conn.execute(query, params_with_pagination)
        contacts = await cur.fetchall()

        cur = await conn.execute(count_query, params)
        total_count = (await cur.fetchone())["count"]

        # Get distinct lead sources for filter chips
        cur = await conn.execute(
            "SELECT DISTINCT lead_source FROM contacts WHERE agent_id = %s AND lead_source IS NOT NULL ORDER BY lead_source",
            [agent_id],
        )
        sources = await cur.fetchall()

    lead_sources = [s["lead_source"] for s in sources]
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    return _render(request, "contacts.html",
        page_title="Contacts", active_nav="contacts", agent=agent,
        contacts=contacts, search=search, role_filter=role_filter,
        source_filter=source_filter, lead_sources=lead_sources,
        page=page, total_pages=total_pages, total_count=total_count,
        per_page=per_page,
    )


# ── Conversations ─────────────────────────────────────────────

@router.get("/conversations", response_class=HTMLResponse)
async def conversations_list(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    search = request.query_params.get("search", "")

    from app.db.connection import get_async_db_connection

    query = """SELECT cv.*, c.name as contact_name,
                      (SELECT body FROM messages WHERE conversation_id = cv.id ORDER BY created_at DESC LIMIT 1) as last_message
               FROM conversations cv
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.agent_id = %s"""
    params = [agent_id]

    if search:
        query += " AND c.name ILIKE %s"
        params.append(f"%{escape_ilike(search)}%")

    query += " ORDER BY cv.last_message_at DESC NULLS LAST LIMIT 50"

    async with get_async_db_connection() as conn:
        cur = await conn.execute(query, params)
        conversations = await cur.fetchall()

    return _render(request, "conversations.html",
        page_title="Messages", active_nav="conversations", agent=agent,
        conversations=conversations, search=search,
    )


@router.get("/conversations/{conversation_id}", response_class=HTMLResponse)
async def conversation_detail(request: Request, conversation_id: str):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        cur = await conn.execute(
            """SELECT cv.*, c.name as contact_name, c.phone as contact_phone
               FROM conversations cv
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.id = %s AND cv.agent_id = %s""",
            [conversation_id, agent_id],
        )
        conv = await cur.fetchone()

        if not conv:
            return RedirectResponse("/agent/conversations", status_code=303)

        # Limit to most recent 200 messages to prevent unbounded memory usage
        cur = await conn.execute(
            "SELECT * FROM messages WHERE conversation_id = %s ORDER BY created_at DESC LIMIT 200",
            [conversation_id],
        )
        messages = list(reversed(await cur.fetchall()))

    detail = {
        **conv,
        "messages": messages,
    }

    return _render(request, "conversation_detail.html",
        page_title="Conversation", active_nav="conversations", agent=agent,
        detail=detail,
    )


# ── Schedule ──────────────────────────────────────────────────

@router.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    status_filter = request.query_params.get("status", "")

    from app.db.connection import get_async_db_connection

    base = """SELECT s.*, l.address as listing_address, c.name as contact_name
              FROM showings s
              JOIN listings l ON l.id = s.listing_id
              JOIN contacts c ON c.id = s.contact_id
              WHERE s.agent_id = %s"""
    params = [agent_id]

    if status_filter:
        base += " AND s.status = %s"
        params.append(status_filter)

    async with get_async_db_connection() as conn:
        cur = await conn.execute(
            base + " AND s.start_time::date = CURRENT_DATE ORDER BY s.start_time",
            params,
        )
        today = await cur.fetchall()

        cur = await conn.execute(
            base + " AND s.start_time > CURRENT_DATE ORDER BY s.start_time LIMIT 20",
            params,
        )
        upcoming = await cur.fetchall()

    return _render(request, "schedule.html",
        page_title="Schedule", active_nav="schedule", agent=agent,
        today_showings=today, upcoming_showings=upcoming,
        status_filter=status_filter,
    )


# ── Triggers / Reminders ─────────────────────────────────────

@router.get("/triggers", response_class=HTMLResponse)
async def triggers_list(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    type_filter = request.query_params.get("type", "")

    from app.db.connection import get_async_db_connection

    query = """SELECT t.*, c.name as contact_name
               FROM triggers t
               LEFT JOIN contacts c ON c.id = t.entity_id AND t.entity_type = 'contact'
               WHERE t.agent_id = %s AND t.status IN ('pending', 'completed')"""
    params = [agent_id]

    if type_filter:
        query += " AND t.trigger_type = %s"
        params.append(type_filter)

    query += " ORDER BY t.scheduled_at DESC LIMIT 50"

    async with get_async_db_connection() as conn:
        cur = await conn.execute(query, params)
        triggers = await cur.fetchall()

    return _render(request, "triggers.html",
        page_title="Reminders", active_nav="triggers", agent=agent,
        triggers=triggers, type_filter=type_filter,
    )


# ── Transactions ─────────────────────────────────────────────

@router.get("/transactions", response_class=HTMLResponse)
async def transactions_list(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    status_filter = request.query_params.get("status", "")

    from app.db.connection import get_async_db_connection

    query = """SELECT t.*, c.name as contact_name, l.address as listing_address
               FROM transactions t
               JOIN contacts c ON c.id = t.contact_id
               LEFT JOIN listings l ON l.id = t.listing_id
               WHERE t.agent_id = %s"""
    params = [agent_id]

    if status_filter:
        query += " AND t.status = %s"
        params.append(status_filter)

    query += " ORDER BY t.closing_date ASC NULLS LAST, t.created_at DESC LIMIT 50"

    async with get_async_db_connection() as conn:
        cur = await conn.execute(query, params)
        transactions = await cur.fetchall()

    return _render(request, "transactions.html",
        page_title="Transactions", active_nav="transactions", agent=agent,
        transactions=transactions, status_filter=status_filter,
    )


# ── Lead Scores ─────────────────────────────────────────────

@router.get("/scores", response_class=HTMLResponse)
async def lead_scores(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    from app.tools.lead_scoring import score_all_contacts
    scored_contacts = score_all_contacts(UUID(agent_id))

    return _render(request, "scores.html",
        page_title="Lead Scores", active_nav="scores", agent=agent,
        contacts=scored_contacts,
    )


# ── Drip Campaigns ──────────────────────────────────────────

@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_list(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    from app.tools.drip_campaigns import get_campaigns, get_enrollments

    campaigns = get_campaigns(UUID(agent_id))
    enrollments = get_enrollments(UUID(agent_id))

    return _render(request, "campaigns.html",
        page_title="Campaigns", active_nav="campaigns", agent=agent,
        campaigns=campaigns, enrollments=enrollments,
    )


# ── POST: Approve / Reject Trigger ──────────────────────────

@router.post("/triggers/{trigger_id}/approve", response_class=HTMLResponse)
async def trigger_approve(request: Request, trigger_id: str):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        cur = await conn.execute(
            "UPDATE triggers SET status = 'approved' WHERE id = %s AND agent_id = %s AND status = 'pending' RETURNING id",
            [trigger_id, agent_id],
        )
        result = await cur.fetchone()
        await conn.commit()

    if not result:
        return HTMLResponse('<span class="badge badge-red">Not found</span>')

    # Return HTMX partial for inline swap
    return HTMLResponse(
        '<span class="badge badge-green">Approved</span>'
    )


@router.post("/triggers/{trigger_id}/reject", response_class=HTMLResponse)
async def trigger_reject(request: Request, trigger_id: str):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        cur = await conn.execute(
            "UPDATE triggers SET status = 'cancelled' WHERE id = %s AND agent_id = %s AND status = 'pending' RETURNING id",
            [trigger_id, agent_id],
        )
        result = await cur.fetchone()
        await conn.commit()

    if not result:
        return HTMLResponse('<span class="badge badge-red">Not found</span>')

    return HTMLResponse(
        '<span class="badge badge-gray">Rejected</span>'
    )


# ── POST: Reply to Conversation ──────────────────────────────

@router.post("/conversations/{conversation_id}/reply", response_class=HTMLResponse)
async def conversation_reply(request: Request, conversation_id: str):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    body = (form.get("body") or "").strip()
    if not body:
        return HTMLResponse(
            '<div class="flash flash-error">Message cannot be empty.</div>',
            status_code=422,
        )

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        # Verify conversation belongs to this agent and get contact phone
        cur = await conn.execute(
            """SELECT cv.id, cv.agent_id, c.phone as contact_phone
               FROM conversations cv
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.id = %s AND cv.agent_id = %s""",
            [conversation_id, agent_id],
        )
        conv = await cur.fetchone()

        if not conv:
            return HTMLResponse(
                '<div class="flash flash-error">Conversation not found.</div>',
                status_code=404,
            )

        # Get agent's Twilio number
        cur = await conn.execute(
            "SELECT twilio_number FROM agents WHERE id = %s",
            [agent_id],
        )
        agent_row = await cur.fetchone()

        # Insert the outbound message record
        cur = await conn.execute(
            """INSERT INTO messages (agent_id, conversation_id, sender_type, body, ai_generated, delivery_status)
               VALUES (%s, %s, 'agent', %s, false, 'pending')
               RETURNING id, created_at""",
            [agent_id, conversation_id, body],
        )
        msg = await cur.fetchone()

        # Update conversation last_message_at
        await conn.execute(
            "UPDATE conversations SET last_message_at = %s WHERE id = %s",
            [msg["created_at"], conversation_id],
        )
        await conn.commit()

    # Send via Twilio (non-blocking — if it fails, the message is still recorded)
    if conv["contact_phone"] and agent_row:
        try:
            from app.services.twilio_service import send_sms
            sms_result = send_sms(
                to=conv["contact_phone"],
                from_=agent_row["twilio_number"],
                body=body,
                agent_id=UUID(agent_id),
            )

            # Update delivery status based on Twilio result
            if sms_result.get("sid"):
                async with get_async_db_connection() as conn:
                    await conn.execute(
                        "UPDATE messages SET provider_message_id = %s, delivery_status = %s WHERE id = %s",
                        [sms_result["sid"], sms_result.get("status", "sent"), msg["id"]],
                    )
                    await conn.commit()
        except Exception as e:  # Broad catch: mixed Twilio + DB call
            logger.error(f"SMS send failed for agent reply: {e}")

    # Return HTMX partial — the new message bubble
    time_str = msg["created_at"].strftime('%b %d %I:%M%p').lstrip('0') if msg["created_at"] else ""
    return HTMLResponse(f'''
        <div class="chat-msg chat-outbound">
            {html.escape(body)}
            <div class="chat-time">{html.escape(time_str)} &middot; You</div>
        </div>
    ''')


# ── POST: Edit Contact ───────────────────────────────────────

@router.post("/contacts/{contact_id}/edit", response_class=HTMLResponse)
async def contact_edit(request: Request, contact_id: str):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    email = (form.get("email") or "").strip() or None
    notes = (form.get("notes") or "").strip() or None
    lifecycle_stage = (form.get("lifecycle_stage") or "").strip() or None

    if not name or not phone:
        return HTMLResponse(
            '<div class="flash flash-error">Name and phone are required.</div>',
            status_code=422,
        )

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        cur = await conn.execute(
            """UPDATE contacts
               SET name = %s, phone = %s, email = %s, notes = %s,
                   lifecycle_stage = COALESCE(%s, lifecycle_stage),
                   updated_at = now()
               WHERE id = %s AND agent_id = %s
               RETURNING id, name, phone, email, notes, lifecycle_stage""",
            [name, phone, email, notes, lifecycle_stage, contact_id, agent_id],
        )
        result = await cur.fetchone()
        await conn.commit()

    if not result:
        return HTMLResponse(
            '<div class="flash flash-error">Contact not found.</div>',
            status_code=404,
        )

    return HTMLResponse(
        '<div class="flash flash-success">Contact updated.</div>'
    )


# ── POST: Confirm / Cancel Showing ──────────────────────────

@router.post("/showings/{showing_id}/confirm", response_class=HTMLResponse)
async def showing_confirm(request: Request, showing_id: str):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        cur = await conn.execute(
            """UPDATE showings SET status = 'confirmed', hold_expires_at = NULL
               WHERE id = %s AND agent_id = %s AND status IN ('hold', 'pending')
               RETURNING id""",
            [showing_id, agent_id],
        )
        result = await cur.fetchone()
        await conn.commit()

    if not result:
        return HTMLResponse('<span class="badge badge-red">Not found</span>')

    return HTMLResponse('<span class="badge badge-green">confirmed</span>')


@router.post("/showings/{showing_id}/cancel", response_class=HTMLResponse)
async def showing_cancel(request: Request, showing_id: str):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        cur = await conn.execute(
            """UPDATE showings SET status = 'cancelled'
               WHERE id = %s AND agent_id = %s AND status IN ('hold', 'confirmed', 'pending')
               RETURNING id""",
            [showing_id, agent_id],
        )
        result = await cur.fetchone()
        await conn.commit()

    if not result:
        return HTMLResponse('<span class="badge badge-red">Not found</span>')

    return HTMLResponse('<span class="badge badge-gray">cancelled</span>')


# ── POST: Quick Note on Contact ──────────────────────────────

@router.post("/contacts/{contact_id}/note", response_class=HTMLResponse)
async def contact_add_note(request: Request, contact_id: str):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    note_text = (form.get("note") or "").strip()
    if not note_text:
        return HTMLResponse(
            '<div class="flash flash-error">Note cannot be empty.</div>',
            status_code=422,
        )

    from app.db.connection import get_async_db_connection

    async with get_async_db_connection() as conn:
        # Append to existing notes with timestamp
        cur = await conn.execute(
            """UPDATE contacts
               SET notes = CASE
                   WHEN notes IS NULL OR notes = '' THEN %s
                   ELSE notes || E'\n---\n' || %s
               END,
               updated_at = now()
               WHERE id = %s AND agent_id = %s
               RETURNING id""",
            [note_text, note_text, contact_id, agent_id],
        )
        result = await cur.fetchone()
        await conn.commit()

    if not result:
        return HTMLResponse(
            '<div class="flash flash-error">Contact not found.</div>',
            status_code=404,
        )

    return HTMLResponse(
        '<div class="flash flash-success">Note added.</div>'
    )
