"""Operator Console — web-based admin interface for system operators."""
import logging
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.api.console_auth import (
    verify_password, create_session, check_session, clear_session,
    generate_csrf_token, validate_csrf_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/console", tags=["console"])

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "console"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _render(request: Request, template: str, response: Response | None = None, **ctx):
    """Render a template with CSRF token injected."""
    # Generate the CSRF token first (may set cookie via response object).
    # We use a temporary Response to capture any Set-Cookie header, then
    # transfer it to the final TemplateResponse so the cookie reaches the browser.
    tmp = Response()
    csrf = generate_csrf_token(request, tmp)
    ctx["csrf_token"] = csrf
    resp = templates.TemplateResponse(request, template, ctx)
    # Copy Set-Cookie headers from the temp response to the real one
    for header_value in tmp.headers.getlist("set-cookie"):
        resp.headers.append("set-cookie", header_value)
    return resp


def _require_auth(request: Request) -> RedirectResponse | None:
    """Return a redirect if not authenticated, else None."""
    if not check_session(request):
        return RedirectResponse("/console/login", status_code=303)
    return None


def _check_csrf(request: Request, csrf_token: str | None) -> Response | None:
    """Return 403 if CSRF token is invalid, else None."""
    if not validate_csrf_token(request, csrf_token):
        return Response("CSRF validation failed", status_code=403)
    return None


# ============================================================
# Auth routes
# ============================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "login.html", error=None)


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    # No CSRF on login — the password itself is the auth factor,
    # and this may be the first page visited (no CSRF cookie yet).
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
        async_get_system_pulse, async_get_recent_activity, async_get_agents_needing_attention,
    )

    return _render(request, "dashboard.html",
        page_title="Home", active_nav="dashboard",
        pulse=await async_get_system_pulse(),
        activity=await async_get_recent_activity(limit=20),
        attention=await async_get_agents_needing_attention(),
    )


