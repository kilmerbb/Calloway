"""Operator Console — web-based admin interface for system operators."""
import logging
from pathlib import Path

import markdown
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.api.console_auth import (
    verify_password, create_session, check_session, clear_session,
    generate_csrf_token, validate_csrf_token,
    check_rate_limit, record_failed_attempt, reset_rate_limit,
    log_audit,
)
import psycopg

from app.services.console_queries import set_console_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/console", tags=["console"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "console"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _render(request: Request, template: str, response: Response | None = None, **ctx):
    """Render a template with CSRF token injected."""
    tmp = Response()
    csrf = generate_csrf_token(request, tmp)
    ctx["csrf_token"] = csrf
    # Inject current user info from session for templates (e.g. display name, role)
    if "current_user" not in ctx:
        user_info = check_session(request)
        ctx["current_user"] = user_info
    resp = templates.TemplateResponse(request, template, ctx)
    for header_value in tmp.headers.getlist("set-cookie"):
        resp.headers.append("set-cookie", header_value)
    return resp


def _safe_int(value: str | None, default: int, min_val: int = 1, max_val: int = 500) -> int:
    """Parse a query param as int with safe defaults and clamping."""
    try:
        return max(min_val, min(int(value or default), max_val))
    except (ValueError, TypeError):
        return default


def _require_auth(request: Request) -> dict | RedirectResponse:
    """Return user info dict if authenticated, or a redirect to login.

    On success, sets the console auth context so that downstream query
    functions (guarded by ``@console_authorized``) can execute.
    """
    user_info = check_session(request)
    if not user_info:
        return RedirectResponse("/console/login", status_code=303)
    set_console_context({"source": "console", "ip": request.client.host, **user_info})
    return user_info


def _require_admin(user_info: dict) -> Response | None:
    """Return 403 if user is not an admin. Returns None if OK."""
    if user_info.get("role") != "admin":
        return Response("Forbidden — admin role required", status_code=403)
    return None


def _check_csrf(request: Request, csrf_token: str | None) -> Response | None:
    """Return 403 if CSRF token is invalid, else None."""
    if not validate_csrf_token(request, csrf_token):
        return Response("CSRF validation failed", status_code=403)
    return None


def _client_ip(request: Request) -> str:
    """Extract client IP from request."""
    return request.client.host if request.client else "unknown"


def _render_markdown(filepath: Path) -> str | None:
    """Read a markdown file and convert to HTML. Returns None if file missing."""
    if not filepath.is_file():
        return None
    text = filepath.read_text(encoding="utf-8")
    return markdown.markdown(text, extensions=["fenced_code", "tables", "toc"])


# ============================================================
# Auth routes
# ============================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "login.html", error=None)


