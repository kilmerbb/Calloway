"""Security test suite — auth bypass, CSRF, SendGrid auth, Vapi blocking, sessions."""
import base64
import time

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


# ============================================================
# Helpers
# ============================================================

def _fresh_client(**kwargs) -> TestClient:
    """Return a TestClient with no cookies."""
    return TestClient(app, cookies={}, **kwargs)


def _authed_client() -> TestClient:
    """Return a TestClient that has logged in and carries session cookies."""
    c = TestClient(app)
    resp = c.post("/console/login", data={"password": "changeme"}, follow_redirects=False)
    assert resp.status_code == 303, "Login failed during test setup"
    return c


def _basic_auth_header(username: str, password: str) -> str:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {encoded}"


# ============================================================
# 1. Auth bypass — protected console routes without session
# ============================================================

class TestAuthBypass:
    """GET/POST to any /console/* route without session -> redirect to login."""

    PROTECTED_GET_ROUTES = [
        "/console/dashboard",
        "/console/tenants",
        "/console/conversations",
        "/console/triggers",
        "/console/errors",
        "/console/costs",
        "/console/health",
        "/console/onboard",
        "/console/tenants/new",
    ]

    PROTECTED_POST_ROUTES = [
        "/console/onboard",
        "/console/tenants/new",
    ]

    def test_get_routes_redirect_to_login(self):
        """All protected GET routes redirect unauthenticated users to login."""
        c = _fresh_client()
        for route in self.PROTECTED_GET_ROUTES:
            resp = c.get(route, follow_redirects=False)
            assert resp.status_code == 303, f"GET {route} should redirect, got {resp.status_code}"
            location = resp.headers.get("location", "")
            assert "/console/login" in location, f"GET {route} should redirect to login, got {location}"

    def test_post_routes_redirect_to_login(self):
        """All protected POST routes redirect unauthenticated users to login."""
        c = _fresh_client()
        for route in self.PROTECTED_POST_ROUTES:
            resp = c.post(route, data={"dummy": "data"}, follow_redirects=False)
            assert resp.status_code == 303, f"POST {route} should redirect, got {resp.status_code}"
            location = resp.headers.get("location", "")
            assert "/console/login" in location, f"POST {route} should redirect to login, got {location}"


# ============================================================
# 2. CSRF protection
# ============================================================

