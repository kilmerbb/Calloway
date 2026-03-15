"""Tests for app/api/mobile/auth.py — mobile auth endpoints."""

import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "test-secret-key-for-mobile-auth-tests-0123456789"
TEST_AGENT_ID = str(uuid4())
TEST_PHONE = "+14155551234"
TEST_TWILIO_NUMBER = "+18005551234"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.MOBILE_JWT_SECRET = TEST_JWT_SECRET
    settings.ENVIRONMENT = "development"
    settings.TWILIO_PHONE_NUMBER = TEST_TWILIO_NUMBER
    settings.REDIS_URL = "redis://localhost:6379/0"
    return settings


@pytest.fixture
def mock_redis():
    """A MagicMock that behaves like a Redis client."""
    r = MagicMock()
    r.ping.return_value = True
    r.get.return_value = None
    r.setex.return_value = True
    r.delete.return_value = True
    r.incr.return_value = 1
    r.expire.return_value = True
    r.ttl.return_value = -1
    return r


def _make_async_db_ctx(rows=None, fetchone_result=None):
    """Build a mock async DB connection context manager.

    If *fetchone_result* is provided it is returned by result.fetchone().
    Otherwise *rows* (default None) is used.
    """
    result_mock = AsyncMock()
    if fetchone_result is not None:
        result_mock.fetchone.return_value = fetchone_result
    else:
        result_mock.fetchone.return_value = rows

    conn = AsyncMock()
    conn.execute.return_value = result_mock

    @asynccontextmanager
    async def _ctx():
        yield conn

    return _ctx


def _build_access_token(agent_id: str, secret: str = TEST_JWT_SECRET, **overrides) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "agent_id": agent_id,
        "type": "access",
        "jti": str(uuid4()),
        "exp": now + timedelta(minutes=30),
        "iat": now,
        **overrides,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Patch helper — applies all common patches for auth endpoints
# ---------------------------------------------------------------------------

def _auth_patches(mock_settings_obj, mock_redis_obj, db_ctx_factory):
    """Return a list of active patches for the auth endpoints."""
    return [
        patch("app.api.mobile.auth.get_settings", return_value=mock_settings_obj),
        patch("app.api.mobile.deps.get_settings", return_value=mock_settings_obj),
        patch("app.api.mobile.auth.get_redis_pool", return_value=mock_redis_obj),
        patch("app.api.mobile.deps.get_redis_pool", return_value=mock_redis_obj),
        patch("app.api.mobile.auth.get_async_db_connection", side_effect=db_ctx_factory),
        patch("app.api.mobile.auth.send_sms"),
    ]


