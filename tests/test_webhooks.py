"""Tests for Twilio webhook endpoints."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from uuid import UUID

from app.main import app
from app.models.schemas import AgentConfig

TEST_AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

client = TestClient(app)


def make_twilio_payload(from_="+12675551234", to="+12155559999", body="Hello"):
    return {
        "From": from_,
        "To": to,
        "Body": body,
        "MessageSid": "SM" + "a" * 32,
        "AccountSid": "AC" + "b" * 32,
        "NumMedia": "0",
    }


def mock_agent():
    return AgentConfig(
        id=TEST_AGENT_ID, name="Jane Smith", email="jane@test.com",
        phone="+12155551000", twilio_number="+12155559999",
    )


@patch("app.api.webhooks.validate_twilio_signature", return_value=True)
@patch("app.api.webhooks.get_agent_by_twilio_number")
def test_twilio_inbound_valid(mock_get_agent, mock_validate):
    mock_get_agent.return_value = mock_agent()
    payload = make_twilio_payload()
    response = client.post("/webhooks/twilio/inbound", data=payload)
    assert response.status_code == 200
    assert "Response" in response.text


@patch("app.api.webhooks.validate_twilio_signature", return_value=False)
def test_twilio_inbound_invalid_signature(mock_validate):
    payload = make_twilio_payload()
    response = client.post("/webhooks/twilio/inbound", data=payload)
    assert response.status_code == 403


@patch("app.api.webhooks.validate_twilio_signature", return_value=True)
@patch("app.api.webhooks.get_agent_by_twilio_number", return_value=None)
def test_twilio_inbound_unknown_number(mock_get_agent, mock_validate):
    payload = make_twilio_payload(to="+19999999999")
    response = client.post("/webhooks/twilio/inbound", data=payload)
    assert response.status_code == 200  # Still 200 for Twilio


def test_twilio_status():
    payload = {
        "MessageSid": "SM" + "a" * 32,
        "MessageStatus": "delivered",
    }
    response = client.post("/webhooks/twilio/status", data=payload)
    assert response.status_code == 200


@patch("app.api.webhooks.validate_twilio_signature", return_value=True)
@patch("app.api.webhooks.get_agent_by_twilio_number")
def test_twilio_inbound_resolves_agent(mock_get_agent, mock_validate):
    agent = mock_agent()
    mock_get_agent.return_value = agent
    payload = make_twilio_payload()
    response = client.post("/webhooks/twilio/inbound", data=payload)
    assert response.status_code == 200
    mock_get_agent.assert_called_once_with("+12155559999")
