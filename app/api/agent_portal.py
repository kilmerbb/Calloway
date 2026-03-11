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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent-portal"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "agent"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

SESSION_COOKIE = "agent_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days

# In-memory login codes (in production, use Redis)
_login_codes: dict[str, dict] = {}


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


def _get_agent(agent_id: str):
    from app.services.agent_config import get_agent_by_id
    return get_agent_by_id(UUID(agent_id))


# ── Authentication ────────────────────────────────────────────

def generate_login_code(phone: str) -> str:
    """Generate a 6-digit login code for the given phone."""
    code = f"{secrets.randbelow(1000000):06d}"
    _login_codes[phone] = {
        "code": code,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
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
    stored = _login_codes.get(phone)
    if not stored:
        return _render(request, "login.html",
            error="No code found. Please request a new one.", message=None)

    if datetime.now(timezone.utc) > stored["expires_at"]:
        del _login_codes[phone]
        return _render(request, "login.html",
            error="Code expired. Please request a new one.", message=None)

    if stored["code"] != code.strip():
        return _render(request, "login.html",
            error="Invalid code. Please try again.", message=None)

    # Success — clean up and create session
    del _login_codes[phone]
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
