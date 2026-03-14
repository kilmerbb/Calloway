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
# Errors (redirect to Health)
# ============================================================

@router.get("/errors")
async def error_list_redirect(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    return RedirectResponse(url="/console/health?tab=errors", status_code=302)


# ============================================================
# Costs (redirect to Billing)
# ============================================================

@router.get("/costs")
async def cost_dashboard_redirect(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    return RedirectResponse(url="/console/billing?tab=ai-costs", status_code=302)


# ============================================================
# Health
# ============================================================

@router.get("/health", response_class=HTMLResponse)
async def health_overview(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import (
        async_get_health_overview, async_get_all_agents, async_get_recent_errors,
    )

    agent_filter = request.query_params.get("agent", "")
    active_tab = request.query_params.get("tab", "services")

    return _render(request, "health.html",
        page_title="System Health", active_nav="health",
        health=await async_get_health_overview(),
        agents=await async_get_all_agents(),
        errors=await async_get_recent_errors(limit=100, agent_id=agent_filter or None),
        agent_filter=agent_filter,
        active_tab=active_tab,
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
    from app.services.console_queries import (
        async_get_cost_summary, async_get_cost_by_agent, async_get_model_tier_breakdown,
    )

    active_tab = request.query_params.get("tab", "subscriptions")

    return _render(request, "billing.html",
        page_title="Billing", active_nav="billing",
        subscriptions=get_billing_summary(),
        plan_tiers=PLAN_TIERS,
        cost_summary=await async_get_cost_summary(days=30),
        per_agent=await async_get_cost_by_agent(days=30),
        model_tiers=await async_get_model_tier_breakdown(days=30),
        active_tab=active_tab,
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


# ============================================================
# Customer Detail — Messages Tab
# ============================================================

@router.get("/tenants/{agent_id}/tab/messages", response_class=HTMLResponse)
async def tenant_messages_tab(request: Request, agent_id: str):
    """HTMX partial: Messages tab — contact list with conversation summaries."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_conversations_by_contact

    page = int(request.query_params.get("page", "1"))
    per_page = int(request.query_params.get("per_page", "25"))
    offset = (page - 1) * per_page

    contacts = await async_get_conversations_by_contact(
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
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import async_get_conversation_thread

    page = int(request.query_params.get("page", "1"))
    per_page = 50
    offset = (page - 1) * per_page

    thread = await async_get_conversation_thread(
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
# Customer Detail — Knowledge Base Tab
# ============================================================

@router.get("/tenants/{agent_id}/tab/knowledge-base", response_class=HTMLResponse)
async def tenant_kb_tab(request: Request, agent_id: str):
    """HTMX partial: Knowledge Base tab — items grouped by source type."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    from app.services.console_queries import (
        async_get_knowledge_base_items, async_get_kb_settings,
    )

    items = await async_get_knowledge_base_items(agent_id)
    settings = await async_get_kb_settings(agent_id)

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
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import async_remove_kb_item

    try:
        deleted = await async_remove_kb_item(agent_id, source_type, source_id)
        logger.info(f"Removed {deleted} KB chunks for {source_type}/{source_id} (agent {agent_id})")
    except Exception as e:
        logger.error(f"KB remove failed: {e}")

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


@router.post("/tenants/{agent_id}/kb/{source_type}/{source_id}/reindex")
async def tenant_kb_reindex(request: Request, agent_id: str, source_type: str, source_id: str):
    """Re-index a KB item by re-reading the source and re-embedding."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

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
    except Exception as e:
        logger.error(f"KB re-index failed: {e}")

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


@router.post("/tenants/{agent_id}/kb/{source_type}/{source_id}/expire")
async def tenant_kb_set_expiration(request: Request, agent_id: str, source_type: str, source_id: str):
    """Set or clear expiration date on a KB item."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import async_set_kb_item_expiration

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
        await async_set_kb_item_expiration(agent_id, source_type, source_id, expires_at)
    except Exception as e:
        logger.error(f"KB expiration update failed: {e}")

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


@router.post("/tenants/{agent_id}/kb/settings")
async def tenant_kb_update_settings(request: Request, agent_id: str):
    """Update KB expiration policy settings."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

    form = await request.form()
    csrf_err = _check_csrf(request, form.get("csrf_token"))
    if csrf_err:
        return csrf_err

    from app.services.console_queries import async_update_kb_settings

    policy = form.get("kb_expiration_policy", "remind_only")
    default_ttl_raw = form.get("kb_default_ttl_days")
    default_ttl = int(default_ttl_raw) if default_ttl_raw and default_ttl_raw.strip() else None

    try:
        await async_update_kb_settings(agent_id, policy, default_ttl)
    except ValueError as e:
        return Response(str(e), status_code=400)
    except Exception as e:
        logger.error(f"KB settings update failed: {e}")

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)


@router.post("/tenants/{agent_id}/kb/upload")
async def tenant_kb_upload(request: Request, agent_id: str):
    """Upload a new document to the knowledge base (text content, chunk and embed)."""
    redirect = _require_auth(request)
    if redirect:
        return redirect

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
    import re
    content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r"<[^>]+>", "", content)

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
            from app.services.console_queries import async_set_kb_item_expiration
            await async_set_kb_item_expiration(agent_id, "document", str(doc_source_id), expires_at)

        logger.info(
            f"Uploaded KB document '{title}' with {len(chunks)} chunks "
            f"(agent {agent_id}, source_id {doc_source_id})"
        )
    except Exception as e:
        logger.error(f"KB document upload failed: {e}")
        return Response(f"Upload failed: {e}", status_code=500)

    return RedirectResponse(f"/console/tenants/{agent_id}?tab=knowledge-base", status_code=303)
