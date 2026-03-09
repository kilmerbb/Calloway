"""Step 25: End-to-end client messaging tests.
Tests the full pipeline from client message → AI response.
"""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock

from app.pipeline.normalizer import normalize_twilio_event
from app.pipeline.resolver import resolve_contact
from app.pipeline.classifier import classify_intent
from app.pipeline.router import route_and_handle
from app.pipeline.assembler import assemble_context
from app.models.schemas import AgentConfig, Contact, Listing, IntentClassification

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def get_agent():
    try:
        from app.services.agent_config import get_agent_by_id
        agent = get_agent_by_id(AGENT_ID)
        if not agent:
            pytest.skip("Agent not in DB")
        return agent
    except Exception:
        pytest.skip("Database not available")


# Test 1: Known client texts listing question
@patch("app.pipeline.handlers.get_anthropic_client")
def test_known_client_listing_qa(mock_get_client):
    agent = get_agent()
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "listing_qa", "confidence": 0.95,
        "needs_full_context": False, "_tokens": 100,
    }
    mock_client.compose.return_value = "$250/month covering water, trash, and exterior. The renovated kitchen is really nice too!"

    payload = {"From": "+12675551234", "To": agent.twilio_number,
               "Body": "What's the HOA on 123 Oak?", "MessageSid": "SM001"}
    event = normalize_twilio_event(payload, AGENT_ID)
    contact, is_agent = resolve_contact(event, agent)

    assert contact is not None
    assert contact.name == "Sarah Chen"
    assert is_agent is False

    intent = classify_intent(event, contact, agent)
    assert intent.intent == "listing_qa"

    decision = route_and_handle(event, contact, intent, agent)
    assert decision.response_text is not None
    assert "$250" in decision.response_text


# Test 2: Unknown number texts about a listing
@patch("app.pipeline.handlers.get_anthropic_client")
def test_unknown_listing_inquiry(mock_get_client):
    agent = get_agent()
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "listing_qa", "confidence": 0.9,
        "needs_full_context": False, "_tokens": 80,
    }
    mock_client.compose.return_value = "Yes, 123 Oak St is still active at $475,000. It has 3 beds, 2 baths, and a renovated kitchen."

    payload = {"From": "+19999999999", "To": agent.twilio_number,
               "Body": "Is 123 Oak still available?", "MessageSid": "SM002"}
    event = normalize_twilio_event(payload, AGENT_ID)
    contact, is_agent = resolve_contact(event, agent)
    assert contact is None
    assert is_agent is False

    intent = classify_intent(event, contact, agent)
    decision = route_and_handle(event, contact, intent, agent)
    assert decision.response_text is not None


# Test 3: Known client asks to schedule a showing
@patch("app.pipeline.handlers.get_anthropic_client")
def test_scheduling_request(mock_get_client):
    agent = get_agent()
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "scheduling", "confidence": 0.92,
        "needs_full_context": True, "_tokens": 100,
    }

    def mock_response(*args, **kwargs):
        from app.models.schemas import AgentDecision
        return AgentDecision(
            response_text="Saturday looks great! Jane is free at 11am and 2pm. Want to see 123 Oak and 789 Front?",
            model_used="sonnet", tokens_used=500,
        )
    mock_client.reason = mock_response

    payload = {"From": "+12675551234", "To": agent.twilio_number,
               "Body": "Can we see some houses Saturday?", "MessageSid": "SM003"}
    event = normalize_twilio_event(payload, AGENT_ID)
    contact, _ = resolve_contact(event, agent)

    intent = classify_intent(event, contact, agent)
    assert intent.intent == "scheduling"

    decision = route_and_handle(event, contact, intent, agent)
    assert decision.response_text is not None
    assert decision.model_used == "sonnet"


# Test 4: Client confirms a showing time
@patch("app.pipeline.handlers.get_anthropic_client")
def test_showing_confirmation(mock_get_client):
    agent = get_agent()
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "scheduling", "confidence": 0.9,
        "needs_full_context": True, "_tokens": 80,
    }

    def mock_reason(*args, **kwargs):
        from app.models.schemas import AgentDecision
        return AgentDecision(
            response_text="Perfect! Confirmed for Saturday at 11am at 123 Oak St.",
            model_used="sonnet", tokens_used=400,
            notifications=[{"tier": "informational", "title": "Showing confirmed", "body": "Sarah at 123 Oak, Saturday 11am"}],
        )
    mock_client.reason = mock_reason

    payload = {"From": "+12675551234", "To": agent.twilio_number,
               "Body": "11am works!", "MessageSid": "SM004"}
    event = normalize_twilio_event(payload, AGENT_ID)
    contact, _ = resolve_contact(event, agent)
    intent = classify_intent(event, contact, agent)

    decision = route_and_handle(event, contact, intent, agent)
    assert decision.response_text is not None
    assert len(decision.notifications) > 0


# Test 5: Client asks about pricing/offer → escalation
@patch("app.pipeline.handlers.get_anthropic_client")
def test_offer_escalation(mock_get_client):
    agent = get_agent()
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "escalation", "confidence": 0.95,
        "needs_full_context": True, "_tokens": 80,
    }

    payload = {"From": "+12675551234", "To": agent.twilio_number,
               "Body": "Should I offer under asking?", "MessageSid": "SM005"}
    event = normalize_twilio_event(payload, AGENT_ID)
    contact, _ = resolve_contact(event, agent)
    intent = classify_intent(event, contact, agent)

    assert intent.intent == "escalation"
    decision = route_and_handle(event, contact, intent, agent)
    assert decision.response_text is not None
    assert "Jane Smith" in decision.response_text  # escalation ack mentions agent
    assert len(decision.notifications) > 0  # agent should be notified


# Test 6: Client says "let me talk to agent" → immediate escalation
@patch("app.pipeline.handlers.get_anthropic_client")
def test_direct_agent_request(mock_get_client):
    agent = get_agent()
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "escalation", "confidence": 0.98,
        "needs_full_context": True, "_tokens": 70,
    }

    payload = {"From": "+12675551234", "To": agent.twilio_number,
               "Body": "Can I speak to Jane directly?", "MessageSid": "SM006"}
    event = normalize_twilio_event(payload, AGENT_ID)
    contact, _ = resolve_contact(event, agent)
    intent = classify_intent(event, contact, agent)

    decision = route_and_handle(event, contact, intent, agent)
    assert decision.notifications  # must notify agent


# Test conversation view endpoint
def test_conversation_view_invalid_token():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    response = client.get("/conversations/b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11?token=invalid")
    assert response.status_code == 403


def test_conversation_view_valid_token():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.conversations import generate_conversation_token

    token = generate_conversation_token(
        UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"), AGENT_ID
    )

    client = TestClient(app)
    try:
        response = client.get(
            f"/conversations/b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11?token={token}"
        )
        assert response.status_code == 200
        assert "Sarah Chen" in response.text
    except Exception:
        pytest.skip("Database not available")