@router.get("/dashboard/activity-feed", response_class=HTMLResponse)
async def dashboard_activity_feed(request: Request):
    """HTMX partial: refreshable activity feed."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_recent_activity
    return _render(request, "partials/activity_feed.html",
        activity=await async_get_recent_activity(limit=20),
    )


# ============================================================
# Onboarding Wizard
# ============================================================

@router.get("/onboard", response_class=HTMLResponse)
async def onboard_wizard(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    return _render(request, "onboard_wizard.html",
        page_title="Onboard New Agent", active_nav="onboard", error=None,
    )


@router.post("/onboard")
async def onboard_submit(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import create_agent_from_wizard

    try:
        result = create_agent_from_wizard(dict(form))
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
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_all_agents
    agents = await async_get_all_agents()

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
    redirect = _require_auth(request)
    if redirect:
        return redirect
    return _render(request, "tenant_new.html",
        page_title="New Customer", active_nav="tenants", error=None,
    )


@router.post("/tenants/new")
async def tenant_create(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import create_agent_tenant

    try:
        agent_id = create_agent_tenant(dict(form))
        return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)
    except ValueError as e:
        return _render(request, "tenant_new.html",
            page_title="New Customer", active_nav="tenants", error=str(e),
        )


@router.get("/tenants/{agent_id}", response_class=HTMLResponse)
async def tenant_detail(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_agent_detail
    detail = await async_get_agent_detail(agent_id)
    if not detail:
        return RedirectResponse("/console/tenants", status_code=303)

    return _render(request, "tenant_detail.html",
        page_title=f"Customer: {detail['agent']['name']}",
        active_nav="tenants", detail=detail,
    )


@router.get("/tenants/{agent_id}/edit", response_class=HTMLResponse)
async def tenant_edit_form(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_agent_detail
    detail = await async_get_agent_detail(agent_id)
    if not detail:
        return RedirectResponse("/console/tenants", status_code=303)

    return _render(request, "tenant_edit.html",
        page_title=f"Edit Customer: {detail['agent']['name']}",
        active_nav="tenants", agent=detail["agent"], error=None,
    )


@router.post("/tenants/{agent_id}/edit")
async def tenant_update(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import update_agent_tenant

    try:
        update_agent_tenant(agent_id, dict(form))
        return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)
    except ValueError as e:
        from app.services.console_queries import async_get_agent_detail
        detail = await async_get_agent_detail(agent_id)
        return _render(request, "tenant_edit.html",
            page_title=f"Edit Customer: {detail['agent']['name']}",
            active_nav="tenants", agent=detail["agent"], error=str(e),
        )


@router.post("/tenants/{agent_id}/deactivate")
async def tenant_deactivate(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import async_deactivate_agent
    await async_deactivate_agent(agent_id)
    return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)


@router.post("/tenants/{agent_id}/test-sms")
async def tenant_test_sms(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

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

    from app.services.console_queries import async_get_recent_conversations, async_get_all_agents

    agent_filter = request.query_params.get("agent", "")
    channel_filter = request.query_params.get("channel", "")
    search = request.query_params.get("search", "")

    return _render(request, "conversations.html",
        page_title="Messages", active_nav="conversations",
        conversations=await async_get_recent_conversations(
            agent_id=agent_filter or None,
            channel=channel_filter or None,
            search=search or None, limit=100,
        ),
        agents=await async_get_all_agents(),
        agent_filter=agent_filter, channel_filter=channel_filter, search=search,
    )


@router.get("/conversations/{conversation_id}", response_class=HTMLResponse)
async def conversation_detail(request: Request, conversation_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_conversation_detail
    detail = await async_get_conversation_detail(conversation_id)
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

    from app.services.console_queries import async_get_trigger_queue, async_get_all_agents

    status_filter = request.query_params.get("status", "pending")
    agent_filter = request.query_params.get("agent", "")

    return _render(request, "triggers.html",
        page_title="Automations", active_nav="triggers",
        triggers=await async_get_trigger_queue(
            status=status_filter if status_filter != "all" else None,
            agent_id=agent_filter or None,
        ),
        agents=await async_get_all_agents(),
        status_filter=status_filter, agent_filter=agent_filter,
    )


@router.post("/triggers/{trigger_id}/retry")
async def trigger_retry(request: Request, trigger_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import async_retry_trigger
    await async_retry_trigger(trigger_id)
    return RedirectResponse("/console/triggers", status_code=303)


@router.post("/triggers/{trigger_id}/cancel")
async def trigger_cancel(request: Request, trigger_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import async_cancel_trigger
    await async_cancel_trigger(trigger_id)
    return RedirectResponse("/console/triggers", status_code=303)


@router.post("/triggers/{trigger_id}/fire-now")
async def trigger_fire_now(request: Request, trigger_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import async_fire_trigger_now
    await async_fire_trigger_now(trigger_id)
    return RedirectResponse("/console/triggers", status_code=303)


# ============================================================
# Errors
# ============================================================

@router.get("/errors", response_class=HTMLResponse)
async def error_list(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_recent_errors, async_get_all_agents

    agent_filter = request.query_params.get("agent", "")

    return _render(request, "errors.html",
        page_title="Errors", active_nav="errors",
        errors=await async_get_recent_errors(limit=100, agent_id=agent_filter or None),
        agents=await async_get_all_agents(), agent_filter=agent_filter,
    )


# ============================================================
# Costs
# ============================================================

@router.get("/costs", response_class=HTMLResponse)
async def cost_dashboard(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_cost_summary, async_get_cost_by_agent, async_get_model_tier_breakdown

    return _render(request, "costs.html",
        page_title="Costs", active_nav="costs",
        summary=await async_get_cost_summary(days=30),
        per_agent=await async_get_cost_by_agent(days=30),
        model_tiers=await async_get_model_tier_breakdown(days=30),
    )


# ============================================================
# Health
# ============================================================

@router.get("/health", response_class=HTMLResponse)
async def health_overview(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_health_overview, async_get_all_agents

    return _render(request, "health.html",
        page_title="System Health", active_nav="health",
        health=await async_get_health_overview(),
        agents=await async_get_all_agents(),
    )


@router.get("/health/status-dot", response_class=HTMLResponse)
async def health_status_dot(request: Request):
    """HTMX partial: health status indicator."""
    from app.services.console_queries import async_get_health_status_color
    color = await async_get_health_status_color()
    return HTMLResponse(
        f'<span class="status-dot status-{color}" title="System {color}"></span>'
    )


@router.post("/health/run-scan/{agent_id}")
async def manual_daily_scan(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import run_manual_scan
    run_manual_scan(agent_id)
    return RedirectResponse("/console/health", status_code=303)


# ============================================================
# Billing
# ============================================================

@router.get("/billing", response_class=HTMLResponse)
async def billing_overview(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.billing_service import get_billing_summary, PLAN_TIERS

    return _render(request, "billing.html",
        page_title="Billing", active_nav="billing",
        subscriptions=get_billing_summary(),
        plan_tiers=PLAN_TIERS,
    )


@router.post("/billing/{agent_id}/change-plan")
async def billing_change_plan(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

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
    except Exception as e:
        logger.error(f"Plan change failed: {e}")

    return RedirectResponse("/console/billing", status_code=303)


@router.post("/billing/{agent_id}/cancel")
async def billing_cancel(request: Request, agent_id: str):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from uuid import UUID
    from app.services.billing_service import cancel_subscription
    try:
        cancel_subscription(UUID(agent_id))
    except Exception as e:
        logger.error(f"Subscription cancellation failed: {e}")

    return RedirectResponse("/console/billing", status_code=303)


# ============================================================
# User Manual
# ============================================================

@router.get("/manual", response_class=HTMLResponse)
async def user_manual(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    return _render(request, "manual.html",
        page_title="Help", active_nav="manual",
    )
