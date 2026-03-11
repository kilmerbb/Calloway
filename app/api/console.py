"""Operator Console — web-based admin interface for system operators."""
import logging
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.console_auth import verify_password, create_session, check_session, clear_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/console", tags=["console"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "console"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _render(request: Request, template: str, **ctx):
    """Render a template with the new TemplateResponse signature."""
    return templates.TemplateResponse(request, template, ctx)


def _require_auth(request: Request) -> RedirectResponse | None:
    """Return a redirect if not authenticated, else None."""
    if not check_session(request):
        return RedirectResponse("/console/login", status_code=303)
    return None


# ============================================================
# Auth routes
# ============================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "login.html", error=None)


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if verify_password(password):
        response = RedirectResponse("/console/dashboard", status_code=303)
        create_session(response)
        return response
    return _render(request, "login.html", error="Invalid password.")


@router.get("/logout")
async def logout(request: Request):
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
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import (
        get_system_pulse, get_recent_activity, get_agents_needing_attention,
    )

    return _render(request, "dashboard.html",
        page_title="Dashboard", active_nav="dashboard",
        pulse=get_system_pulse(),
        activity=get_recent_activity(limit=20),
        attention=get_agents_needing_attention(),
    )


@router.get("/dashboard/activity-feed", response_class=HTMLResponse)
async def dashboard_activity_feed(request: Request):
    """HTMX partial: refreshable activity feed."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_recent_activity
    return _render(request, "partials/activity_feed.html",
        activity=get_recent_activity(limit=20),
    )


# ============================================================
# Tenants
# ============================================================

@router.get("/tenants", response_class=HTMLResponse)
async def tenant_list(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_all_agents
    agents = get_all_agents()

    search = request.query_params.get("search", "")
    sort_by = request.query_params.get("sort", "name")
    if search:
        agents = [a for a in agents if search.lower() in a["name"].lower()
                  or search.lower() in (a.get("market") or "").lower()]

    return _render(request, "tenants.html",
        page_title="Tenants", active_nav="tenants",
        agents=agents, search=search, sort_by=sort_by,
    )


@router.get("/tenants/new", response_class=HTMLResponse)
async def tenant_new_form(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    return _render(request, "tenant_new.html",
        page_title="New Tenant", active_nav="tenants", error=None,
    )


@router.post("/tenants/new")
async def tenant_create(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    from app.services.console_queries import create_agent_tenant

    try:
        agent_id = create_agent_tenant(dict(form))
        return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)
    except ValueError as e:
        return _render(request, "tenant_new.html",
            page_title="New Tenant", active_nav="tenants", error=str(e),
        )


@router.get("/tenants/{agent_id}", response_class=HTMLResponse)
async def tenant_detail(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_agent_detail
    detail = get_agent_detail(agent_id)
    if not detail:
        return RedirectResponse("/console/tenants", status_code=303)

    return _render(request, "tenant_detail.html",
        page_title=f"Tenant: {detail['agent']['name']}",
        active_nav="tenants", detail=detail,
    )


@router.get("/tenants/{agent_id}/edit", response_class=HTMLResponse)
async def tenant_edit_form(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_agent_detail
    detail = get_agent_detail(agent_id)
    if not detail:
        return RedirectResponse("/console/tenants", status_code=303)

    return _render(request, "tenant_edit.html",
        page_title=f"Edit: {detail['agent']['name']}",
        active_nav="tenants", agent=detail["agent"], error=None,
    )


@router.post("/tenants/{agent_id}/edit")
async def tenant_update(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    from app.services.console_queries import update_agent_tenant

    try:
        update_agent_tenant(agent_id, dict(form))
        return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)
    except ValueError as e:
        from app.services.console_queries import get_agent_detail
        detail = get_agent_detail(agent_id)
        return _render(request, "tenant_edit.html",
            page_title=f"Edit: {detail['agent']['name']}",
            active_nav="tenants", agent=detail["agent"], error=str(e),
        )


@router.post("/tenants/{agent_id}/deactivate")
async def tenant_deactivate(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import deactivate_agent
    deactivate_agent(agent_id)
    return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)


@router.post("/tenants/{agent_id}/test-sms")
async def tenant_test_sms(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import send_test_sms
    try:
        send_test_sms(agent_id)
    except Exception as e:
        logger.error(f"Test SMS failed: {e}")
    return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)


# ============================================================
# Conversations
# ============================================================

@router.get("/conversations", response_class=HTMLResponse)
async def conversation_list(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_recent_conversations, get_all_agents

    agent_filter = request.query_params.get("agent", "")
    channel_filter = request.query_params.get("channel", "")
    search = request.query_params.get("search", "")

    return _render(request, "conversations.html",
        page_title="Conversations", active_nav="conversations",
        conversations=get_recent_conversations(
            agent_id=agent_filter or None,
            channel=channel_filter or None,
            search=search or None, limit=100,
        ),
        agents=get_all_agents(),
        agent_filter=agent_filter, channel_filter=channel_filter, search=search,
    )


@router.get("/conversations/{conversation_id}", response_class=HTMLResponse)
async def conversation_detail(request: Request, conversation_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_conversation_detail
    detail = get_conversation_detail(conversation_id)
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
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_trigger_queue, get_all_agents

    status_filter = request.query_params.get("status", "pending")
    agent_filter = request.query_params.get("agent", "")

    return _render(request, "triggers.html",
        page_title="Triggers", active_nav="triggers",
        triggers=get_trigger_queue(
            status=status_filter if status_filter != "all" else None,
            agent_id=agent_filter or None,
        ),
        agents=get_all_agents(),
        status_filter=status_filter, agent_filter=agent_filter,
    )


@router.post("/triggers/{trigger_id}/retry")
async def trigger_retry(request: Request, trigger_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import retry_trigger
    retry_trigger(trigger_id)
    return RedirectResponse("/console/triggers", status_code=303)


@router.post("/triggers/{trigger_id}/cancel")
async def trigger_cancel(request: Request, trigger_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import cancel_trigger
    cancel_trigger(trigger_id)
    return RedirectResponse("/console/triggers", status_code=303)


@router.post("/triggers/{trigger_id}/fire-now")
async def trigger_fire_now(request: Request, trigger_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import fire_trigger_now
    fire_trigger_now(trigger_id)
    return RedirectResponse("/console/triggers", status_code=303)


# ============================================================
# Errors
# ============================================================

@router.get("/errors", response_class=HTMLResponse)
async def error_list(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_recent_errors, get_all_agents

    agent_filter = request.query_params.get("agent", "")

    return _render(request, "errors.html",
        page_title="Errors", active_nav="errors",
        errors=get_recent_errors(limit=100, agent_id=agent_filter or None),
        agents=get_all_agents(), agent_filter=agent_filter,
    )


# ============================================================
# Costs
# ============================================================

@router.get("/costs", response_class=HTMLResponse)
async def cost_dashboard(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_cost_summary, get_cost_by_agent, get_model_tier_breakdown

    return _render(request, "costs.html",
        page_title="Costs", active_nav="costs",
        summary=get_cost_summary(days=30),
        per_agent=get_cost_by_agent(days=30),
        model_tiers=get_model_tier_breakdown(days=30),
    )


# ============================================================
# Health
# ============================================================

@router.get("/health", response_class=HTMLResponse)
async def health_overview(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import get_health_overview

    return _render(request, "health.html",
        page_title="Health", active_nav="health",
        health=get_health_overview(),
    )


@router.get("/health/status-dot", response_class=HTMLResponse)
async def health_status_dot(request: Request):
    """HTMX partial: health status indicator."""
    from app.services.console_queries import get_health_status_color
    color = get_health_status_color()
    return HTMLResponse(
        f'<span class="status-dot status-{color}" title="System {color}"></span>'
    )


@router.post("/health/run-scan/{agent_id}")
async def manual_daily_scan(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import run_manual_scan
    run_manual_scan(agent_id)
    return RedirectResponse("/console/health", status_code=303)


# ============================================================
# User Manual
# ============================================================

@router.get("/manual", response_class=HTMLResponse)
async def user_manual(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    return _render(request, "manual.html",
        page_title="User Manual", active_nav="manual",
    )
