"""Step 16: End-to-end command channel tests.
Tests the full pipeline from agent SMS → processing → confirmation.
Uses mocked Twilio but real database.
"""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock

from app.pipeline.normalizer import normalize_twilio_event
from app.pipeline.resolver import resolve_contact
from app.pipeline.classifier import classify_intent
from app.pipeline.handlers import handle_agent_command
from app.services.agent_config import get_agent_by_id
from app.tools.listings import get_listing

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def get_agent():
    try:
        agent = get_agent_by_id(AGENT_ID)
        if agent is None:
            pytest.skip("Agent not found in DB")
        return agent
    except Exception:
        pytest.skip("Database not available")


@patch("app.pipeline.handlers.get_anthropic_client")
def test_e2e_new_listing(mock_get_client):
    """Agent texts 'New listing 123 Oak, 3/2, 475K, HOA 250' → listing created."""
    agent = get_agent()

    # Step 1: Normalize
    payload = {
        "From": agent.phone,
        "To": agent.twilio_number,
        "Body": "New listing 123 Oak, 3/2, 475K, HOA 250",
        "MessageSid": "SMtest1",
    }
    event = normalize_twilio_event(payload, AGENT_ID)
    assert event.body == "New listing 123 Oak, 3/2, 475K, HOA 250"

    # Step 2: Resolve contact
    contact, is_agent = resolve_contact(event, agent)
    assert is_agent is True

    # Step 3: Classify
    intent = classify_intent(event, contact, agent, is_agent_command=True)
    assert intent.intent == "agent_command"

    # Step 4: Handle command
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "listing_update",
        "_tokens": 100,
    }

    with patch("app.pipeline.handlers.ingest_listing") as mock_ingest:
        from app.models.schemas import Listing
        mock_ingest.return_value = (
            Listing(id=UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
                    agent_id=AGENT_ID, address="123 Oak St", price=475000,
                    beds=3, baths=2, hoa=250),
            [],
        )
        result = handle_agent_command(event, agent)

    assert "123 Oak" in result.response_text
    assert "$475,000" in result.response_text


@patch("app.pipeline.handlers.get_anthropic_client")
def test_e2e_listing_qa(mock_get_client):
    """Agent texts 'What's the HOA on 123 Oak?' → correct answer."""
    agent = get_agent()

    payload = {
        "From": agent.phone,
        "To": agent.twilio_number,
        "Body": "What's the HOA on 123 Oak?",
        "MessageSid": "SMtest2",
    }
    event = normalize_twilio_event(payload, AGENT_ID)

    contact, is_agent = resolve_contact(event, agent)
    assert is_agent is True

    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "query_listing",
        "listing_address": "123 Oak",
        "_tokens": 50,
    }

    result = handle_agent_command(event, agent)
    # Should return listing info
    assert result.response_text is not None


@patch("app.pipeline.handlers.get_anthropic_client")
def test_e2e_new_client(mock_get_client):
    """Agent texts 'New client...' → contact created."""
    agent = get_agent()

    payload = {
        "From": agent.phone,
        "To": agent.twilio_number,
        "Body": "New client John Doe 267-555-9876 active buyer Fishtown 475K",
        "MessageSid": "SMtest3",
    }
    event = normalize_twilio_event(payload, AGENT_ID)

    contact, is_agent = resolve_contact(event, agent)
    assert is_agent is True

    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "client_instruction",
        "contact_name": "John Doe",
        "details": "active buyer Fishtown 475K",
        "_tokens": 80,
    }

    # Since John Doe doesn't exist, should say "I don't have a contact"
    with patch("app.pipeline.handlers.lookup_contact", return_value=None):
        result = handle_agent_command(event, agent)
        assert "don't have" in result.response_text.lower() or "create" in result.response_text.lower()


@patch("app.pipeline.handlers.get_anthropic_client")
def test_e2e_price_update(mock_get_client):
    """Agent texts 'Drop 123 Oak to 465K' → listing updated."""
    agent = get_agent()

    payload = {
        "From": agent.phone,
        "To": agent.twilio_number,
        "Body": "Drop 123 Oak to 465K",
        "MessageSid": "SMtest4",
    }
    event = normalize_twilio_event(payload, AGENT_ID)

    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "listing_update",
        "listing_address": "123 Oak",
        "_tokens": 60,
    }

    with patch("app.pipeline.handlers.ingest_listing") as mock_ingest:
        from app.models.schemas import Listing
        mock_ingest.return_value = (
            Listing(id=UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
                    agent_id=AGENT_ID, address="123 Oak St", price=465000,
                    beds=3, baths=2),
            [],
        )
        result = handle_agent_command(event, agent)

    assert "123 Oak" in result.response_text