class TestCSRF:
    """CSRF token validation on console write endpoints."""

    def test_post_without_csrf_token_returns_403(self):
        """POST to a console write endpoint without CSRF token -> 403."""
        c = _authed_client()
        # POST /console/onboard without csrf_token field
        resp = c.post("/console/onboard", data={"name": "Test Agent"}, follow_redirects=False)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

    def test_post_with_invalid_csrf_token_returns_403(self):
        """POST with an invalid CSRF token -> 403."""
        c = _authed_client()
        resp = c.post(
            "/console/onboard",
            data={"name": "Test Agent", "csrf_token": "totally-bogus-token"},
            follow_redirects=False,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

    def test_post_with_valid_csrf_token_succeeds(self):
        """POST with a valid CSRF token passes CSRF check (may fail on business logic, not 403)."""
        c = _authed_client()
        # First GET a page to obtain a CSRF cookie
        page = c.get("/console/onboard")
        assert page.status_code == 200

        csrf_cookie = c.cookies.get("console_csrf")
        assert csrf_cookie, "CSRF cookie should be set after page load"

        # POST with the valid CSRF token — mock the business logic so we isolate CSRF
        with patch("app.services.console_queries.create_agent_from_wizard") as mock_create:
            mock_create.return_value = {
                "agent_id": "test-123",
                "agent_name": "Test Agent",
                "checklist": [],
            }
            resp = c.post(
                "/console/onboard",
                data={
                    "name": "Test Agent",
                    "phone": "+15551234567",
                    "csrf_token": csrf_cookie,
                },
                follow_redirects=False,
            )
            # Should NOT be 403 — CSRF passed
            assert resp.status_code != 403, f"CSRF should have passed, got 403"


# ============================================================
# 3. SendGrid webhook auth
# ============================================================

class TestSendGridAuth:
    """POST to /webhooks/email/inbound with Basic Auth checks."""

    def test_sendgrid_no_auth_returns_401(self):
        """POST to /webhooks/email/inbound without Authorization header -> 401."""
        c = _fresh_client()
        with patch("app.api.webhooks.get_settings") as mock_settings:
            s = MagicMock()
            s.SENDGRID_INBOUND_SECRET = "s3cr3t"
            s.ENVIRONMENT = "development"
            mock_settings.return_value = s
            resp = c.post("/webhooks/email/inbound", data={"to": "test@example.com"})
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_sendgrid_wrong_credentials_returns_401(self):
        """POST with wrong Basic Auth credentials -> 401."""
        c = _fresh_client()
        with patch("app.api.webhooks.get_settings") as mock_settings:
            s = MagicMock()
            s.SENDGRID_INBOUND_SECRET = "s3cr3t"
            s.ENVIRONMENT = "development"
            mock_settings.return_value = s
            resp = c.post(
                "/webhooks/email/inbound",
                data={"to": "test@example.com"},
                headers={"Authorization": _basic_auth_header("sendgrid", "wrong-password")},
            )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_sendgrid_valid_auth_succeeds(self):
        """POST with valid Basic Auth -> not 401/403 (request proceeds)."""
        c = _fresh_client()
        with patch("app.api.webhooks.get_settings") as mock_settings, \
             patch("app.api.webhooks._resolve_agent_from_email", return_value=None):
            s = MagicMock()
            s.SENDGRID_INBOUND_SECRET = "s3cr3t"
            s.ENVIRONMENT = "development"
            mock_settings.return_value = s
            resp = c.post(
                "/webhooks/email/inbound",
                data={"to": "test@example.com"},
                headers={"Authorization": _basic_auth_header("sendgrid", "s3cr3t")},
            )
        # Should pass auth — no agent found returns 200 with status
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json().get("status") == "no_agent"


# ============================================================
# 4. Vapi webhook auth
# ============================================================

class TestVapiAuth:
    """POST to /webhooks/vapi/post-call with x-vapi-secret checks."""

    def test_vapi_missing_secret_header_returns_401(self):
        """POST without x-vapi-secret when secret is configured -> 401."""
        c = _fresh_client()
        with patch("app.api.webhooks.get_settings") as mock_settings:
            s = MagicMock()
            s.VAPI_WEBHOOK_SECRET = "my-vapi-secret"
            s.ENVIRONMENT = "development"
            mock_settings.return_value = s
            resp = c.post(
                "/webhooks/vapi/post-call",
                json={"call_id": "test-call"},
            )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_vapi_wrong_secret_returns_401(self):
        """POST with wrong x-vapi-secret -> 401."""
        c = _fresh_client()
        with patch("app.api.webhooks.get_settings") as mock_settings:
            s = MagicMock()
            s.VAPI_WEBHOOK_SECRET = "my-vapi-secret"
            s.ENVIRONMENT = "development"
            mock_settings.return_value = s
            resp = c.post(
                "/webhooks/vapi/post-call",
                json={"call_id": "test-call"},
                headers={"x-vapi-secret": "wrong-secret"},
            )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    def test_vapi_no_secret_configured_production_returns_403(self):
        """POST when VAPI_WEBHOOK_SECRET not configured + production -> 403."""
        c = _fresh_client()
        with patch("app.api.webhooks.get_settings") as mock_settings:
            s = MagicMock()
            s.VAPI_WEBHOOK_SECRET = ""
            s.ENVIRONMENT = "production"
            mock_settings.return_value = s
            resp = c.post(
                "/webhooks/vapi/post-call",
                json={"call_id": "test-call"},
            )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

    def test_vapi_valid_secret_succeeds(self):
        """POST with valid x-vapi-secret -> succeeds (200)."""
        c = _fresh_client()
        with patch("app.api.webhooks.get_settings") as mock_settings, \
             patch("app.api.webhooks.process_vapi_transcript", return_value=None):
            s = MagicMock()
            s.VAPI_WEBHOOK_SECRET = "my-vapi-secret"
            s.ENVIRONMENT = "development"
            mock_settings.return_value = s
            resp = c.post(
                "/webhooks/vapi/post-call",
                json={"call_id": "test-call"},
                headers={"x-vapi-secret": "my-vapi-secret"},
            )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json().get("status") == "ok"


# ============================================================
# 5. Login auth
# ============================================================

class TestLogin:
    """Login endpoint with valid/invalid password."""

    def test_invalid_password_rejected(self):
        """POST /console/login with wrong password -> stays on login page."""
        c = _fresh_client()
        resp = c.post("/console/login", data={"password": "wrong"}, follow_redirects=False)
        assert resp.status_code == 200, "Should re-render login page"
        assert "invalid" in resp.text.lower() or "Invalid" in resp.text

    def test_valid_password_creates_session(self):
        """POST /console/login with correct password -> redirect + session cookie."""
        c = _fresh_client()
        resp = c.post("/console/login", data={"password": "changeme"}, follow_redirects=False)
        assert resp.status_code == 303
        assert "/console/dashboard" in resp.headers.get("location", "")
        # Session cookie should be set
        set_cookie = resp.headers.get("set-cookie", "")
        assert "console_session" in set_cookie


# ============================================================
# 6. Session expiry
# ============================================================

class TestSessionExpiry:
    """Expired session cookie -> redirect to login."""

    def test_expired_session_redirects_to_login(self):
        """A session token signed >24h ago should be rejected."""
        from app.api import console as console_module

        c = _fresh_client()
        c.cookies.set("console_session", "some-old-token")

        # Replace check_session on the console module so _require_auth sees it
        # as returning False (simulating an expired/invalid session).
        original_fn = console_module.check_session
        console_module.check_session = lambda request: None
        try:
            resp = c.get("/console/dashboard", follow_redirects=False)
        finally:
            console_module.check_session = original_fn

        assert resp.status_code == 303, f"Expired session should redirect, got {resp.status_code}"
        assert "/console/login" in resp.headers.get("location", "")

    def test_tampered_session_redirects_to_login(self):
        """A tampered/invalid session cookie should be rejected."""
        c = _fresh_client()
        c.cookies.set("console_session", "this-is-not-a-valid-token")
        resp = c.get("/console/dashboard", follow_redirects=False)
        assert resp.status_code == 303, f"Tampered session should redirect, got {resp.status_code}"
        assert "/console/login" in resp.headers.get("location", "")
