"""Tests for the Operator Console — Steps 1-14."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone, date
from uuid import uuid4
from decimal import Decimal

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

AGENT_ID = str(uuid4())


# ============================================================
# Step 1: Auth Tests
# ============================================================

def test_console_root_redirects_to_login():
    """Unauthenticated /console → redirect to login."""
    response = client.get("/console/", follow_redirects=False)
    assert response.status_code == 303
    assert "/console/login" in response.headers.get("location", "") or \
           "/console/dashboard" in response.headers.get("location", "")


def test_console_login_page_renders():
    """GET /console/login returns login form."""
    response = client.get("/console/login")
    assert response.status_code == 200
    assert "password" in response.text.lower()


def test_console_login_wrong_password():
    """POST /console/login with wrong password shows error."""
    response = client.post("/console/login", data={"password": "wrongpassword"})
    assert response.status_code == 200
    assert "Invalid" in response.text or "invalid" in response.text


def test_console_login_correct_password():
    """POST /console/login with correct password redirects to dashboard."""
    response = client.post(
        "/console/login",
        data={"password": "changeme"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/console/dashboard" in response.headers.get("location", "")
    assert "console_session" in response.headers.get("set-cookie", "")


def test_console_dashboard_requires_auth():
    """GET /console/dashboard without session → redirect to login."""
    # Use a fresh client with no cookies
    fresh = TestClient(app, cookies={})
    response = fresh.get("/console/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert "/console/login" in response.headers.get("location", "")


def test_console_all_pages_require_auth():
    """All console pages redirect to login without session."""
    fresh = TestClient(app, cookies={})
    pages = [
        "/console/dashboard",
        "/console/tenants",
        "/console/conversations",
        "/console/triggers",
        "/console/errors",
        "/console/costs",
        "/console/health",
    ]
    for page in pages:
        response = fresh.get(page, follow_redirects=False)
        assert response.status_code == 303, f"{page} should redirect"
        assert "/console/login" in response.headers.get("location", ""), f"{page} should go to login"


def _get_authed_client():
    """Get a client with a valid session cookie."""
    response = client.post(
        "/console/login",
        data={"password": "changeme"},
        follow_redirects=False,
    )
    cookies = response.cookies
    return cookies


def test_console_logout():
    """Logout clears session."""
    cookies = _get_authed_client()
    response = client.get("/console/logout", cookies=cookies, follow_redirects=False)
    assert response.status_code == 303
    assert "/console/login" in response.headers.get("location", "")


# ============================================================
# Step 2: Navigation
# ============================================================

@patch("app.services.console_queries.async_get_system_pulse", new_callable=AsyncMock)
@patch("app.services.console_queries.async_get_recent_activity", new_callable=AsyncMock)
@patch("app.services.console_queries.async_get_agents_needing_attention", new_callable=AsyncMock)
def test_dashboard_has_navigation(mock_attn, mock_act, mock_pulse):
    """Dashboard page has sidebar navigation links."""
    mock_pulse.return_value = {
        "total_agents": 5, "messages_today": 100, "messages_24h": 250,
        "errors_24h": 2, "cost_today_dollars": 3.50,
    }
    mock_act.return_value = []
    mock_attn.return_value = {"error_agents": [], "inactive_agents": []}

    cookies = _get_authed_client()
    response = client.get("/console/dashboard", cookies=cookies)
    assert response.status_code == 200
    assert "/console/tenants" in response.text
    assert "/console/conversations" in response.text
    assert "/console/triggers" in response.text
    assert "/console/errors" in response.text
    assert "/console/costs" in response.text
    assert "/console/health" in response.text


# ============================================================
# Step 3: Dashboard
# ============================================================

@patch("app.services.console_queries.async_get_system_pulse", new_callable=AsyncMock)
@patch("app.services.console_queries.async_get_recent_activity", new_callable=AsyncMock)
@patch("app.services.console_queries.async_get_agents_needing_attention", new_callable=AsyncMock)
def test_dashboard_shows_pulse(mock_attn, mock_act, mock_pulse):
    """Dashboard shows system pulse cards."""
    mock_pulse.return_value = {
        "total_agents": 10, "messages_today": 500, "messages_24h": 1200,
        "errors_24h": 3, "cost_today_dollars": 12.50,
    }
    mock_act.return_value = []
    mock_attn.return_value = {"error_agents": [], "inactive_agents": []}

    cookies = _get_authed_client()
    response = client.get("/console/dashboard", cookies=cookies)
    assert response.status_code == 200
    assert "10" in response.text  # total agents
    assert "500" in response.text  # messages today
    assert "$12.5" in response.text  # cost


@patch("app.services.console_queries.async_get_recent_activity", new_callable=AsyncMock)
def test_activity_feed_partial(mock_act):
    """HTMX activity feed partial returns events."""
    mock_act.return_value = [
        {
            "created_at": datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
            "sender_type": "client",
            "body": "Is 123 Oak available?",
            "agent_name": "Test Agent",
            "contact_name": "Sarah",
            "ai_generated": False,
            "model_used": None,
        }
    ]

    cookies = _get_authed_client()
    response = client.get("/console/dashboard/activity-feed", cookies=cookies)
    assert response.status_code == 200
    assert "Test Agent" in response.text
    assert "123 Oak" in response.text


# ============================================================
# Step 4: Query Layer
# ============================================================

def test_query_layer_functions_exist():
    """All query functions are importable."""
    from app.services.console_queries import (
        get_system_pulse, get_recent_activity, get_agents_needing_attention,
        get_all_agents, get_agent_detail, get_recent_conversations,
        get_conversation_detail, get_trigger_queue, get_recent_errors,
        get_cost_summary, get_cost_by_agent, get_model_tier_breakdown,
        get_health_overview, get_health_status_color,
        log_error, retry_trigger, cancel_trigger, fire_trigger_now,
        create_agent_tenant, update_agent_tenant, deactivate_agent,
    )


@patch("app.services.console_queries.get_db_connection")
def test_system_pulse_returns_defaults_on_error(mock_conn):
    """System pulse returns zeros when DB is unavailable."""
    from app.services.console_queries import get_system_pulse
    mock_conn.side_effect = Exception("DB down")
    result = get_system_pulse()
    assert result["total_agents"] == 0
    assert result["messages_today"] == 0


@patch("app.services.console_queries.get_db_connection")
def test_get_all_agents(mock_conn):
    """get_all_agents returns agent list with stats."""
    from app.services.console_queries import get_all_agents

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = [
        {"id": AGENT_ID, "name": "Agent One", "contact_count": 15,
         "messages_today": 42, "last_active": date(2026, 3, 9),
         "errors_24h": 0, "current_status": "available",
         "brokerage": "Test RE", "market": "Philly", "twilio_number": "+15551111"},
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    agents = get_all_agents()
    assert len(agents) == 1
    assert agents[0]["name"] == "Agent One"
    assert agents[0]["contact_count"] == 15


# ============================================================
# Step 5: Tenant List + Detail
# ============================================================

@patch("app.services.console_queries.get_all_agents")
def test_tenant_list_renders(mock_agents):
    """Tenant list page renders agent table."""
    mock_agents.return_value = [
        {"id": AGENT_ID, "name": "Sarah Agent", "brokerage": "RE/MAX",
         "market": "Philly", "twilio_number": "+15551234567",
         "contact_count": 20, "messages_today": 15, "last_active": date(2026, 3, 9),
         "current_status": "available", "errors_24h": 0},
    ]

    cookies = _get_authed_client()
    response = client.get("/console/tenants", cookies=cookies)
    assert response.status_code == 200
    assert "Sarah Agent" in response.text
    assert "RE/MAX" in response.text


@patch("app.services.console_queries.get_all_agents")
def test_tenant_search(mock_agents):
    """Tenant search filters by name."""
    mock_agents.return_value = [
        {"id": "1", "name": "Alpha Agent", "brokerage": None, "market": "NYC",
         "twilio_number": "+1", "contact_count": 0, "messages_today": 0,
         "last_active": None, "current_status": "available", "errors_24h": 0},
        {"id": "2", "name": "Beta Agent", "brokerage": None, "market": "LA",
         "twilio_number": "+2", "contact_count": 0, "messages_today": 0,
         "last_active": None, "current_status": "available", "errors_24h": 0},
    ]

    cookies = _get_authed_client()
    response = client.get("/console/tenants?search=alpha", cookies=cookies)
    assert "Alpha Agent" in response.text
    assert "Beta Agent" not in response.text


# ============================================================
# Step 6: Conversation Viewer
# ============================================================

@patch("app.services.console_queries.get_all_agents")
@patch("app.services.console_queries.get_recent_conversations")
def test_conversation_list_renders(mock_convos, mock_agents):
    """Conversation list renders."""
    mock_agents.return_value = []
    mock_convos.return_value = [
        {"id": str(uuid4()), "channel": "sms", "last_message_at": datetime.now(timezone.utc),
         "agent_name": "Test Agent", "contact_name": "Sarah", "phone": "+18005551234",
         "msg_count": 12, "last_message": "Is 123 Oak available?"},
    ]

    cookies = _get_authed_client()
    response = client.get("/console/conversations", cookies=cookies)
    assert response.status_code == 200
    assert "Sarah" in response.text


# ============================================================
# Step 7: Trigger Queue
# ============================================================

@patch("app.services.console_queries.get_all_agents")
@patch("app.services.console_queries.get_trigger_queue")
def test_trigger_list_renders(mock_triggers, mock_agents):
    """Trigger queue renders with status badges."""
    mock_agents.return_value = []
    mock_triggers.return_value = [
        {"id": str(uuid4()), "agent_name": "Test Agent", "trigger_type": "follow_up",
         "scheduled_at": datetime.now(timezone.utc), "status": "pending",
         "action_type": "notify_agent", "autonomy_level": "ask_agent",
         "recurrence": None},
        {"id": str(uuid4()), "agent_name": "Test Agent", "trigger_type": "dom_alert",
         "scheduled_at": datetime.now(timezone.utc), "status": "error",
         "action_type": "both", "autonomy_level": "autonomous",
         "recurrence": "daily"},
    ]

    cookies = _get_authed_client()
    response = client.get("/console/triggers", cookies=cookies)
    assert response.status_code == 200
    assert "follow_up" in response.text
    assert "Retry" in response.text  # Error trigger should have retry button


# ============================================================
# Step 8: Error Log
# ============================================================

@patch("app.services.console_queries.get_all_agents")
@patch("app.services.console_queries.get_recent_errors")
def test_error_log_renders(mock_errors, mock_agents):
    """Error log renders tool execution errors."""
    mock_agents.return_value = []
    mock_errors.return_value = {
        "tool_errors": [
            {"created_at": datetime.now(timezone.utc), "agent_name": "Test Agent",
             "tool_name": "lookup_contact", "error_message": "Connection timeout",
             "input_json": "{}", "output_json": None, "latency_ms": 5000},
        ],
        "app_errors": [],
    }

    cookies = _get_authed_client()
    response = client.get("/console/errors", cookies=cookies)
    assert response.status_code == 200
    assert "Connection timeout" in response.text
    assert "lookup_contact" in response.text


def test_log_error_function():
    """log_error function is callable."""
    from app.services.console_queries import log_error
    # Should not raise even without DB
    log_error("test_module", "error", "Test error message")


# ============================================================
# Step 9: Cost Dashboard
# ============================================================

@patch("app.services.console_queries.get_model_tier_breakdown")
@patch("app.services.console_queries.get_cost_by_agent")
@patch("app.services.console_queries.get_cost_summary")
def test_cost_dashboard_renders(mock_summary, mock_agent_costs, mock_tiers):
    """Cost dashboard renders with data."""
    mock_summary.return_value = {
        "total_cost_dollars": 45.50, "total_messages": 3000,
        "total_voice_minutes": 120.5, "total_showings": 25,
        "total_llm_calls": 800, "daily": [],
    }
    mock_agent_costs.return_value = [
        {"name": "Agent One", "messages": 1500, "llm_calls": 400,
         "tokens": 500000, "cost_cents": 2500, "voice_minutes": 60,
         "cost_dollars": 25.0, "cost_per_message": 0.017},
    ]
    mock_tiers.return_value = {
        "template": {"count": 500, "pct": 62.5},
        "haiku": {"count": 200, "pct": 25.0},
        "sonnet": {"count": 100, "pct": 12.5},
        "_total": 800,
    }

    cookies = _get_authed_client()
    response = client.get("/console/costs", cookies=cookies)
    assert response.status_code == 200
    assert "$45.5" in response.text
    assert "Agent One" in response.text
    assert "template" in response.text


# ============================================================
# Step 10: Health Overview
# ============================================================

@patch("app.services.console_queries.get_health_overview")
def test_health_page_renders(mock_health):
    """Health page renders service indicators."""
    mock_health.return_value = {
        "services": {
            "database": "green",
            "redis": "red",
            "anthropic": "yellow",
            "twilio": "green",
        },
        "pipeline": {"avg_latency_ms": 150, "p50_ms": 120, "p95_ms": 450},
    }

    cookies = _get_authed_client()
    response = client.get("/console/health", cookies=cookies)
    assert response.status_code == 200
    assert "database" in response.text.lower()
    assert "green" in response.text


@patch("app.services.console_queries.get_health_status_color")
def test_health_status_dot(mock_color):
    """Health status dot HTMX partial works."""
    mock_color.return_value = "green"
    response = client.get("/console/health/status-dot")
    assert response.status_code == 200
    assert "status-green" in response.text


# ============================================================
# Step 11: Integration
# ============================================================

def test_static_css_served():
    """Static CSS file is served."""
    response = client.get("/static/console/style.css")
    assert response.status_code == 200
    assert "sidebar" in response.text


def test_full_auth_flow():
    """Full auth flow: login → dashboard → logout → redirected."""
    # Login
    r1 = client.post("/console/login", data={"password": "changeme"}, follow_redirects=False)
    assert r1.status_code == 303
    cookies = r1.cookies

    # Access dashboard
    r2 = client.get("/console/dashboard", cookies=cookies, follow_redirects=False)
    # Should either render (200) or redirect to dashboard (303 from /)
    assert r2.status_code in (200, 303)

    # Logout
    r3 = client.get("/console/logout", cookies=cookies, follow_redirects=False)
    assert r3.status_code == 303

    # After logout, dashboard should redirect to login
    r4 = client.get("/console/dashboard", follow_redirects=False)
    assert r4.status_code == 303
    assert "/console/login" in r4.headers.get("location", "")


# ============================================================
# Steps 12-14: Controls
# ============================================================

def test_tenant_new_form_renders():
    """New tenant form page renders."""
    cookies = _get_authed_client()
    response = client.get("/console/tenants/new", cookies=cookies)
    assert response.status_code == 200
    assert "Agent Profile" in response.text
    assert "Twilio" in response.text


def test_tenant_create_validates_required():
    """Creating tenant without required fields raises error."""
    from app.services.console_queries import create_agent_tenant
    with pytest.raises(ValueError, match="Missing required field"):
        create_agent_tenant({"name": "Test"})


@patch("app.services.console_queries.get_db_connection")
def test_tenant_create_checks_duplicate_twilio(mock_conn):
    """Creating tenant with duplicate Twilio number raises error."""
    from app.services.console_queries import create_agent_tenant

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = {"id": "existing"}
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    with pytest.raises(ValueError, match="already assigned"):
        create_agent_tenant({
            "name": "Test", "email": "t@t.com",
            "phone": "+1555", "twilio_number": "+1555dup",
        })


@patch("app.services.console_queries.get_db_connection")
def test_retry_trigger(mock_conn):
    """retry_trigger resets status to pending."""
    from app.services.console_queries import retry_trigger

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    retry_trigger(str(uuid4()))
    ctx.execute.assert_called_once()
    assert "pending" in str(ctx.execute.call_args)


@patch("app.services.console_queries.get_db_connection")
def test_cancel_trigger(mock_conn):
    """cancel_trigger sets status to cancelled."""
    from app.services.console_queries import cancel_trigger

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    cancel_trigger(str(uuid4()))
    ctx.execute.assert_called_once()
    assert "cancelled" in str(ctx.execute.call_args)


@patch("app.services.console_queries.get_db_connection")
def test_deactivate_agent(mock_conn):
    """deactivate_agent sets status and cancels triggers."""
    from app.services.console_queries import deactivate_agent

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    deactivate_agent(str(uuid4()))
    assert ctx.execute.call_count == 2  # agent update + trigger cancel


def test_error_log_table_in_schema():
    """error_log table is defined in schema.sql."""
    with open("app/db/schema.sql") as f:
        schema = f.read()
    assert "error_log" in schema
    assert "module" in schema
    assert "severity" in schema
    assert "stack_trace" in schema
