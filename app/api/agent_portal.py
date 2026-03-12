"""Agent Portal — mobile-first dashboard for real estate agents."""
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent-portal"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "agent"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

SESSION_COOKIE = "agent_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days

LOGIN_CODE_TTL = 300  # 5 minutes

# Fallback in-memory store for when Redis is unavailable
_login_codes: dict[str, dict] = {}


def _store_login_code(phone: str, code: str) -> None:
    """Store a login code in Redis, falling back to in-memory dict."""
    try:
        r = get_redis_pool()
        r.setex(f"login_code:{phone}", LOGIN_CODE_TTL, code)
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        logger.warning("Redis unavailable for login code deletion, using in-memory fallback: %s", e)
        _login_codes.pop(phone, None)


def _get_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.CONSOLE_SESSION_SECRET + "-agent")


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
    resp = Response()
    csrf = generate_csrf_token(request, resp)
    ctx["csrf_token"] = csrf
    return templates.TemplateResponse(request, template, ctx)


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
    from app.db.connection import get_db_connection

    phone = phone.strip()

    # Look up agent by phone number
    with get_db_connection() as conn:
        agent = conn.execute(
            "SELECT id, phone FROM agents WHERE phone = %s",
            [phone],
        ).fetchone()

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
                with get_db_connection() as conn:
                    agent_full = conn.execute(
                        "SELECT twilio_number FROM agents WHERE phone = %s",
                        [phone],
                    ).fetchone()
                if agent_full:
                    send_sms(
                        to=phone, from_=agent_full["twilio_number"],
                        body=f"Your Calloway login code is: {login_code}",
                        agent_id=agent["id"],
                    )
            except Exception as e:
                logger.error(f"Failed to send login code: {e}")
            return _render(request, "login.html",
                error=None, message="A verification code has been sent to your phone.")

    # Verify code
    stored_code = _get_login_code(phone)
    if not stored_code:
        return _render(request, "login.html",
            error="No code found or code expired. Please request a new one.", message=None)

    if stored_code != code.strip():
        return _render(request, "login.html",
            error="Invalid code. Please try again.", message=None)

    # Success — clean up and create session
    _delete_login_code(phone)
    response = RedirectResponse("/agent/dashboard", status_code=303)
    _create_session(response, str(agent["id"]))
    return response


