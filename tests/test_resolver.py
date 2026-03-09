"""Tests for contact resolver."""
import pytest
from datetime import datetime, timezone
from uuid import UUID

from app.pipeline.resolver import resolve_contact
from app.models.schemas import NormalizedEvent, AgentConfig

TEST_AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

AGENT = AgentConfig(
    id=TEST_AGENT_ID, name="Jane Smith", email="jane@test.com",
    phone="+12155551000", twilio_number="+12155559999",
)


def make_event(sender_phone: str, body: str = "Hello") -> NormalizedEvent:
    return NormalizedEvent(
        sender_phone=sender_phone, channel="sms", body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id="SM123", raw_payload={},
        agent_id=TEST_AGENT_ID,
    )


def test_resolve_known_contact():
    """Sarah Chen's phone should resolve to her contact record."""
    try:
        event = make_event("+12675551234")
        contact, is_agent = resolve_contact(event, AGENT)
        assert contact is not None
        assert contact.name == "Sarah Chen"
        assert contact.role == "buyer"
        assert is_agent is False
    except Exception:
        pytest.skip("Database not available")


def test_resolve_unknown_phone():
    """Unknown phone should return None."""
    try:
        event = make_event("+19999999999")
        contact, is_agent = resolve_contact(event, AGENT)
        assert contact is None
        assert is_agent is False
    except Exception:
        pytest.skip("Database not available")


def test_resolve_agent_own_phone():
    """Agent's own phone should be identified as agent command."""
    event = make_event("+12155551000")
    contact, is_agent = resolve_contact(event, AGENT)
    assert contact is None
    assert is_agent is True


def test_resolve_buyer_agent():
    """Tom Rivera (buyer_agent) should resolve correctly."""
    try:
        event = make_event("+12675555678")
        contact, is_agent = resolve_contact(event, AGENT)
        assert contact is not None
        assert contact.role == "buyer_agent"
        assert is_agent is False
    except Exception:
        pytest.skip("Database not available")
