"""Tests for intent classifier."""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch

from app.pipeline.classifier import classify_intent, _keyword_classify
from app.models.schemas import NormalizedEvent, Contact, AgentConfig

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONTACT_ID = UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

AGENT = AgentConfig(
    id=AGENT_ID, name="Jane Smith", email="jane@test.com",
    phone="+12155551000", twilio_number="+12155559999",
)

SARAH = Contact(
    id=CONTACT_ID, agent_id=AGENT_ID, name="Sarah Chen",
    phone="+12675551234", role="buyer", lifecycle_stage="active_buyer",
)


def make_event(body: str, sender="+12675551234") -> NormalizedEvent:
    return NormalizedEvent(
        sender_phone=sender, channel="sms", body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id="SM123", raw_payload={}, agent_id=AGENT_ID,
    )


def test_agent_command_skips_llm():
    """Agent commands should be detected without LLM call."""
    event = make_event("Text Sarah and confirm Thursday", sender="+12155551000")
    result = classify_intent(event, None, AGENT, is_agent_command=True)
    assert result.intent == "agent_command"
    assert result.sender_type == "agent_command"
    assert result.confidence == 1.0


def test_keyword_fallback_scheduling():
    assert _keyword_classify("Can we schedule a showing?") == "scheduling"


def test_keyword_fallback_listing_qa():
    assert _keyword_classify("What's the HOA?") == "listing_qa"


def test_keyword_fallback_escalation():
    assert _keyword_classify("I want to make an offer") == "escalation"


def test_keyword_fallback_transaction():
    assert _keyword_classify("When is the inspection?") == "transaction"


def test_keyword_fallback_personal():
    assert _keyword_classify("Thanks!") == "personal"


def test_keyword_fallback_lead():
    assert _keyword_classify("I'm looking to buy in Fishtown") == "lead_qualification"


@patch("app.pipeline.classifier.get_anthropic_client")
def test_classify_with_mock_llm(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "listing_qa",
        "confidence": 0.95,
        "needs_full_context": False,
    }

    event = make_event("What's the HOA on 123 Oak?")
    result = classify_intent(event, SARAH, AGENT)
    assert result.intent == "listing_qa"
    assert result.sender_type == "known_client"


@patch("app.pipeline.classifier.get_anthropic_client")
def test_classify_scheduling(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "scheduling",
        "confidence": 0.92,
        "needs_full_context": True,
    }

    event = make_event("Can we see some houses Saturday?")
    result = classify_intent(event, SARAH, AGENT)
    assert result.intent == "scheduling"
    assert result.needs_full_context is True


@patch("app.pipeline.classifier.get_anthropic_client")
def test_classify_unknown_sender_listing(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "listing_qa",
        "confidence": 0.9,
        "needs_full_context": False,
    }

    event = make_event("Is 123 Oak still available?", sender="+19999999999")
    result = classify_intent(event, None, AGENT)
    assert result.sender_type == "unknown_listing_inquiry"


@patch("app.pipeline.classifier.get_anthropic_client")
def test_classify_unknown_sender_general(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "lead_qualification",
        "confidence": 0.8,
        "needs_full_context": True,
    }

    event = make_event("I'm interested in buying", sender="+19999999999")
    result = classify_intent(event, None, AGENT)
    assert result.sender_type == "unknown_general"


@patch("app.pipeline.classifier.get_anthropic_client")
def test_classify_escalation(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "escalation",
        "confidence": 0.95,
        "needs_full_context": True,
    }

    event = make_event("Should I offer under asking?")
    result = classify_intent(event, SARAH, AGENT)
    assert result.intent == "escalation"


@patch("app.pipeline.classifier.get_anthropic_client")
def test_classify_llm_failure_uses_fallback(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.side_effect = Exception("API error")

    event = make_event("Can we schedule a showing?")
    result = classify_intent(event, SARAH, AGENT)
    assert result.intent == "scheduling"
    assert result.confidence < 0.5


@patch("app.pipeline.classifier.get_anthropic_client")
def test_classify_buyer_agent(mock_get_client):
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "intent": "listing_qa",
        "confidence": 0.9,
        "needs_full_context": False,
    }

    agent_contact = Contact(
        id=UUID("b5eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        agent_id=AGENT_ID, name="Tom Rivera", phone="+12675555678",
        role="buyer_agent", lifecycle_stage="other_agent",
    )
    event = make_event("My client is interested in 123 Oak", sender="+12675555678")
    result = classify_intent(event, agent_contact, AGENT)
    assert result.sender_type == "known_agent"