@router.get("/logout")
async def logout(request: Request):
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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        # Today's stats
        messages_today = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE agent_id = %s AND created_at >= CURRENT_DATE",
            [agent_id],
        ).fetchone()["cnt"]

        showings_today = conn.execute(
            "SELECT COUNT(*) as cnt FROM showings WHERE agent_id = %s AND start_time::date = CURRENT_DATE",
            [agent_id],
        ).fetchone()["cnt"]

        active_contacts = conn.execute(
            "SELECT COUNT(*) as cnt FROM contacts WHERE agent_id = %s AND lifecycle_stage NOT IN ('closed', 'inactive')",
            [agent_id],
        ).fetchone()["cnt"]

        # Pending approvals (triggers needing agent approval)
        pending_triggers = conn.execute(
            """SELECT t.*, c.name as contact_name
               FROM triggers t
               LEFT JOIN contacts c ON c.id = t.entity_id AND t.entity_type = 'contact'
               WHERE t.agent_id = %s AND t.status = 'pending' AND t.autonomy_level = 'ask_agent'
               ORDER BY t.scheduled_at
               LIMIT 10""",
            [agent_id],
        ).fetchall()

        # Upcoming showings
        upcoming = conn.execute(
            """SELECT s.*, l.address as listing_address, c.name as contact_name
               FROM showings s
               JOIN listings l ON l.id = s.listing_id
               JOIN contacts c ON c.id = s.contact_id
               WHERE s.agent_id = %s AND s.start_time > now() AND s.status IN ('confirmed', 'hold')
               ORDER BY s.start_time
               LIMIT 5""",
            [agent_id],
        ).fetchall()

        # Recent conversations
        conversations = conn.execute(
            """SELECT cv.*, c.name as contact_name,
                      (SELECT body FROM messages WHERE conversation_id = cv.id ORDER BY created_at DESC LIMIT 1) as last_message
               FROM conversations cv
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.agent_id = %s
               ORDER BY cv.last_message_at DESC NULLS LAST
               LIMIT 8""",
            [agent_id],
        ).fetchall()

        # Active listings
        listings = conn.execute(
            "SELECT * FROM listings WHERE agent_id = %s AND status = 'active' ORDER BY created_at DESC",
            [agent_id],
        ).fetchall()

        # Active transactions
        active_transactions = conn.execute(
            "SELECT COUNT(*) as cnt FROM transactions WHERE agent_id = %s AND status NOT IN ('closed', 'withdrawn', 'expired')",
            [agent_id],
        ).fetchone()["cnt"]

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

    from app.db.connection import get_db_connection

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
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    query += " ORDER BY last_contact_at DESC NULLS LAST"

    with get_db_connection() as conn:
        contacts = conn.execute(query, params).fetchall()

        # Get distinct lead sources for filter chips
        sources = conn.execute(
            "SELECT DISTINCT lead_source FROM contacts WHERE agent_id = %s AND lead_source IS NOT NULL ORDER BY lead_source",
            [agent_id],
        ).fetchall()

    lead_sources = [s["lead_source"] for s in sources]

    return _render(request, "contacts.html",
        page_title="Contacts", active_nav="contacts", agent=agent,
        contacts=contacts, search=search, role_filter=role_filter,
        source_filter=source_filter, lead_sources=lead_sources,
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

    from app.db.connection import get_db_connection

    query = """SELECT cv.*, c.name as contact_name,
                      (SELECT body FROM messages WHERE conversation_id = cv.id ORDER BY created_at DESC LIMIT 1) as last_message
               FROM conversations cv
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.agent_id = %s"""
    params = [agent_id]

    if search:
        query += " AND c.name ILIKE %s"
        params.append(f"%{search}%")

    query += " ORDER BY cv.last_message_at DESC NULLS LAST LIMIT 50"

    with get_db_connection() as conn:
        conversations = conn.execute(query, params).fetchall()

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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        conv = conn.execute(
            """SELECT cv.*, c.name as contact_name, c.phone as contact_phone
               FROM conversations cv
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.id = %s AND cv.agent_id = %s""",
            [conversation_id, agent_id],
        ).fetchone()

        if not conv:
            return RedirectResponse("/agent/conversations", status_code=303)

        messages = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = %s ORDER BY created_at",
            [conversation_id],
        ).fetchall()

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

    from app.db.connection import get_db_connection

    base = """SELECT s.*, l.address as listing_address, c.name as contact_name
              FROM showings s
              JOIN listings l ON l.id = s.listing_id
              JOIN contacts c ON c.id = s.contact_id
              WHERE s.agent_id = %s"""
    params = [agent_id]

    if status_filter:
        base += " AND s.status = %s"
        params.append(status_filter)

    with get_db_connection() as conn:
        today = conn.execute(
            base + " AND s.start_time::date = CURRENT_DATE ORDER BY s.start_time",
            params,
        ).fetchall()

        upcoming = conn.execute(
            base + " AND s.start_time > CURRENT_DATE ORDER BY s.start_time LIMIT 20",
            params,
        ).fetchall()

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

    from app.db.connection import get_db_connection

    query = """SELECT t.*, c.name as contact_name
               FROM triggers t
               LEFT JOIN contacts c ON c.id = t.entity_id AND t.entity_type = 'contact'
               WHERE t.agent_id = %s AND t.status IN ('pending', 'completed')"""
    params = [agent_id]

    if type_filter:
        query += " AND t.trigger_type = %s"
        params.append(type_filter)

    query += " ORDER BY t.scheduled_at DESC LIMIT 50"

    with get_db_connection() as conn:
        triggers = conn.execute(query, params).fetchall()

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

    from app.db.connection import get_db_connection

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

    with get_db_connection() as conn:
        transactions = conn.execute(query, params).fetchall()

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


# ── Analytics ──────────────────────────────────────────────

def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    if not seconds or seconds == 0:
        return "--"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if minutes:
        return f"{hours}h {minutes}m"
    return f"{hours}h"


