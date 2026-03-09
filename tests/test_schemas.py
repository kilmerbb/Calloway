"""Tests for Pydantic models."""
import json
from datetime import datetime, date, time
from decimal import Decimal
from uuid import uuid4, UUID

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    AgentConfig, Contact, LeadPreferences, Listing, Conversation,
    Message, Showing, Trigger, Email, ToolExecution, UsageMetrics,
    NormalizedEvent, IntentClassification, AssembledContext, AgentDecision,
)

AGENT_ID = uuid4()
CONTACT_ID = uuid4()
LISTING_ID = uuid4()
CONV_ID = uuid4()


def test_agent_config_valid():
    agent = AgentConfig(
        id=AGENT_ID, name="Jane Smith", email="jane@test.com",
        phone="+12155551000", twilio_number="+12155559999",
    )
    assert agent.name == "Jane Smith"
    assert agent.timezone == "America/New_York"
    assert agent.current_status == "available"


def test_agent_config_missing_required():
    with pytest.raises(ValidationError):
        AgentConfig(id=AGENT_ID, name="Jane")  # missing email, phone, twilio_number


def test_contact_valid():
    contact = Contact(
        id=CONTACT_ID, agent_id=AGENT_ID, name="Sarah Chen", phone="+12675551234",
    )
    assert contact.role == "lead"
    assert contact.lifecycle_stage == "new_lead"
    assert contact.silent_mode is False


def test_contact_missing_required():
    with pytest.raises(ValidationError):
        Contact(id=CONTACT_ID, agent_id=AGENT_ID)  # missing name, phone


def test_lead_preferences_valid():
    prefs = LeadPreferences(
        contact_id=CONTACT_ID, areas=["Fishtown", "Northern Liberties"],
        timeline="1-3 months", preapproved=True, price_min=400000, price_max=500000,
    )
    assert prefs.areas == ["Fishtown", "Northern Liberties"]


def test_listing_valid():
    listing = Listing(
        id=LISTING_ID, agent_id=AGENT_ID, address="123 Oak St", price=475000,
        beds=3, baths=Decimal("2.0"), features=["renovated kitchen"],
    )
    assert listing.status == "active"
    assert listing.features == ["renovated kitchen"]


def test_listing_missing_price():
    with pytest.raises(ValidationError):
        Listing(id=LISTING_ID, agent_id=AGENT_ID, address="123 Oak St")


def test_conversation_valid():
    conv = Conversation(
        id=CONV_ID, agent_id=AGENT_ID, contact_id=CONTACT_ID, channel="rcs",
    )
    assert conv.stage == "open"


def test_message_valid():
    msg = Message(
        agent_id=AGENT_ID, conversation_id=CONV_ID,
        sender_type="client", body="Can we see houses Saturday?",
    )
    assert msg.ai_generated is False


def test_showing_valid():
    showing = Showing(
        agent_id=AGENT_ID, contact_id=CONTACT_ID, listing_id=LISTING_ID,
        start_time=datetime(2026, 3, 15, 10, 0),
        end_time=datetime(2026, 3, 15, 11, 0),
    )
    assert showing.status == "hold"


def test_trigger_valid():
    trigger = Trigger(
        agent_id=AGENT_ID, entity_type="contact", entity_id=CONTACT_ID,
        trigger_type="follow_up", scheduled_at=datetime(2026, 3, 15, 10, 0),
        action_type="send_message",
    )
    assert trigger.autonomy_level == "ask_agent"
    assert trigger.status == "pending"


def test_tool_execution_valid():
    te = ToolExecution(
        agent_id=AGENT_ID, tool_name="lookup_contact",
        input_json={"phone": "+12675551234"}, status="success",
    )
    assert te.status == "success"


def test_usage_metrics_valid():
    um = UsageMetrics(agent_id=AGENT_ID, date=date(2026, 3, 9))
    assert um.messages_sent == 0
    assert um.llm_cost_cents == 0


def test_normalized_event_valid():
    event = NormalizedEvent(
        sender_phone="+12675551234", channel="rcs",
        body="What's the HOA on 123 Oak?",
        timestamp=datetime.now(), provider_message_id="SM123",
        raw_payload={"Body": "What's the HOA on 123 Oak?"},
        agent_id=AGENT_ID,
    )
    assert event.channel == "rcs"


def test_normalized_event_invalid_channel():
    with pytest.raises(ValidationError):
        NormalizedEvent(
            sender_phone="+12675551234", channel="whatsapp",
            body="Hi", timestamp=datetime.now(),
            provider_message_id="SM123", raw_payload={}, agent_id=AGENT_ID,
        )


def test_intent_classification_valid():
    ic = IntentClassification(
        intent="scheduling", sender_type="known_client",
        confidence=0.95, needs_full_context=True,
    )
    assert ic.intent == "scheduling"


def test_intent_classification_invalid_intent():
    with pytest.raises(ValidationError):
        IntentClassification(
            intent="unknown_type", sender_type="known_client",
            confidence=0.9, needs_full_context=False,
        )


def test_assembled_context_valid():
    agent = AgentConfig(
        id=AGENT_ID, name="Jane", email="j@t.com",
        phone="+1", twilio_number="+2",
    )
    intent = IntentClassification(
        intent="listing_qa", sender_type="known_client",
        confidence=0.9, needs_full_context=False,
    )
    ctx = AssembledContext(agent=agent, intent=intent)
    assert ctx.contact is None
    assert ctx.listings == []


def test_agent_decision_valid():
    decision = AgentDecision(
        response_text="The HOA is $250/month.",
        model_used="haiku", tokens_used=150,
    )
    assert decision.model_used == "haiku"
    assert decision.tool_calls == []


def test_agent_decision_defaults():
    decision = AgentDecision()
    assert decision.response_text is None
    assert decision.model_used == "template"
    assert decision.tokens_used == 0


def test_models_serialize_to_json():
    """All models should serialize to and from JSON."""
    agent = AgentConfig(
        id=AGENT_ID, name="Jane", email="j@t.com",
        phone="+1", twilio_number="+2",
    )
    json_str = agent.model_dump_json()
    restored = AgentConfig.model_validate_json(json_str)
    assert restored.name == agent.name

    listing = Listing(
        id=LISTING_ID, agent_id=AGENT_ID,
        address="123 Oak", price=475000,
        baths=Decimal("2.0"),
    )
    json_str = listing.model_dump_json()
    restored = Listing.model_validate_json(json_str)
    assert restored.price == 475000