# ---------------------------------------------------------------------------
# POST /api/v1/mobile/auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_sends_code_to_valid_phone(self, mock_settings, mock_redis):
        agent_row = {"id": TEST_AGENT_ID, "phone": TEST_PHONE, "twilio_number": TEST_TWILIO_NUMBER}
        db_ctx = _make_async_db_ctx(fetchone_result=agent_row)

        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post("/api/v1/mobile/auth/login", json={"phone": TEST_PHONE})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["expires_in"] == 300

    def test_anti_enumeration_unknown_phone(self, mock_settings, mock_redis):
        """Unknown phone should still return 200 with the same message shape."""
        db_ctx = _make_async_db_ctx(fetchone_result=None)

        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post("/api/v1/mobile/auth/login", json={"phone": "+19995550000"})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data.get("dev_code") is None

    def test_returns_dev_code_in_development(self, mock_settings, mock_redis):
        mock_settings.ENVIRONMENT = "development"
        agent_row = {"id": TEST_AGENT_ID, "phone": TEST_PHONE, "twilio_number": None}
        db_ctx = _make_async_db_ctx(fetchone_result=agent_row)

        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post("/api/v1/mobile/auth/login", json={"phone": TEST_PHONE})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("dev_code") is not None
        assert len(data["dev_code"]) == 6

    def test_503_when_redis_unavailable(self, mock_settings):
        bad_redis = MagicMock()
        bad_redis.ping.side_effect = Exception("Connection refused")

        patches = [
            patch("app.api.mobile.auth.get_settings", return_value=mock_settings),
            patch("app.api.mobile.deps.get_settings", return_value=mock_settings),
            patch("app.api.mobile.auth.get_redis_pool", return_value=bad_redis),
            patch("app.api.mobile.deps.get_redis_pool", return_value=bad_redis),
        ]
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post("/api/v1/mobile/auth/login", json={"phone": TEST_PHONE})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/v1/mobile/auth/verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_valid_code_login(self, mock_settings, mock_redis):
        code = "123456"
        mock_redis.get.side_effect = lambda key: {
            f"mobile_verify_attempts:{TEST_PHONE}": None,
            f"mobile_login_code:{TEST_PHONE}": code.encode(),
        }.get(key)

        agent_row = {"id": TEST_AGENT_ID}
        db_ctx = _make_async_db_ctx(fetchone_result=agent_row)

        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/verify",
                json={"phone": TEST_PHONE, "code": code},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 1800

    def test_invalid_code(self, mock_settings, mock_redis):
        mock_redis.get.side_effect = lambda key: {
            f"mobile_verify_attempts:{TEST_PHONE}": None,
            f"mobile_login_code:{TEST_PHONE}": b"999999",
        }.get(key)

        db_ctx = _make_async_db_ctx()
        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/verify",
                json={"phone": TEST_PHONE, "code": "000000"},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 401

    def test_rate_limiting_429(self, mock_settings, mock_redis):
        """After 5 failed attempts, returns 429."""
        mock_redis.get.side_effect = lambda key: {
            f"mobile_verify_attempts:{TEST_PHONE}": b"5",
            f"mobile_login_code:{TEST_PHONE}": b"123456",
        }.get(key)

        db_ctx = _make_async_db_ctx()
        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/verify",
                json={"phone": TEST_PHONE, "code": "123456"},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 429
        assert "too many" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/v1/mobile/auth/refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    def test_valid_refresh(self, mock_settings, mock_redis):
        refresh_token = secrets.token_urlsafe(48)
        mock_redis.get.side_effect = lambda key: {
            f"mobile_refresh:{refresh_token}": TEST_AGENT_ID.encode(),
            f"mobile_refresh_rate:{refresh_token[:16]}": None,
        }.get(key)

        agent_row = {"id": TEST_AGENT_ID}
        db_ctx = _make_async_db_ctx(fetchone_result=agent_row)

        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_invalid_refresh_token(self, mock_settings, mock_redis):
        mock_redis.get.return_value = None  # no token in Redis

        db_ctx = _make_async_db_ctx()
        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/refresh",
                json={"refresh_token": "nonexistent-token"},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 401

    def test_rate_limiting_429(self, mock_settings, mock_redis):
        refresh_token = secrets.token_urlsafe(48)
        mock_redis.get.side_effect = lambda key: {
            f"mobile_refresh_rate:{refresh_token[:16]}": b"10",
            f"mobile_refresh:{refresh_token}": TEST_AGENT_ID.encode(),
        }.get(key)

        db_ctx = _make_async_db_ctx()
        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 429
        assert "too many" in resp.json()["detail"].lower()

    def test_503_when_redis_unavailable(self, mock_settings):
        bad_redis = MagicMock()
        bad_redis.ping.side_effect = Exception("Connection refused")

        patches = [
            patch("app.api.mobile.auth.get_settings", return_value=mock_settings),
            patch("app.api.mobile.deps.get_settings", return_value=mock_settings),
            patch("app.api.mobile.auth.get_redis_pool", return_value=bad_redis),
            patch("app.api.mobile.deps.get_redis_pool", return_value=bad_redis),
        ]
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/refresh",
                json={"refresh_token": "some-token"},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/v1/mobile/auth/logout
# ---------------------------------------------------------------------------


class TestLogout:
    def test_revokes_jwt_and_refresh_token(self, mock_settings, mock_redis):
        access_token = _build_access_token(TEST_AGENT_ID)
        refresh_token = secrets.token_urlsafe(48)

        # get_current_agent will call get() for deny-list check
        mock_redis.get.return_value = None

        db_ctx = _make_async_db_ctx()
        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/logout",
                json={"refresh_token": refresh_token},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"

        # Verify JWT was added to deny list (setex called with mobile_jwt_deny:*)
        deny_calls = [
            call for call in mock_redis.setex.call_args_list
            if str(call).startswith("call('mobile_jwt_deny:")
               or (len(call[0]) > 0 and str(call[0][0]).startswith("mobile_jwt_deny:"))
        ]
        assert len(deny_calls) >= 1

        # Verify refresh token was deleted
        mock_redis.delete.assert_any_call(f"mobile_refresh:{refresh_token}")

    def test_logout_without_refresh_token(self, mock_settings, mock_redis):
        access_token = _build_access_token(TEST_AGENT_ID)
        mock_redis.get.return_value = None

        db_ctx = _make_async_db_ctx()
        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/logout",
                json={},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200

    def test_logout_requires_auth(self, mock_settings, mock_redis):
        db_ctx = _make_async_db_ctx()
        patches = _auth_patches(mock_settings, mock_redis, db_ctx)
        for p in patches:
            p.start()
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/mobile/auth/logout",
                json={"refresh_token": "some-token"},
            )
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 401
