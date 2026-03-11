"""Tests for Phase 5: Email channel + lead source tracking.

Tests the email service, email webhook, contact resolver email support,
dispatcher email routing, and lead_source field propagation.
"""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock

from app.services.email_service import parse_inbound_email, _extract_name, _extract_email
from app.models.schemas import NormalizedEvent, AgentConfig, Contact

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
AGENT = AgentConfig(
    id=AGENT_ID, name="Jane Smith", email="jane@calloway.ai",
    phone="+12155551000", twilio_number="+12155559999",
    style_profile={"tone": "professional"},
)


# ── Email parsing tests ──────────────────────────────────────

def test_parse_inbound_email_basic():
    """Parse a basic SendGrid inbound email payload."""
    payload = {
        "from": "Sarah Chen <sarah@example.com>",
        "to": "jane@calloway.ai",
        "subject": "Question about 123 Oak St",
        "text": "Hi, is this listing still available?",
        "html": "<p>Hi, is this listing still available?</p>",
        "Message-ID": "<abc123@example.com>",
    }
    result = parse_inbound_email(payload)

    assert result["from_address"] == "Sarah Chen <sarah@example.com>"
    assert result["from_name"] == "Sarah Chen"
    assert result["to_address"] == "jane@calloway.ai"
    assert result["subject"] == "Question about 123 Oak St"
    assert "still available" in result["text"]
    assert result["message_id"] == "<abc123@example.com>"


def test_parse_inbound_email_plain_address():
    """Parse email without display name."""
    payload = {
        "from": "sarah@example.com",
        "to": "jane@calloway.ai",
        "subject": "Hello",
        "text": "Hi",
    }
    result = parse_inbound_email(payload)
    assert result["from_name"] == "sarah"


def test_extract_name():
    assert _extract_name("Jane Smith <jane@test.com>") == "Jane Smith"
    assert _extract_name("jane@test.com") == "jane"
    assert _extract_name('"Dr. Smith" <dr@test.com>') == "Dr. Smith"


def test_extract_email():
    assert _extract_email("Jane <jane@test.com>") == "jane@test.com"
    assert _extract_email("jane@test.com") == "jane@test.com"


# ── Email service tests ──────────────────────────────────────

@patch("app.services.email_service.get_settings")
def test_send_email_not_configured(mock_settings):
    """When SendGrid key is missing, return not_configured status."""
    from app.services.email_service import send_email

    settings = MagicMock()
    settings.SENDGRID_API_KEY = ""
    mock_settings.return_value = settings

    result = send_email("to@test.com", "from@test.com", "Subject", "Body")
    assert result["status"] == "not_configured"


# ── Resolver email support tests ─────────────────────────────

@patch("app.pipeline.resolver.get_db_connection")
def test_resolver_email_channel_agent_check(mock_conn):
    """Resolver identifies agent commands from email channel."""
    from app.pipeline.resolver import resolve_contact

    event = NormalizedEvent(
        sender_phone="jane@calloway.ai",
        channel="email",
        body="Schedule meeting",
        timestamp=datetime.now(timezone.utc),
        provider_message_id="test",
        raw_payload={},
        agent_id=AGENT_ID,
    )

    contact, is_agent = resolve_contact(event, AGENT)
    assert is_agent is True
    assert contact is None


@patch("app.pipeline.resolver.get_db_connection")
def test_resolver_email_lookup_by_email(mock_conn):
    """Resolver can find contacts by email for email channel."""
    from app.pipeline.resolver import resolve_contact

    mock_ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    contact_row = {
        "id": UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        "agent_id": AGENT_ID,
        "name": "Sarah Chen",
        "phone": "+12675551234",
        "email": "sarah@example.com",
        "role": "buyer",
        "lifecycle_stage": "active_buyer",
        "preferences": {},
        "consent_status": "granted",
        "silent_mode": False,
        "interaction_count": 5,
        "language_detected": "en",
    }
    mock_ctx.execute.return_value.fetchone.return_value = contact_row

    event = NormalizedEvent(
        sender_phone="sarah@example.com",
        channel="email",
        body="Question about listing",
        timestamp=datetime.now(timezone.utc),
        provider_message_id="test",
        raw_payload={},
        agent_id=AGENT_ID,
    )

    contact, is_agent = resolve_contact(event, AGENT)
    assert is_agent is False
    assert contact is not None
    assert contact.name == "Sarah Chen"

    # Verify the SQL used OR for email matching
    call_args = mock_ctx.execute.call_args
    sql = call_args[0][0]
    assert "email" in sql


# ── Dispatcher email routing tests ───────────────────────────

@patch("app.pipeline.dispatcher.send_sms")
@patch("app.pipeline.dispatcher.send_client_message")
def test_dispatcher_routes_email_channel(mock_sms_client, mock_sms):
    """Dispatcher uses email service for email channel messages."""
    from app.pipeline.dispatcher import dispatch
    from app.models.schemas import AgentDecision

    contact = Contact(
        id=UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        agent_id=AGENT_ID, name="Sarah", phone="+12675551234",
        email="sarah@example.com", consent_status="granted",
    )

    decision = AgentDecision(response_text="Yes, that listing is available!")
    event = NormalizedEvent(
        sender_phone="sarah@example.com", channel="email",
        body="Is it available?", timestamp=datetime.now(timezone.utc),
        provider_message_id="test", raw_payload={}, agent_id=AGENT_ID,
    )

    with patch("app.pipeline.dispatcher._log_conversation"), \
         patch("app.pipeline.dispatcher._update_usage_metrics"), \
         patch("app.services.email_service.send_email", return_value={"status": "sent", "message_id": "test"}) as mock_send_email, \
         patch("app.services.email_service.get_db_connection"):
        dispatch(decision, event, contact, AGENT)

    # Should NOT call SMS
    mock_sms.assert_not_called()
    mock_sms_client.assert_not_called()

    # Should have called send_email for the email channel
    mock_send_email.assert_called_once()


# ── Lead source tracking tests ───────────────────────────────

def test_contact_model_has_lead_source():
    """Contact model has lead_source field."""
    contact = Contact(
        id=UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        agent_id=AGENT_ID, name="Test", phone="+1234567890",
        lead_source="email",
    )
    assert contact.lead_source == "email"


def test_contact_model_lead_source_defaults_none():
    """Lead source defaults to None."""
    contact = Contact(
        id=UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        agent_id=AGENT_ID, name="Test", phone="+1234567890",
    )
    assert contact.lead_source is None
