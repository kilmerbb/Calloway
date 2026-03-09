"""Tests for message handlers (Steps 10, 15, 21)."""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock

from app.pipeline.handlers import (
    handle_agent_command, handle_listing_qa, handle_template,
)
from app.models.schemas import NormalizedEvent, AgentConfig, Contact, Listing

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

AGENT = AgentConfig(
    id=AGENT_ID, name="Jane Smith", email="jane@test.com",
    phone="+12155551000", twilio_number="+12155559999",
    style_profile={"tone": "casual and friendly", "emoji": "occasionally"},
)


def make_event(body: str) -> NormalizedEvent:
    return NormalizedEvent(
        sender_phone="+12155551000", channel="sms", body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id="SM123", raw_payload={}, agent_id=AGENT_ID,
    )


# --- Step 10: Agent Command Tests ---

@patch("app.pipeline.handlers.get_anthropic_client")
def test_command_listing_update(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "listing_update",
        "contact_name": None,
        "listing_address": "200 Front St",
        "details": "",
        "time_reference": None,
        "raw_data": "New listing 200 Front St, 3/2, 465K",
        "_tokens": 100,
    }
    mock_client.compose = MagicMock(return_value="Test")

    # Mock ingest_listing to avoid DB
    with patch("app.pipeline.handlers.ingest_listing") as mock_ingest:
        mock_listing = Listing(
            id=UUID("c4eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
            agent_id=AGENT_ID, address="200 Front St", price=465000,
            beds=3, baths=2,
        )
        mock_ingest.return_value = (mock_listing, ["sqft", "lockbox"])

        event = make_event("New listing 200 Front St, 3/2, 465K")
        result = handle_agent_command(event, AGENT)

        assert "200 Front St" in result.response_text
        assert "$465,000" in result.response_text


@patch("app.pipeline.handlers.get_anthropic_client")
def test_command_gap_query(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "query_gap",
        "_tokens": 50,
    }

    with patch("app.pipeline.handlers.analyze_contact_gaps") as mock_gaps:
        mock_gaps.return_value = [
            {
                "contact": Contact(
                    id=UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
                    agent_id=AGENT_ID, name="Sarah Chen", phone="+12675551234",
                    lifecycle_stage="active_buyer",
                ),
                "days_since_contact": 11,
                "lifecycle_stage": "active_buyer",
                "suggested_action": "Send listing alert",
            }
        ]

        event = make_event("Who needs follow-up?")
        result = handle_agent_command(event, AGENT)
        assert "Sarah Chen" in result.response_text
        assert "1 client" in result.response_text


@patch("app.pipeline.handlers.get_anthropic_client")
def test_command_status_change(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "status_change",
        "contact_name": None,
        "time_reference": None,
        "_tokens": 50,
    }

    with patch("app.pipeline.handlers.get_db_connection"):
        event = make_event("I'm back")
        result = handle_agent_command(event, AGENT)
        assert "available" in result.response_text.lower()


@patch("app.pipeline.handlers.get_anthropic_client")
def test_command_contact_query(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "query_contact",
        "contact_name": "Sarah",
        "_tokens": 50,
    }

    sarah = Contact(
        id=UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        agent_id=AGENT_ID, name="Sarah Chen", phone="+12675551234",
        role="buyer", lifecycle_stage="active_buyer",
        last_contact_at=datetime.now(timezone.utc),
    )

    with patch("app.pipeline.handlers.lookup_contact", return_value=sarah):
        with patch("app.pipeline.handlers.get_db_connection") as mock_conn:
            mock_ctx = MagicMock()
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute.return_value.fetchall.return_value = []

            event = make_event("What's going on with Sarah?")
            result = handle_agent_command(event, AGENT)
            assert "Sarah Chen" in result.response_text


# --- Step 15: Listing Q&A Tests ---

@patch("app.pipeline.handlers.get_anthropic_client")
def test_listing_qa(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.compose.return_value = "$250/month covering water, trash, and exterior maintenance."

    listing = Listing(
        id=UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        agent_id=AGENT_ID, address="123 Oak St", price=475000,
        beds=3, baths=2, hoa=250,
        features=["renovated kitchen", "hardwood floors"],
    )

    event = make_event("What's the HOA on 123 Oak?")
    result = handle_listing_qa(event, None, AGENT, listing)
    assert "$250" in result.response_text
    assert result.model_used == "haiku"


# --- Step 21: Template Responder Tests ---

def test_template_showing_confirmation():
    event = make_event("confirm")
    result = handle_template(
        event, None, AGENT, "showing_confirmation",
        address="123 Oak St", time="2pm", lockbox="4521",
    )
    assert "123 Oak St" in result.response_text
    assert "4521" in result.response_text
    assert result.tokens_used == 0


def test_template_acknowledgment():
    event = make_event("thanks")
    result = handle_template(event, None, AGENT, "acknowledgment")
    assert "Jane Smith" in result.response_text
    assert result.tokens_used == 0


def test_template_escalation_ack():
    event = make_event("offer?")
    result = handle_template(event, None, AGENT, "escalation_ack")
    assert "Jane Smith" in result.response_text
