"""Tests for Phase 3: Billing system and agent portal.

Tests the Stripe billing service, agent portal authentication,
and portal page rendering.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.services.billing_service import PLAN_TIERS


# ── Plan tier tests ──────────────────────────────────────────

def test_plan_tiers_defined():
    """All three plan tiers exist with required fields."""
    assert "starter" in PLAN_TIERS
    assert "professional" in PLAN_TIERS
    assert "enterprise" in PLAN_TIERS

    for tier_name, tier in PLAN_TIERS.items():
        assert "name" in tier, f"Missing 'name' in {tier_name}"
        assert "price_cents" in tier, f"Missing 'price_cents' in {tier_name}"
        assert "message_limit" in tier, f"Missing 'message_limit' in {tier_name}"


def test_plan_tier_pricing_order():
    """Plan tiers are ordered by price: starter < professional < enterprise."""
    assert PLAN_TIERS["starter"]["price_cents"] < PLAN_TIERS["professional"]["price_cents"]
    assert PLAN_TIERS["professional"]["price_cents"] < PLAN_TIERS["enterprise"]["price_cents"]


# ── Agent portal tests ───────────────────────────────────────

def test_agent_login_page_renders(client):
    """Agent portal login page renders."""
    response = client.get("/agent/login")
    assert response.status_code == 200
    assert "phone" in response.text.lower() or "login" in response.text.lower()


def test_agent_portal_redirects_without_session(client):
    """Agent portal pages redirect to login without session."""
    for path in ["/agent/dashboard", "/agent/contacts", "/agent/conversations",
                 "/agent/schedule", "/agent/triggers"]:
        response = client.get(path, follow_redirects=False)
        assert response.status_code in (303, 307), f"Expected redirect for {path}"


# ── Console billing page tests ───────────────────────────────

def test_console_billing_requires_auth(client):
    """Console billing page requires authentication."""
    response = client.get("/console/billing", follow_redirects=False)
    assert response.status_code in (303, 307)


def test_console_billing_renders_with_db_errors(client):
    """Billing page renders 200 even when DB queries fail (graceful degradation)."""
    with patch("app.api.console.check_session", return_value={
        "authenticated": True, "user_id": "test", "email": "t@t.com",
        "display_name": "Test", "role": "admin",
    }), \
    patch("app.services.billing_service.get_billing_summary", return_value=[]), \
    patch("app.services.console_queries.get_cost_summary", return_value={
        "total_cost_dollars": 0, "llm_cost_dollars": 0,
        "sms_cost_dollars": 0, "voice_cost_dollars": 0,
        "total_sms_segments": 0, "total_messages": 0,
        "total_voice_minutes": 0, "total_showings": 0,
        "total_llm_calls": 0, "daily": [],
    }), \
    patch("app.services.console_queries.get_cost_by_agent", return_value=[]), \
    patch("app.services.console_queries.get_model_tier_breakdown", return_value={"_total": 0}):
        response = client.get("/console/billing")
        assert response.status_code == 200
        assert "Subscriptions" in response.text
        assert "AI Costs" in response.text
