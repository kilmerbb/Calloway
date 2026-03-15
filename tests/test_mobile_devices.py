"""Tests for mobile device registration/unregistration endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.api.mobile.deps import get_current_agent

AGENT_ID = "12345678-1234-1234-1234-123456789012"


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_agent] = lambda: AGENT_ID
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


# -----------------------------------------------------------------------
# POST /api/v1/mobile/devices/register
# -----------------------------------------------------------------------


class TestRegisterDevice:
    """Tests for the register_device endpoint."""

    @patch("app.api.mobile.devices.register_device_token")
    def test_register_device_success(self, mock_register, client):
        """Registers a device token and returns device_id."""
        mock_register.return_value = {"id": "device-abc-123"}

        resp = client.post(
            "/api/v1/mobile/devices/register",
            json={
                "fcm_token": "fake-fcm-token-value",
                "device_name": "iPhone 15",
                "platform": "ios",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "registered"
        assert body["device_id"] == "device-abc-123"

        # Verify register_device_token was called with correct args
        mock_register.assert_called_once_with(
            UUID(AGENT_ID),
            "fake-fcm-token-value",
            "iPhone 15",
            "ios",
        )

    @patch("app.api.mobile.devices.register_device_token")
    def test_register_device_minimal_payload(self, mock_register, client):
        """Registers with only fcm_token (device_name and platform optional)."""
        mock_register.return_value = {"id": "device-xyz-789"}

        resp = client.post(
            "/api/v1/mobile/devices/register",
            json={"fcm_token": "another-token"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "registered"
        assert body["device_id"] == "device-xyz-789"

        mock_register.assert_called_once_with(
            UUID(AGENT_ID),
            "another-token",
            None,
            None,
        )

    def test_register_device_empty_token_rejected(self, client):
        """Rejects empty fcm_token with 422."""
        resp = client.post(
            "/api/v1/mobile/devices/register",
            json={"fcm_token": ""},
        )

        assert resp.status_code == 422

    def test_register_device_whitespace_token_rejected(self, client):
        """Rejects whitespace-only fcm_token with 422."""
        resp = client.post(
            "/api/v1/mobile/devices/register",
            json={"fcm_token": "   "},
        )

        assert resp.status_code == 422

    def test_register_device_missing_token_rejected(self, client):
        """Rejects request with missing fcm_token field."""
        resp = client.post(
            "/api/v1/mobile/devices/register",
            json={},
        )

        assert resp.status_code == 422

    @patch("app.api.mobile.devices.register_device_token")
    def test_register_device_returns_empty_id_when_none(self, mock_register, client):
        """Returns empty device_id when register_device_token returns None."""
        mock_register.return_value = None

        resp = client.post(
            "/api/v1/mobile/devices/register",
            json={"fcm_token": "some-token"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "registered"
        assert body["device_id"] == ""


# -----------------------------------------------------------------------
# POST /api/v1/mobile/devices/unregister
# -----------------------------------------------------------------------


class TestUnregisterDevice:
    """Tests for the unregister_device endpoint."""

    @patch("app.api.mobile.devices.unregister_device_token")
    def test_unregister_device_success(self, mock_unregister, client):
        """Unregisters a device token with ownership check via agent_id."""
        mock_unregister.return_value = True

        resp = client.post(
            "/api/v1/mobile/devices/unregister",
            json={"fcm_token": "token-to-remove"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "unregistered"

        # Verify agent_id is passed for ownership check
        mock_unregister.assert_called_once_with(
            "token-to-remove",
            UUID(AGENT_ID),
        )

    def test_unregister_device_empty_token_rejected(self, client):
        """Rejects empty fcm_token with 422."""
        resp = client.post(
            "/api/v1/mobile/devices/unregister",
            json={"fcm_token": ""},
        )

        assert resp.status_code == 422

    def test_unregister_device_whitespace_token_rejected(self, client):
        """Rejects whitespace-only fcm_token with 422."""
        resp = client.post(
            "/api/v1/mobile/devices/unregister",
            json={"fcm_token": "   "},
        )

        assert resp.status_code == 422

    def test_unregister_device_missing_token_rejected(self, client):
        """Rejects request with missing fcm_token field."""
        resp = client.post(
            "/api/v1/mobile/devices/unregister",
            json={},
        )

        assert resp.status_code == 422

    @patch("app.api.mobile.devices.unregister_device_token")
    def test_unregister_device_passes_agent_id(self, mock_unregister, client):
        """Confirms the agent_id UUID is passed to unregister_device_token."""
        mock_unregister.return_value = True

        client.post(
            "/api/v1/mobile/devices/unregister",
            json={"fcm_token": "another-token"},
        )

        call_args = mock_unregister.call_args[0]
        assert call_args[0] == "another-token"
        assert call_args[1] == UUID(AGENT_ID)
        assert isinstance(call_args[1], UUID)