@router.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request):
    agent_id, redirect = _require_agent(request)
    if redirect:
        return redirect

    agent = _get_agent(agent_id)
    if not agent:
        return RedirectResponse("/agent/login", status_code=303)

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        # ── KPI 1: Average response time (today, 7d, 30d) ──
        # Time between inbound (contact) message and next outbound response
        response_time_query = """
            WITH response_pairs AS (
                SELECT
                    m_in.conversation_id,
                    m_in.created_at AS inbound_at,
                    (
                        SELECT MIN(m_out.created_at)
                        FROM messages m_out
                        WHERE m_out.conversation_id = m_in.conversation_id
                          AND m_out.agent_id = %s
                          AND m_out.sender_type IN ('assistant', 'agent')
                          AND m_out.created_at > m_in.created_at
                          AND m_out.created_at < m_in.created_at + INTERVAL '24 hours'
                    ) AS response_at
                FROM messages m_in
                WHERE m_in.agent_id = %s
                  AND m_in.sender_type = 'contact'
                  AND m_in.created_at >= CURRENT_DATE - INTERVAL '30 days'
            )
            SELECT
                COALESCE(AVG(EXTRACT(EPOCH FROM response_at - inbound_at))
                    FILTER (WHERE inbound_at >= CURRENT_DATE), 0) AS avg_today,
                COALESCE(AVG(EXTRACT(EPOCH FROM response_at - inbound_at))
                    FILTER (WHERE inbound_at >= CURRENT_DATE - INTERVAL '7 days'), 0) AS avg_7d,
                COALESCE(AVG(EXTRACT(EPOCH FROM response_at - inbound_at)), 0) AS avg_30d
            FROM response_pairs
            WHERE response_at IS NOT NULL
        """
        rt = conn.execute(response_time_query, [agent_id, agent_id]).fetchone()
        response_times = {
            "today": _format_duration(rt["avg_today"]),
            "7d": _format_duration(rt["avg_7d"]),
            "30d": _format_duration(rt["avg_30d"]),
        }

        # ── KPI 2: Active conversations (unique contacts in 7d/30d) ──
        active_convos = conn.execute(
            """
            SELECT
                COUNT(DISTINCT contact_id) FILTER (
                    WHERE last_message_at >= CURRENT_DATE - INTERVAL '7 days'
                ) AS active_7d,
                COUNT(DISTINCT contact_id) FILTER (
                    WHERE last_message_at >= CURRENT_DATE - INTERVAL '30 days'
                ) AS active_30d
            FROM conversations
            WHERE agent_id = %s
              AND contact_id IS NOT NULL
              AND last_message_at >= CURRENT_DATE - INTERVAL '30 days'
            """,
            [agent_id],
        ).fetchone()

        # ── KPI 3: Showings this week + last week with status breakdown ──
        showings_stats = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE start_time >= date_trunc('week', CURRENT_DATE)
                ) AS this_week,
                COUNT(*) FILTER (
                    WHERE start_time >= date_trunc('week', CURRENT_DATE) - INTERVAL '7 days'
                      AND start_time < date_trunc('week', CURRENT_DATE)
                ) AS last_week,
                COUNT(*) FILTER (
                    WHERE start_time >= date_trunc('week', CURRENT_DATE) AND status = 'confirmed'
                ) AS confirmed,
                COUNT(*) FILTER (
                    WHERE start_time >= date_trunc('week', CURRENT_DATE) AND status = 'completed'
                ) AS completed,
                COUNT(*) FILTER (
                    WHERE start_time >= date_trunc('week', CURRENT_DATE) AND status = 'cancelled'
                ) AS cancelled
            FROM showings
            WHERE agent_id = %s
              AND start_time >= date_trunc('week', CURRENT_DATE) - INTERVAL '7 days'
            """,
            [agent_id],
        ).fetchone()

        # ── KPI 4: Lead pipeline by lifecycle stage ──
        pipeline = conn.execute(
            """
            SELECT lifecycle_stage, COUNT(*) AS cnt
            FROM contacts
            WHERE agent_id = %s
            GROUP BY lifecycle_stage
            ORDER BY CASE lifecycle_stage
                WHEN 'new_lead' THEN 1
                WHEN 'active' THEN 2
                WHEN 'under_contract' THEN 3
                WHEN 'closed' THEN 4
                WHEN 'past_client' THEN 5
                ELSE 6
            END
            """,
            [agent_id],
        ).fetchall()
        pipeline_data = {row["lifecycle_stage"]: row["cnt"] for row in pipeline}
        pipeline_total = sum(pipeline_data.values())

        # ── Conversation volume: messages per day (last 30 days) ──
        volume = conn.execute(
            """
            SELECT
                d.day::date AS day,
                COALESCE(SUM(CASE WHEN m.sender_type = 'contact' THEN 1 ELSE 0 END), 0) AS received,
                COALESCE(SUM(CASE WHEN m.sender_type IN ('assistant', 'agent') THEN 1 ELSE 0 END), 0) AS sent
            FROM generate_series(
                CURRENT_DATE - INTERVAL '29 days',
                CURRENT_DATE,
                '1 day'
            ) AS d(day)
            LEFT JOIN messages m
                ON m.agent_id = %s
                AND m.created_at::date = d.day::date
            GROUP BY d.day
            ORDER BY d.day
            """,
            [agent_id],
        ).fetchall()

        volume_max = max(
            (row["received"] + row["sent"] for row in volume),
            default=1,
        )
        if volume_max == 0:
            volume_max = 1

        volume_data = []
        for row in volume:
            total = row["received"] + row["sent"]
            volume_data.append({
                "day": row["day"],
                "received": row["received"],
                "sent": row["sent"],
                "total": total,
                "pct": round(total / volume_max * 100),
                "sent_pct": round(row["sent"] / volume_max * 100),
                "received_pct": round(row["received"] / volume_max * 100),
            })

        # ── Trigger performance (last 7 days) ──
        triggers_perf = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'completed') AS delivered,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending
            FROM triggers
            WHERE agent_id = %s
              AND scheduled_at >= CURRENT_DATE - INTERVAL '7 days'
            """,
            [agent_id],
        ).fetchone()

        # ── AI cost from usage_metrics (today, 7d, 30d) ──
        ai_cost = conn.execute(
            """
            SELECT
                COALESCE(SUM(llm_tokens_used) FILTER (WHERE date = CURRENT_DATE), 0) AS tokens_today,
                COALESCE(SUM(llm_cost_cents) FILTER (WHERE date = CURRENT_DATE), 0) AS cost_today,
                COALESCE(SUM(llm_tokens_used) FILTER (
                    WHERE date >= CURRENT_DATE - INTERVAL '6 days'
                ), 0) AS tokens_7d,
                COALESCE(SUM(llm_cost_cents) FILTER (
                    WHERE date >= CURRENT_DATE - INTERVAL '6 days'
                ), 0) AS cost_7d,
                COALESCE(SUM(llm_tokens_used), 0) AS tokens_30d,
                COALESCE(SUM(llm_cost_cents), 0) AS cost_30d
            FROM usage_metrics
            WHERE agent_id = %s
              AND date >= CURRENT_DATE - INTERVAL '29 days'
            """,
            [agent_id],
        ).fetchone()

    return _render(request, "analytics.html",
        page_title="Analytics", active_nav="analytics", agent=agent,
        response_times=response_times,
        active_convos={"7d": active_convos["active_7d"], "30d": active_convos["active_30d"]},
        showings=showings_stats,
        pipeline=pipeline_data,
        pipeline_total=pipeline_total,
        volume=volume_data,
        volume_max=volume_max,
        triggers=triggers_perf,
        ai_cost=ai_cost,
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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        result = conn.execute(
            "UPDATE triggers SET status = 'approved' WHERE id = %s AND agent_id = %s AND status = 'pending' RETURNING id",
            [trigger_id, agent_id],
        ).fetchone()
        conn.commit()

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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        result = conn.execute(
            "UPDATE triggers SET status = 'cancelled' WHERE id = %s AND agent_id = %s AND status = 'pending' RETURNING id",
            [trigger_id, agent_id],
        ).fetchone()
        conn.commit()

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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        # Verify conversation belongs to this agent and get contact phone
        conv = conn.execute(
            """SELECT cv.id, cv.agent_id, c.phone as contact_phone
               FROM conversations cv
               LEFT JOIN contacts c ON c.id = cv.contact_id
               WHERE cv.id = %s AND cv.agent_id = %s""",
            [conversation_id, agent_id],
        ).fetchone()

        if not conv:
            return HTMLResponse(
                '<div class="flash flash-error">Conversation not found.</div>',
                status_code=404,
            )

        # Get agent's Twilio number
        agent_row = conn.execute(
            "SELECT twilio_number FROM agents WHERE id = %s",
            [agent_id],
        ).fetchone()

        # Insert the outbound message record
        msg = conn.execute(
            """INSERT INTO messages (agent_id, conversation_id, sender_type, body, ai_generated, delivery_status)
               VALUES (%s, %s, 'agent', %s, false, 'pending')
               RETURNING id, created_at""",
            [agent_id, conversation_id, body],
        ).fetchone()

        # Update conversation last_message_at
        conn.execute(
            "UPDATE conversations SET last_message_at = %s WHERE id = %s",
            [msg["created_at"], conversation_id],
        )
        conn.commit()

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
                with get_db_connection() as conn:
                    conn.execute(
                        "UPDATE messages SET provider_message_id = %s, delivery_status = %s WHERE id = %s",
                        [sms_result["sid"], sms_result.get("status", "sent"), msg["id"]],
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"SMS send failed for agent reply: {e}")

    # Return HTMX partial — the new message bubble
    time_str = msg["created_at"].strftime('%b %d %I:%M%p').lstrip('0') if msg["created_at"] else ""
    return HTMLResponse(f'''
        <div class="chat-msg chat-outbound">
            {body}
            <div class="chat-time">{time_str} &middot; You</div>
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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        result = conn.execute(
            """UPDATE contacts
               SET name = %s, phone = %s, email = %s, notes = %s,
                   lifecycle_stage = COALESCE(%s, lifecycle_stage),
                   updated_at = now()
               WHERE id = %s AND agent_id = %s
               RETURNING id, name, phone, email, notes, lifecycle_stage""",
            [name, phone, email, notes, lifecycle_stage, contact_id, agent_id],
        ).fetchone()
        conn.commit()

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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        result = conn.execute(
            """UPDATE showings SET status = 'confirmed', hold_expires_at = NULL
               WHERE id = %s AND agent_id = %s AND status IN ('hold', 'pending')
               RETURNING id""",
            [showing_id, agent_id],
        ).fetchone()
        conn.commit()

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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        result = conn.execute(
            """UPDATE showings SET status = 'cancelled'
               WHERE id = %s AND agent_id = %s AND status IN ('hold', 'confirmed', 'pending')
               RETURNING id""",
            [showing_id, agent_id],
        ).fetchone()
        conn.commit()

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

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        # Append to existing notes with timestamp
        result = conn.execute(
            """UPDATE contacts
               SET notes = CASE
                   WHEN notes IS NULL OR notes = '' THEN %s
                   ELSE notes || E'\n---\n' || %s
               END,
               updated_at = now()
               WHERE id = %s AND agent_id = %s
               RETURNING id""",
            [note_text, note_text, contact_id, agent_id],
        ).fetchone()
        conn.commit()

    if not result:
        return HTMLResponse(
            '<div class="flash flash-error">Contact not found.</div>',
            status_code=404,
        )

    return HTMLResponse(
        '<div class="flash flash-success">Note added.</div>'
    )


# ── Push Notification Device Tokens ──────────────────────────

@router.post("/devices/register")
async def register_device(request: Request):
    """Register an FCM device token for push notifications.

    Accepts JSON: {fcm_token: str, device_name?: str, platform?: str}
    Called by the frontend JS after obtaining the FCM token from Firebase.
    """
    agent_id, redirect = _require_agent(request)
    if redirect:
        return Response("Unauthorized", status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return Response("Invalid JSON", status_code=400)

    fcm_token = (payload.get("fcm_token") or "").strip()
    if not fcm_token:
        return Response("fcm_token is required", status_code=400)

    device_name = payload.get("device_name")
    platform = payload.get("platform")

    from app.services.firebase_service import register_device_token

    result = register_device_token(
        agent_id=UUID(agent_id),
        fcm_token=fcm_token,
        device_name=device_name,
        platform=platform,
    )

    return {"ok": True, "device_token_id": str(result.get("id", ""))}


@router.post("/devices/unregister")
async def unregister_device(request: Request):
    """Unregister an FCM device token (e.g. on logout).

    Accepts JSON: {fcm_token: str}
    """
    agent_id, redirect = _require_agent(request)
    if redirect:
        return Response("Unauthorized", status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return Response("Invalid JSON", status_code=400)

    fcm_token = (payload.get("fcm_token") or "").strip()
    if not fcm_token:
        return Response("fcm_token is required", status_code=400)

    from app.services.firebase_service import unregister_device_token

    unregister_device_token(fcm_token)

    return {"ok": True}