@router.post("/login")
async def login_submit(
    request: Request,
    password: str = Form(...),
    email: str = Form(default=None),
):
    ip = _client_ip(request)
    allowed, retry_after = check_rate_limit(ip)
    if not allowed:
        return Response(
            "Too many login attempts. Please try again later.",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    user_info = verify_password(password, email=email if email else None)
    if user_info:
        reset_rate_limit(ip)
        response = RedirectResponse("/console/dashboard", status_code=303)
        create_session(response, user_info)
        log_audit(
            user_id=user_info.get("user_id"),
            action="login",
            ip_address=ip,
            metadata={"email": user_info.get("email"), "mode": "per_user" if user_info.get("user_id") else "legacy"},
        )
        return response

    record_failed_attempt(ip)
    log_audit(
        user_id=None,
        action="login_failed",
        ip_address=ip,
        metadata={"email": email},
    )
    return _render(request, "login.html", error="Invalid credentials.")


@router.get("/logout")
async def logout(request: Request):
    user_info = check_session(request)
    if user_info:
        log_audit(
            user_id=user_info.get("user_id"),
            action="logout",
            ip_address=_client_ip(request),
        )
    response = RedirectResponse("/console/login", status_code=303)
    clear_session(response)
    return response


# ============================================================
# Dashboard
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def console_root(request: Request):
    return RedirectResponse("/console/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import (
        get_system_pulse, get_recent_activity, get_agents_needing_attention,
    )

    return _render(request, "dashboard.html",
        page_title="Home", active_nav="dashboard",
        pulse=await get_system_pulse(),
        activity=await get_recent_activity(limit=20),
        attention=await get_agents_needing_attention(),
    )


@router.get("/dashboard/activity-feed", response_class=HTMLResponse)
async def dashboard_activity_feed(request: Request):
    """HTMX partial: refreshable activity feed."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_recent_activity
    return _render(request, "partials/activity_feed.html",
        activity=await get_recent_activity(limit=20),
    )


# ============================================================
# Onboarding Wizard
# ============================================================

@router.get("/onboard", response_class=HTMLResponse)
async def onboard_wizard(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth
    return _render(request, "onboard_wizard.html",
        page_title="Onboard New Agent", active_nav="onboard", error=None,
    )


@router.post("/onboard")
async def onboard_submit(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import create_agent_from_wizard

    try:
        result = create_agent_from_wizard(dict(form))
        log_audit(
            user_id=auth.get("user_id"),
            action="onboard_agent",
            target_entity="agent",
            target_id=result["agent_id"],
            ip_address=_client_ip(request),
        )
        return _render(request, "onboard_success.html",
            page_title="Onboarding Complete", active_nav="onboard",
            agent_id=result["agent_id"],
            agent_name=result["agent_name"],
            checklist=result["checklist"],
        )
    except ValueError as e:
        return _render(request, "onboard_wizard.html",
            page_title="Onboard New Agent", active_nav="onboard", error=str(e),
        )


# ============================================================
# Tenants
# ============================================================

@router.get("/tenants", response_class=HTMLResponse)
async def tenant_list(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_all_agents
    agents = await get_all_agents()

    search = request.query_params.get("search", "")
    sort_by = request.query_params.get("sort", "name")
    if search:
        agents = [a for a in agents if search.lower() in a["name"].lower()
                  or search.lower() in (a.get("market") or "").lower()]

    # Support JSON response for HTMX/JS consumers
    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        from fastapi.responses import JSONResponse
        return JSONResponse([{"id": str(a["id"]), "name": a["name"]} for a in agents])

    return _render(request, "tenants.html",
        page_title="Customers", active_nav="tenants",
        agents=agents, search=search, sort_by=sort_by,
    )


@router.get("/tenants/new", response_class=HTMLResponse)
async def tenant_new_form(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth
    return _render(request, "tenant_new.html",
        page_title="New Customer", active_nav="tenants", error=None,
    )


@router.post("/tenants/new")
async def tenant_create(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import create_agent_tenant

    try:
        agent_id = create_agent_tenant(dict(form))
        log_audit(
            user_id=auth.get("user_id"),
            action="create_tenant",
            target_entity="agent",
            target_id=str(agent_id),
            ip_address=_client_ip(request),
        )
        return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)
    except ValueError as e:
        return _render(request, "tenant_new.html",
            page_title="New Customer", active_nav="tenants", error=str(e),
        )


@router.get("/tenants/{agent_id}", response_class=HTMLResponse)
async def tenant_detail(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_agent_detail
    detail = await get_agent_detail(agent_id)
    if not detail:
        return RedirectResponse("/console/tenants", status_code=303)

    return _render(request, "tenant_detail.html",
        page_title=f"Customer: {detail['agent']['name']}",
        active_nav="tenants", detail=detail,
    )


@router.get("/tenants/{agent_id}/edit", response_class=HTMLResponse)
async def tenant_edit_form(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_agent_basic
    agent = await get_agent_basic(agent_id)
    if not agent:
        return RedirectResponse("/console/tenants", status_code=303)

    return _render(request, "tenant_edit.html",
        page_title=f"Edit Customer: {agent['name']}",
        active_nav="tenants", agent=agent, error=None,
    )


@router.post("/tenants/{agent_id}/edit")
async def tenant_update(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import update_agent_tenant

    try:
        update_agent_tenant(agent_id, dict(form))
        log_audit(
            user_id=auth.get("user_id"),
            action="update_tenant",
            target_entity="agent",
            target_id=agent_id,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)
    except ValueError as e:
        from app.services.console_queries import get_agent_basic
        agent = await get_agent_basic(agent_id)
        return _render(request, "tenant_edit.html",
            page_title=f"Edit Customer: {agent['name']}",
            active_nav="tenants", agent=agent, error=str(e),
        )


@router.post("/tenants/{agent_id}/deactivate")
async def tenant_deactivate(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import deactivate_agent
    await deactivate_agent(agent_id)
    log_audit(
        user_id=auth.get("user_id"),
        action="deactivate_tenant",
        target_entity="agent",
        target_id=agent_id,
        ip_address=_client_ip(request),
    )
    return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)


@router.post("/tenants/{agent_id}/test-sms")
async def tenant_test_sms(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import send_test_sms
    try:
        send_test_sms(agent_id)
        log_audit(
            user_id=auth.get("user_id"),
            action="send_test_sms",
            target_entity="agent",
            target_id=agent_id,
            ip_address=_client_ip(request),
        )
    except Exception as e:  # Broad catch: mixed DB + Twilio call
        logger.error(f"Test SMS failed: {e}")
    return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)


# ============================================================
# Conversations
# ============================================================

@router.get("/conversations", response_class=HTMLResponse)
async def conversation_list(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_recent_conversations, get_agent_options

    agent_filter = request.query_params.get("agent", "")
    channel_filter = request.query_params.get("channel", "")
    search = request.query_params.get("search", "")
    page = _safe_int(request.query_params.get("page"), 1)
    per_page = _safe_int(request.query_params.get("per_page"), 25, max_val=100)
    offset = (page - 1) * per_page

    conversations = await get_recent_conversations(
        agent_id=agent_filter or None,
        channel=channel_filter or None,
        search=search or None,
        limit=per_page,
        offset=offset,
    )

    return _render(request, "conversations.html",
        page_title="Messages", active_nav="conversations",
        conversations=conversations,
        agents=await get_agent_options(),
        agent_filter=agent_filter, channel_filter=channel_filter, search=search,
        page=page, per_page=per_page,
        has_more=len(conversations) == per_page,
    )


@router.get("/conversations/{conversation_id}", response_class=HTMLResponse)
async def conversation_detail(request: Request, conversation_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_conversation_detail
    detail = await get_conversation_detail(conversation_id)
    if not detail:
        return RedirectResponse("/console/conversations", status_code=303)

    return _render(request, "conversation_detail.html",
        page_title="Conversation", active_nav="conversations", detail=detail,
    )


# ============================================================
# Triggers
# ============================================================

@router.get("/triggers", response_class=HTMLResponse)
async def trigger_list(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_trigger_queue, get_agent_options

    status_filter = request.query_params.get("status", "pending")
    agent_filter = request.query_params.get("agent", "")
    page = _safe_int(request.query_params.get("page"), 1)
    per_page = _safe_int(request.query_params.get("per_page"), 50, max_val=500)
    offset = (page - 1) * per_page

    triggers = await get_trigger_queue(
        status=status_filter if status_filter != "all" else None,
        agent_id=agent_filter or None,
        limit=per_page,
        offset=offset,
    )

    return _render(request, "triggers.html",
        page_title="Automations", active_nav="triggers",
        triggers=triggers,
        agents=await get_agent_options(),
        status_filter=status_filter, agent_filter=agent_filter,
        page=page, per_page=per_page,
        has_more=len(triggers) == per_page,
    )


@router.post("/triggers/{trigger_id}/retry")
async def trigger_retry(request: Request, trigger_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import retry_trigger
    await retry_trigger(trigger_id)
    log_audit(
        user_id=auth.get("user_id"),
        action="retry_trigger",
        target_entity="trigger",
        target_id=trigger_id,
        ip_address=_client_ip(request),
    )
    return RedirectResponse("/console/triggers", status_code=303)


@router.post("/triggers/{trigger_id}/cancel")
async def trigger_cancel(request: Request, trigger_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import cancel_trigger
    await cancel_trigger(trigger_id)
    log_audit(
        user_id=auth.get("user_id"),
        action="cancel_trigger",
        target_entity="trigger",
        target_id=trigger_id,
        ip_address=_client_ip(request),
    )
    return RedirectResponse("/console/triggers", status_code=303)


@router.post("/triggers/{trigger_id}/fire-now")
async def trigger_fire_now(request: Request, trigger_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import fire_trigger_now
    await fire_trigger_now(trigger_id)
    log_audit(
        user_id=auth.get("user_id"),
        action="fire_trigger_now",
        target_entity="trigger",
        target_id=trigger_id,
        ip_address=_client_ip(request),
    )
    return RedirectResponse("/console/triggers", status_code=303)


# ============================================================
# Errors (redirect to Health)
# ============================================================

@router.get("/errors")
async def error_list_redirect(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth
    return RedirectResponse(url="/console/health?tab=errors", status_code=302)


# ============================================================
# Costs (redirect to Billing)
# ============================================================

@router.get("/costs")
async def cost_dashboard_redirect(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth
    return RedirectResponse(url="/console/billing?tab=ai-costs", status_code=302)


# ============================================================
# Health
# ============================================================

@router.get("/health", response_class=HTMLResponse)
async def health_overview(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    import asyncio
    from app.services.console_queries import (
        get_health_overview, get_agent_options, get_recent_errors,
    )

    agent_filter = request.query_params.get("agent", "")
    active_tab = request.query_params.get("tab", "services")

    health, agents, errors = await asyncio.gather(
        get_health_overview(),
        get_agent_options(),
        get_recent_errors(limit=100, agent_id=agent_filter or None),
    )

    return _render(request, "health.html",
        page_title="System Health", active_nav="health",
        health=health, agents=agents, errors=errors,
        agent_filter=agent_filter,
        active_tab=active_tab,
    )


@router.get("/health/status-dot", response_class=HTMLResponse)
async def health_status_dot(request: Request):
    """HTMX partial: health status indicator."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_health_status_color
    color = await get_health_status_color()
    return HTMLResponse(
        f'<span class="status-dot status-{color}" title="System {color}"></span>'
    )


@router.post("/health/run-scan/{agent_id}")
async def manual_daily_scan(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import run_manual_scan
    run_manual_scan(agent_id)
    log_audit(
        user_id=auth.get("user_id"),
        action="run_manual_scan",
        target_entity="agent",
        target_id=agent_id,
        ip_address=_client_ip(request),
    )
    return RedirectResponse("/console/health", status_code=303)


# ============================================================
# Billing
# ============================================================

@router.get("/billing", response_class=HTMLResponse)
async def billing_overview(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.billing_service import get_billing_summary, PLAN_TIERS
    from app.services.console_queries import (
        get_cost_summary, get_cost_by_agent, get_model_tier_breakdown,
    )

    active_tab = request.query_params.get("tab", "subscriptions")

    return _render(request, "billing.html",
        page_title="Billing", active_nav="billing",
        subscriptions=get_billing_summary(),
        plan_tiers=PLAN_TIERS,
        cost_summary=await get_cost_summary(days=30),
        per_agent=await get_cost_by_agent(days=30),
        model_tiers=await get_model_tier_breakdown(days=30),
        active_tab=active_tab,
    )


@router.post("/billing/{agent_id}/change-plan")
async def billing_change_plan(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    new_tier = form.get("plan_tier")
    if not new_tier:
        return RedirectResponse("/console/billing", status_code=303)

    from uuid import UUID
    from app.services.billing_service import change_plan
    try:
        change_plan(UUID(agent_id), new_tier)
        log_audit(
            user_id=auth.get("user_id"),
            action="change_plan",
            target_entity="agent",
            target_id=agent_id,
            ip_address=_client_ip(request),
            metadata={"new_tier": new_tier},
        )
    except Exception as e:  # Broad catch: mixed Stripe API + DB call
        logger.error(f"Plan change failed: {e}")

    return RedirectResponse("/console/billing", status_code=303)


@router.post("/billing/{agent_id}/cancel")
async def billing_cancel(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from uuid import UUID
    from app.services.billing_service import cancel_subscription
    try:
        cancel_subscription(UUID(agent_id))
        log_audit(
            user_id=auth.get("user_id"),
            action="cancel_subscription",
            target_entity="agent",
            target_id=agent_id,
            ip_address=_client_ip(request),
        )
    except Exception as e:  # Broad catch: mixed Stripe API + DB call
        logger.error(f"Subscription cancellation failed: {e}")

    return RedirectResponse("/console/billing", status_code=303)


# ============================================================
# User Manual
# ============================================================

@router.get("/manual", response_class=HTMLResponse)
async def user_manual(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    return _render(request, "manual.html",
        page_title="Help", active_nav="manual",
    )


# ============================================================
# Customer Detail — Messages Tab
# ============================================================

@router.get("/tenants/{agent_id}/tab/messages", response_class=HTMLResponse)
async def tenant_messages_tab(request: Request, agent_id: str):
    """HTMX partial: Messages tab — contact list with conversation summaries."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_conversations_by_contact

    page = _safe_int(request.query_params.get("page"), 1)
    per_page = _safe_int(request.query_params.get("per_page"), 25, max_val=100)
    offset = (page - 1) * per_page

    contacts = await get_conversations_by_contact(
        agent_id, limit=per_page, offset=offset,
    )

    return _render(request, "partials/tenant_messages_tab.html",
        agent_id=agent_id, contacts=contacts,
        page=page, per_page=per_page,
        has_more=len(contacts) == per_page,
    )


@router.get("/tenants/{agent_id}/tab/messages/{contact_id}", response_class=HTMLResponse)
async def tenant_messages_thread(request: Request, agent_id: str, contact_id: str):
    """HTMX partial: expanded conversation thread for a contact."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_conversation_thread

    page = _safe_int(request.query_params.get("page"), 1)
    per_page = 50
    offset = (page - 1) * per_page

    thread = await get_conversation_thread(
        agent_id, contact_id, limit=per_page, offset=offset,
    )

    return _render(request, "partials/tenant_messages_thread.html",
        agent_id=agent_id, contact_id=contact_id,
        messages=thread["messages"],
        total_tool_executions=thread["total_tool_executions"],
        page=page, per_page=per_page,
        has_more=len(thread["messages"]) == per_page,
    )


# ============================================================
# Customer Detail — Contacts Tab (PERF-008)
# ============================================================

@router.get("/tenants/{agent_id}/tab/contacts", response_class=HTMLResponse)
async def tenant_contacts_tab(request: Request, agent_id: str):
    """HTMX partial: paginated contacts list."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_agent_contacts_paginated

    page = _safe_int(request.query_params.get("page"), 1)
    per_page = 25
    offset = (page - 1) * per_page

    contacts = await get_agent_contacts_paginated(
        agent_id, limit=per_page, offset=offset,
    )

    return _render(request, "partials/tenant_contacts_list.html",
        agent_id=agent_id, contacts=contacts,
        page=page, per_page=per_page,
        has_more=len(contacts) == per_page,
    )


# ============================================================
# Customer Detail — Listings Tab (PERF-008)
# ============================================================

@router.get("/tenants/{agent_id}/tab/listings", response_class=HTMLResponse)
async def tenant_listings_tab(request: Request, agent_id: str):
    """HTMX partial: paginated listings list."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import get_agent_listings_paginated

    page = _safe_int(request.query_params.get("page"), 1)
    per_page = 25
    offset = (page - 1) * per_page

    listings = await get_agent_listings_paginated(
        agent_id, limit=per_page, offset=offset,
    )

    return _render(request, "partials/tenant_listings_list.html",
        agent_id=agent_id, listings=listings,
        page=page, per_page=per_page,
        has_more=len(listings) == per_page,
    )


# ============================================================
# Customer Detail — Knowledge Base Tab
# ============================================================

@router.get("/tenants/{agent_id}/tab/knowledge-base", response_class=HTMLResponse)
async def tenant_kb_tab(request: Request, agent_id: str):
    """HTMX partial: Knowledge Base tab — items grouped by source type."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    from app.services.console_queries import (
        get_knowledge_base_items, get_kb_settings,
    )

    items = await get_knowledge_base_items(agent_id)
    settings = await get_kb_settings(agent_id)

    # Group items by source_type for display
    grouped = {}
    for item in items:
        st = item["source_type"]
        if st not in grouped:
            grouped[st] = []
        grouped[st].append(item)

    total_chunks = sum(item["chunk_count"] for item in items)

    return _render(request, "partials/tenant_kb_tab.html",
        agent_id=agent_id,
        grouped_items=grouped,
        total_items=len(items),
        total_chunks=total_chunks,
        kb_settings=settings,
    )


@router.post("/tenants/{agent_id}/kb/{source_type}/{source_id}/remove")
async def tenant_kb_remove(request: Request, agent_id: str, source_type: str, source_id: str):
    """Remove a KB item — delete all embedding chunks for the source."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import remove_kb_item

    try:
        deleted = await remove_kb_item(agent_id, source_type, source_id)
        logger.info(f"Removed {deleted} KB chunks for {source_type}/{source_id} (agent {agent_id})")
        log_audit(
            user_id=auth.get("user_id"),
            action="remove_kb_item",
            target_entity=source_type,
            target_id=source_id,
            ip_address=_client_ip(request),
            metadata={"agent_id": agent_id},
        )
    except psycopg.Error as e:
        logger.error(f"KB remove failed: {e}")

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


@router.post("/tenants/{agent_id}/kb/{source_type}/{source_id}/reindex")
async def tenant_kb_reindex(request: Request, agent_id: str, source_type: str, source_id: str):
    """Re-index a KB item by re-reading the source and re-embedding."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    # Documents cannot be re-indexed (no upstream source)
    if source_type == "document":
        return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)

    from uuid import UUID as _UUID
    from app.services.rag_service import get_rag_service
    rag = get_rag_service()

    try:
        agent_uuid = _UUID(agent_id)
        source_uuid = _UUID(source_id)

        if source_type == "conversation":
            chunks = rag.index_conversation(agent_uuid, source_uuid)
        elif source_type == "contact":
            chunks = rag.index_contact(agent_uuid, source_uuid)
        elif source_type == "listing":
            chunks = rag.index_listing(agent_uuid, source_uuid)
        else:
            logger.warning(f"Unknown source_type for re-index: {source_type}")
            chunks = 0

        logger.info(f"Re-indexed {chunks} chunks for {source_type}/{source_id} (agent {agent_id})")
        log_audit(
            user_id=auth.get("user_id"),
            action="reindex_kb_item",
            target_entity=source_type,
            target_id=source_id,
            ip_address=_client_ip(request),
            metadata={"agent_id": agent_id, "chunks": chunks},
        )
    except Exception as e:  # Broad catch: mixed DB + embedding API call
        logger.error(f"KB re-index failed: {e}")

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


@router.post("/tenants/{agent_id}/kb/{source_type}/{source_id}/expire")
async def tenant_kb_set_expiration(request: Request, agent_id: str, source_type: str, source_id: str):
    """Set or clear expiration date on a KB item."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import set_kb_item_expiration

    expires_at = form.get("expires_at") or None

    # Validate that expiration date is in the future (if provided)
    if expires_at:
        from datetime import datetime, timezone as tz
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=tz.utc)
            if exp_dt <= datetime.now(tz.utc):
                return Response("Expiration date must be in the future", status_code=400)
        except ValueError:
            return Response("Invalid date format", status_code=400)

    try:
        await set_kb_item_expiration(agent_id, source_type, source_id, expires_at)
        log_audit(
            user_id=auth.get("user_id"),
            action="set_kb_expiration",
            target_entity=source_type,
            target_id=source_id,
            ip_address=_client_ip(request),
            metadata={"agent_id": agent_id, "expires_at": expires_at},
        )
    except psycopg.Error as e:
        logger.error(f"KB expiration update failed: {e}")

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


@router.post("/tenants/{agent_id}/kb/settings")
async def tenant_kb_update_settings(request: Request, agent_id: str):
    """Update KB expiration policy settings."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import update_kb_settings

    policy = form.get("kb_expiration_policy", "remind_only")
    default_ttl_raw = form.get("kb_default_ttl_days")
    default_ttl = int(default_ttl_raw) if default_ttl_raw and default_ttl_raw.strip() else None

    try:
        await update_kb_settings(agent_id, policy, default_ttl)
        log_audit(
            user_id=auth.get("user_id"),
            action="update_kb_settings",
            target_entity="agent",
            target_id=agent_id,
            ip_address=_client_ip(request),
            metadata={"policy": policy, "default_ttl_days": default_ttl},
        )
    except ValueError as e:
        return Response(str(e), status_code=400)
    except psycopg.Error as e:
        logger.error(f"KB settings update failed: {e}")

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


@router.post("/tenants/{agent_id}/kb/upload")
async def tenant_kb_upload(request: Request, agent_id: str):
    """Upload a new document to the knowledge base (text content, chunk and embed)."""
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    admin_err = _require_admin(auth)
    if admin_err:
        return admin_err

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    title = (form.get("title") or "").strip()
    content = (form.get("content") or "").strip()

    # Validation
    if not title:
        return Response("Title is required", status_code=400)
    if not content:
        return Response("Content is required", status_code=400)
    if len(content) > 50_000:
        return Response(
            "Document too large. Maximum 50,000 characters. Split into multiple documents.",
            status_code=400,
        )

    # Sanitize content: strip HTML/script tags
    import nh3
    content = nh3.clean(content, tags=set())  # Strip ALL HTML tags

    from uuid import uuid4, UUID as _UUID
    from app.services.rag_service import get_rag_service
    from app.services.embedding_service import chunk_text
    from app.config import get_settings

    rag = get_rag_service()
    settings = get_settings()
    agent_uuid = _UUID(agent_id)
    doc_source_id = uuid4()

    try:
        chunks = chunk_text(
            content,
            chunk_size=settings.RAG_CHUNK_SIZE,
            overlap=settings.RAG_CHUNK_OVERLAP,
        )

        if not chunks:
            return Response("Content produced no chunks after processing", status_code=400)

        metadata = {"title": title, "document": True}
        rag._upsert_chunks(agent_uuid, "document", doc_source_id, chunks, metadata)

        # Set title on all chunks for the new document
        from app.db.connection import get_db_connection, set_agent_context
        with get_db_connection() as conn:
            set_agent_context(conn, agent_uuid)
            conn.execute(
                "UPDATE embeddings SET title = %s WHERE source_id = %s",
                [title, str(doc_source_id)],
            )
            conn.commit()

        # Set expiration if provided
        expires_at = form.get("expires_at")
        if expires_at:
            from app.services.console_queries import set_kb_item_expiration
            await set_kb_item_expiration(agent_id, "document", str(doc_source_id), expires_at)

        logger.info(
            f"Uploaded KB document '{title}' with {len(chunks)} chunks "
            f"(agent {agent_id}, source_id {doc_source_id})"
        )
        log_audit(
            user_id=auth.get("user_id"),
            action="upload_kb_document",
            target_entity="document",
            target_id=str(doc_source_id),
            ip_address=_client_ip(request),
            metadata={"agent_id": agent_id, "title": title, "chunks": len(chunks)},
        )
    except Exception as e:  # Broad catch: mixed DB + embedding API call
        logger.error(f"KB document upload failed: {e}")
        return Response(f"Upload failed: {e}", status_code=500)

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


# ============================================================
# Documentation Hub
# ============================================================

@router.get("/docs/research", response_class=HTMLResponse)
async def docs_research(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    docs_map: dict[str, tuple[str, str]] = {
        "competitive-landscape-2026-03": ("Competitive Landscape (Mar 2026)", "docs/research/competitive-landscape-2026-03.md"),
        "htmx-jinja2-css-a11y-reference": ("HTMX / Jinja2 / CSS / A11y Reference", "docs/research/htmx-jinja2-css-a11y-reference.md"),
        "postgres-stack-reference-2025": ("PostgreSQL Stack Reference (2025)", "docs/research/postgres-stack-reference-2025.md"),
        "spotify-design-reference-brief": ("Spotify Design Reference Brief", "docs/research/spotify-design-reference-brief.md"),
    }

    selected = request.query_params.get("doc", "competitive-landscape-2026-03")
    if selected not in docs_map:
        selected = "competitive-landscape-2026-03"

    title, filepath = docs_map[selected]
    doc_html = _render_markdown(PROJECT_ROOT / filepath)

    return _render(request, "docs.html",
        page_title="Research", active_nav="docs-research",
        doc_html=doc_html or "<p>Document not found.</p>",
        doc_title=title,
        docs_map=docs_map,
        selected=selected,
        section="research",
    )


@router.get("/docs/api", response_class=HTMLResponse)
async def docs_api(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    return _render(request, "docs_api.html",
        page_title="API Documentation", active_nav="docs-api",
    )


@router.get("/docs/architecture", response_class=HTMLResponse)
async def docs_architecture(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    docs_map: dict[str, tuple[str, str]] = {
        "architecture-diagram": ("Architecture Diagram", "docs/architecture-diagram.md"),
        "architecture-audit": ("Architecture Audit", "docs/architecture-audit.md"),
        "engineering-standards": ("Engineering Standards", "docs/engineering-standards.md"),
    }

    selected = request.query_params.get("doc", "architecture-diagram")
    if selected not in docs_map:
        selected = "architecture-diagram"

    title, filepath = docs_map[selected]
    doc_html = _render_markdown(PROJECT_ROOT / filepath)

    return _render(request, "docs.html",
        page_title="Architecture", active_nav="docs-architecture",
        doc_html=doc_html or "<p>Document not found.</p>",
        doc_title=title,
        docs_map=docs_map,
        selected=selected,
        section="architecture",
    )


@router.get("/docs/changelog", response_class=HTMLResponse)
async def docs_changelog(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    changelog_path = PROJECT_ROOT / "docs" / "changelog.md"
    doc_html = _render_markdown(changelog_path)

    return _render(request, "docs.html",
        page_title="Changelog", active_nav="docs-changelog",
        doc_html=doc_html or "<p>Changelog has not been generated yet. Run <code>scripts/generate_changelog.sh</code> to generate it.</p>",
        doc_title="Changelog",
        docs_map={},
        selected="",
        section="changelog",
    )


@router.get("/docs/product", response_class=HTMLResponse)
async def docs_product(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    docs_map: dict[str, tuple[str, str]] = {
        "prd-customer-detail-redesign": ("PRD: Customer Detail Redesign", "docs/prd-customer-detail-redesign.md"),
        "ux-audit": ("UX Audit", "docs/ux-audit.md"),
        "audit-2026-03-11": ("Audit (2026-03-11)", "docs/audit-2026-03-11.md"),
    }

    selected = request.query_params.get("doc", "prd-customer-detail-redesign")
    if selected not in docs_map:
        selected = "prd-customer-detail-redesign"

    title, filepath = docs_map[selected]
    doc_html = _render_markdown(PROJECT_ROOT / filepath)

    return _render(request, "docs.html",
        page_title="Product", active_nav="docs-product",
        doc_html=doc_html or "<p>Document not found.</p>",
        doc_title=title,
        docs_map=docs_map,
        selected=selected,
        section="product",
    )
