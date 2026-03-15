"""Tests for app/api/mobile/deps.py — JWT utilities and auth dependency."""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.api.mobile.deps import (
    create_access_token,
    create_refresh_token,
    get_current_agent,
    normalize_e164,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "test-secret-key-for-mobile-jwt-unit-tests"


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.MOBILE_JWT_SECRET = TEST_JWT_SECRET
    settings.ENVIRONMENT = "development"
    return settings


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.get.return_value = None  # no deny-list entry by default
    r.setex.return_value = True
    r.delete.return_value = True
    return r


# ---------------------------------------------------------------------------
# normalize_e164
# ---------------------------------------------------------------------------


class TestNormalizeE164:
    def test_valid_us_number(self):
        assert normalize_e164("+14155551234") == "+14155551234"

    def test_valid_uk_number(self):
        assert normalize_e164("+447911123456") == "+447911123456"

    def test_valid_short_number(self):
        assert normalize_e164("+11") == "+11"

    def test_strips_whitespace(self):
        assert normalize_e164("  +14155551234  ") == "+14155551234"

    def test_missing_plus_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            normalize_e164("14155551234")
        assert exc_info.value.status_code == 422

    def test_empty_string_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            normalize_e164("")
        assert exc_info.value.status_code == 422

    def test_letters_raise(self):
        with pytest.raises(HTTPException) as exc_info:
            normalize_e164("+1abc")
        assert exc_info.value.status_code == 422

    def test_plus_zero_start_raises(self):
        """E.164 country codes cannot start with 0."""
        with pytest.raises(HTTPException) as exc_info:
            normalize_e164("+0123456789")
        assert exc_info.value.status_code == 422

    def test_too_long_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            normalize_e164("+1234567890123456")  # 16 digits, max is 15
        assert exc_info.value.status_code == 422

    def test_plus_only_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            normalize_e164("+")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# create_access_token
# ---------------------------------------------------------------------------


class TestCreateAccessToken:
    @patch("app.api.mobile.deps.get_settings")
    def test_returns_valid_jwt(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings
        agent_id = str(uuid4())

        token = create_access_token(agent_id)

        assert isinstance(token, str)
        payload = jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])
        assert payload["agent_id"] == agent_id

    @patch("app.api.mobile.deps.get_settings")
    def test_payload_fields(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings
        agent_id = str(uuid4())

        token = create_access_token(agent_id)
        payload = jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])

        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload
        # exp should be ~30 minutes from now
        exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = exp_dt - now
        assert timedelta(minutes=29) < delta < timedelta(minutes=31)

    @patch("app.api.mobile.deps.get_settings")
    def test_unique_jti_per_call(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings
        agent_id = str(uuid4())

        t1 = create_access_token(agent_id)
        t2 = create_access_token(agent_id)

        p1 = jwt.decode(t1, TEST_JWT_SECRET, algorithms=["HS256"])
        p2 = jwt.decode(t2, TEST_JWT_SECRET, algorithms=["HS256"])
        assert p1["jti"] != p2["jti"]


# ---------------------------------------------------------------------------
# create_refresh_token
# ---------------------------------------------------------------------------


class TestCreateRefreshToken:
    @patch("app.api.mobile.deps.get_redis_pool")
    def test_returns_token_and_key(self, mock_get_pool, mock_redis):
        mock_get_pool.return_value = mock_redis
        agent_id = str(uuid4())

        token, key = create_refresh_token(agent_id)

        assert isinstance(token, str)
        assert len(token) > 0
        assert key == f"mobile_refresh:{token}"

    @patch("app.api.mobile.deps.get_redis_pool")
    def test_stores_in_redis(self, mock_get_pool, mock_redis):
        mock_get_pool.return_value = mock_redis
        agent_id = str(uuid4())

        token, key = create_refresh_token(agent_id)

        mock_redis.setex.assert_called_once_with(
            key, timedelta(days=30), agent_id
        )


# ---------------------------------------------------------------------------
# get_current_agent
# ---------------------------------------------------------------------------


class TestGetCurrentAgent:
    def _make_request(self, auth_header=None):
        request = MagicMock()
        headers = {}
        if auth_header is not None:
            headers["Authorization"] = auth_header
        request.headers = headers
        request.headers.get = lambda key, default=None: headers.get(key, default)
        return request

    @pytest.mark.asyncio
    @patch("app.api.mobile.deps.get_redis_pool")
    @patch("app.api.mobile.deps.get_settings")
    async def test_valid_token_returns_agent_id(
        self, mock_get_settings, mock_get_pool, mock_settings, mock_redis
    ):
        mock_get_settings.return_value = mock_settings
        mock_get_pool.return_value = mock_redis

        agent_id = str(uuid4())
        token = create_access_token(agent_id)
        request = self._make_request(f"Bearer {token}")

        result = await get_current_agent(request)
        assert result == agent_id

    @pytest.mark.asyncio
    @patch("app.api.mobile.deps.get_settings")
    async def test_expired_token_raises_401(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings

        agent_id = str(uuid4())
        payload = {
            "agent_id": agent_id,
            "type": "access",
            "jti": str(uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=35),
        }
        token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
        request = self._make_request(f"Bearer {token}")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_agent(request)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.api.mobile.deps.get_settings")
    async def test_malformed_token_raises_401(self, mock_get_settings, mock_settings):
        mock_get_settings.return_value = mock_settings
        request = self._make_request("Bearer not-a-valid-jwt")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_agent(request)
        assert exc_info.value.status_code == 401
        assert "malformed" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_missing_auth_header_raises_401(self):
        request = self._make_request()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_agent(request)
        assert exc_info.value.status_code == 401
        assert "not authenticated" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_non_bearer_auth_raises_401(self):
        request = self._make_request("Basic dXNlcjpwYXNz")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_agent(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("app.api.mobile.deps.get_redis_pool")
    @patch("app.api.mobile.deps.get_settings")
    async def test_revoked_token_raises_401(
        self, mock_get_settings, mock_get_pool, mock_settings, mock_redis
    ):
        mock_get_settings.return_value = mock_settings
        mock_redis.get.return_value = b"1"  # token is on deny list
        mock_get_pool.return_value = mock_redis

        agent_id = str(uuid4())
        token = create_access_token(agent_id)
        request = self._make_request(f"Bearer {token}")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_agent(request)
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.api.mobile.deps.get_redis_pool")
    @patch("app.api.mobile.deps.get_settings")
    async def test_wrong_token_type_raises_401(
        self, mock_get_settings, mock_get_pool, mock_settings, mock_redis
    ):
        mock_get_settings.return_value = mock_settings
        mock_get_pool.return_value = mock_redis

        payload = {
            "agent_id": str(uuid4()),
            "type": "refresh",  # wrong type
            "jti": str(uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
        request = self._make_request(f"Bearer {token}")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_agent(request)
        assert exc_info.value.status_code == 401
        assert "token type" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.api.mobile.deps.get_redis_pool")
    @patch("app.api.mobile.deps.get_settings")
    async def test_redis_failure_fails_open(
        self, mock_get_settings, mock_get_pool, mock_settings
    ):
        """When Redis is unavailable for deny-list check, the request should still succeed."""
        mock_get_settings.return_value = mock_settings
        mock_get_pool.side_effect = Exception("Redis connection refused")

        agent_id = str(uuid4())
        token = create_access_token(agent_id)
        request = self._make_request(f"Bearer {token}")

        result = await get_current_agent(request)
        assert result == agent_id
