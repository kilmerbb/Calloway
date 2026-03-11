"""Tests for BUILD SPECIFICATION ADDENDUM — Steps 2A, 5A, 5B, 6A, 10A, 13A, 23A, 44C."""
import pytest
from datetime import datetime, timezone, timedelta, date
from uuid import UUID, uuid4
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.models.schemas import (
    AgentConfig, Contact, NormalizedEvent, IntentClassification,
    AgentDecision, Listing,
)

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def _make_agent(**overrides):
    defaults = dict(
        id=AGENT_ID, name="Test Agent", email="agent@test.com",
        phone="+15551234567", twilio_number="+15559876543",
        style_profile={"tone": "professional"}, autonomy_rules={},
        scheduling_prefs={}, listing_rules={},
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _make_contact(**overrides):
    defaults = dict(
        id=uuid4(), agent_id=AGENT_ID, name="Sarah Test",
        phone="+18005551234", role="buyer", lifecycle_stage="active_buyer",
        consent_status="granted", language_detected="en", interaction_count=0,
    )
    defaults.update(overrides)
    return Contact(**defaults)


def _make_event(body="Hello", sender_phone="+18005551234", **overrides):
    defaults = dict(
        sender_phone=sender_phone, channel="sms", body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id="TEST123",
        raw_payload={"Body": body}, agent_id=AGENT_ID,
    )
    defaults.update(overrides)
    return NormalizedEvent(**defaults)


# ============================================================
# Step 2A: Consent Fields on Contact Model
# ============================================================

def test_contact_model_has_consent_fields():
    """Contact model includes TCPA consent tracking fields."""
    contact = _make_contact()
    assert hasattr(contact, "consent_status")
    assert hasattr(contact, "consent_granted_at")
    assert hasattr(contact, "consent_revoked_at")
    assert hasattr(contact, "consent_method")
    assert hasattr(contact, "consent_message")
    assert hasattr(contact, "consent_response")
    assert contact.consent_status == "granted"


def test_contact_model_has_language_field():
    """Contact model includes language_detected."""
    contact = _make_contact()
    assert contact.language_detected == "en"


def test_contact_model_has_interaction_count():
    """Contact model includes interaction_count."""
    contact = _make_contact(interaction_count=42)
    assert contact.interaction_count == 42


def test_contact_consent_status_values():
    """consent_status can be pending, granted, or revoked."""
    for status in ("pending", "granted", "revoked"):
        c = _make_contact(consent_status=status)
        assert c.consent_status == status


# ============================================================
# Step 5A: STOP/HELP/START Handler
# ============================================================

@patch("app.pipeline.consent.get_db_connection")
def test_stop_keyword_revokes_consent(mock_conn):
    from app.pipeline.consent import check_tcpa_keywords

    agent = _make_agent()
    contact = _make_contact()
    event = _make_event(body="STOP")

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = check_tcpa_keywords(event, contact, agent)
    assert result is not None
    assert result["action"] == "stop"
    assert "unsubscribed" in result["response_text"].lower()
    assert result["notify_agent"] is True


def test_help_keyword_returns_info():
    from app.pipeline.consent import check_tcpa_keywords

    agent = _make_agent()
    event = _make_event(body="help")

    result = check_tcpa_keywords(event, None, agent)
    assert result is not None
    assert result["action"] == "help"
    assert agent.name in result["response_text"]
    assert "STOP" in result["response_text"]


@patch("app.pipeline.consent.get_db_connection")
def test_start_keyword_reinitiates_consent(mock_conn):
    from app.pipeline.consent import check_tcpa_keywords

    agent = _make_agent()
    contact = _make_contact(consent_status="revoked")
    event = _make_event(body="start")

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = check_tcpa_keywords(event, contact, agent)
    assert result is not None
    assert result["action"] == "start"
    assert "YES" in result["response_text"]


@patch("app.pipeline.consent.get_db_connection")
def test_affirmative_grants_consent(mock_conn):
    from app.pipeline.consent import check_tcpa_keywords

    agent = _make_agent()
    contact = _make_contact(consent_status="pending")
    event = _make_event(body="yes")

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = check_tcpa_keywords(event, contact, agent)
    assert result is not None
    assert result["action"] == "consent_granted"
    assert "welcome" in result["response_text"].lower()


def test_normal_message_passes_through():
    from app.pipeline.consent import check_tcpa_keywords

    agent = _make_agent()
    contact = _make_contact()
    event = _make_event(body="Is 123 Oak still available?")

    result = check_tcpa_keywords(event, contact, agent)
    assert result is None


def test_stop_keywords_set():
    from app.pipeline.consent import STOP_KEYWORDS, HELP_KEYWORDS, START_KEYWORDS
    assert "stop" in STOP_KEYWORDS
    assert "unsubscribe" in STOP_KEYWORDS
    assert "help" in HELP_KEYWORDS
    assert "start" in START_KEYWORDS


# ============================================================
# Step 5B: Rate Limiting
# ============================================================

def test_rate_limiter_check_passes_without_redis():
    """Rate limiter fails open when Redis is unavailable."""
    from app.pipeline.rate_limiter import check_rate_limits

    agent = _make_agent()
    contact = _make_contact()
    event = _make_event()

    result = check_rate_limits(event, contact, agent)
    assert result is None  # Fails open


@patch("app.pipeline.rate_limiter.get_db_connection")
def test_cost_cap_under_limit(mock_conn):
    from app.pipeline.rate_limiter import check_cost_cap

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = {"cost": 100}
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    assert check_cost_cap(AGENT_ID) is False


@patch("app.pipeline.rate_limiter.get_db_connection")
def test_cost_cap_over_limit(mock_conn):
    from app.pipeline.rate_limiter import check_cost_cap

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = {"cost": 2000}
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    assert check_cost_cap(AGENT_ID) is True


def test_rate_limiter_thresholds():
    from app.pipeline.rate_limiter import (
        HOURLY_MESSAGE_LIMIT, DAILY_MESSAGE_LIMIT,
        DAILY_COST_CAP_CENTS, UNKNOWN_DAILY_LIMIT,
    )
    assert HOURLY_MESSAGE_LIMIT == 30
    assert DAILY_MESSAGE_LIMIT == 100
    assert DAILY_COST_CAP_CENTS == 1500
    assert UNKNOWN_DAILY_LIMIT == 10


def test_rate_limiter_unknown_passes_without_redis():
    """Unknown number rate limit fails open when Redis is unavailable."""
    from app.pipeline.rate_limiter import check_rate_limits

    agent = _make_agent()
    event = _make_event(sender_phone="+19999999999")

    result = check_rate_limits(event, None, agent)
    assert result is None


# ============================================================
# Step 6A: Language Detection
# ============================================================

def test_intent_classification_has_language_code():
    ic = IntentClassification(
        intent="listing_qa", sender_type="known_client",
        confidence=0.9, needs_full_context=False,
        language_code="es",
    )
    assert ic.language_code == "es"


def test_intent_classification_defaults_to_en():
    ic = IntentClassification(
        intent="personal", sender_type="unknown_general",
        confidence=0.8, needs_full_context=False,
    )
    assert ic.language_code == "en"


def test_classifier_feedback_detection():
    """Standalone '1' or '2' from known contact → feedback intent."""
    from app.pipeline.classifier import classify_intent

    agent = _make_agent()
    contact = _make_contact()

    event_1 = _make_event(body="1")
    result = classify_intent(event_1, contact, agent)
    assert result.intent == "feedback"
    assert result.confidence == 1.0

    event_2 = _make_event(body="2")
    result2 = classify_intent(event_2, contact, agent)
    assert result2.intent == "feedback"


def test_classifier_feedback_requires_contact():
    """Standalone '1' without a contact should NOT be classified as feedback."""
    from app.pipeline.classifier import classify_intent

    agent = _make_agent()
    # Without contact, '1' falls through to keyword/LLM classification
    event = _make_event(body="1")
    # This will try LLM and fail, falling back to keyword
    result = classify_intent(event, None, agent)
    assert result.intent != "feedback"


def test_classify_prompt_includes_language():
    from app.pipeline.classifier import CLASSIFY_PROMPT
    assert "language_code" in CLASSIFY_PROMPT
    assert "ISO 639-1" in CLASSIFY_PROMPT


def test_valid_intents_include_feedback():
    """Feedback is in the valid intents set."""
    from app.pipeline.classifier import CLASSIFY_PROMPT
    assert "feedback" in CLASSIFY_PROMPT


# ============================================================
# Step 10A: Handoff Return Commands
# ============================================================

@patch("app.pipeline.commands.status.lookup_contact")
@patch("app.pipeline.commands.status.update_contact")
def test_handoff_return_reactivates_contact(mock_update, mock_lookup):
    from app.pipeline.commands.status import handle_handoff_return

    agent = _make_agent()
    contact = _make_contact(silent_mode=True)
    mock_lookup.return_value = contact

    result = handle_handoff_return(
        agent, "Sarah Test", "She's pre-approved up to 500K",
        None, None, "Back from Sarah. She's pre-approved up to 500K."
    )

    assert result.response_text is not None
    assert "Sarah Test" in result.response_text
    assert "Reactivated" in result.response_text
    mock_update.assert_any_call(contact.id, silent_mode=False)


@patch("app.pipeline.commands.status.lookup_contact")
def test_handoff_return_no_contact(mock_lookup):
    from app.pipeline.commands.status import handle_handoff_return

    agent = _make_agent()
    mock_lookup.return_value = None

    result = handle_handoff_return(agent, "Nobody", "", None, None, "Back from Nobody")
    assert "don't have" in result.response_text


@patch("app.pipeline.commands.contact.lookup_contact")
@patch("app.pipeline.commands.contact.update_contact")
def test_note_command(mock_update, mock_lookup):
    from app.pipeline.commands.contact import handle_note_command

    agent = _make_agent()
    contact = _make_contact(notes="existing notes")
    mock_lookup.return_value = contact

    result = handle_note_command(agent, "Sarah Test", "lease ends June 30")
    assert "Noted" in result.response_text
    assert "Sarah Test" in result.response_text
    mock_update.assert_called_once()


@patch("app.pipeline.commands.contact.lookup_contact")
@patch("app.pipeline.commands.contact.create_contact")
@patch("app.pipeline.consent.get_db_connection")
def test_connect_command(mock_conn, mock_create, mock_lookup):
    from app.pipeline.commands.contact import handle_connect_command

    agent = _make_agent()
    new_contact = _make_contact(name="John Doe", phone="+15551234567")
    mock_lookup.return_value = None
    mock_create.return_value = new_contact

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    event = _make_event(body="Connect John Doe +15551234567 buyer")
    result = handle_connect_command(event, agent, "John Doe", "buyer", event.body)

    assert "Created" in result.response_text
    assert "opt-in" in result.response_text.lower()
    mock_create.assert_called_once()


def test_command_classify_prompt_has_new_types():
    from app.pipeline.handlers import COMMAND_CLASSIFY_PROMPT
    assert "handoff_return" in COMMAND_CLASSIFY_PROMPT
    assert "note" in COMMAND_CLASSIFY_PROMPT
    assert "connect" in COMMAND_CLASSIFY_PROMPT


# ============================================================
# Step 13A: Consent-Gated Introduction
# ============================================================

def test_consent_check_blocks_revoked():
    from app.pipeline.consent import check_consent_before_send

    contact = _make_contact(consent_status="revoked")
    assert check_consent_before_send(contact) is False


def test_consent_check_allows_granted():
    from app.pipeline.consent import check_consent_before_send

    contact = _make_contact(consent_status="granted")
    assert check_consent_before_send(contact) is True


def test_consent_check_blocks_pending():
    from app.pipeline.consent import check_consent_before_send

    contact = _make_contact(consent_status="pending")
    assert check_consent_before_send(contact) is False


def test_consent_check_allows_unknown():
    """Unknown contacts (None) should be allowed one-off responses."""
    from app.pipeline.consent import check_consent_before_send
    assert check_consent_before_send(None) is True


@patch("app.pipeline.consent.get_db_connection")
def test_send_consent_request(mock_conn):
    from app.pipeline.consent import send_consent_request

    agent = _make_agent()
    contact = _make_contact(consent_status="pending")

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    msg = send_consent_request(agent, contact)
    assert agent.name in msg
    assert "STOP" in msg
    assert "YES" in msg


@patch("app.pipeline.consent.get_db_connection")
def test_consent_expiry_check(mock_conn):
    from app.pipeline.consent import check_consent_expiry

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = [
        {"id": str(uuid4()), "name": "Stale Lead", "phone": "+18005559999",
         "created_at": datetime.now(timezone.utc) - timedelta(hours=72)},
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    expired = check_consent_expiry(AGENT_ID)
    assert len(expired) == 1
    assert expired[0]["name"] == "Stale Lead"


# ============================================================
# Step 23A: Client Feedback Pulse
# ============================================================

def test_feedback_interval_constant():
    from app.pipeline.dispatcher import FEEDBACK_INTERVAL
    assert FEEDBACK_INTERVAL == 10


@patch("app.pipeline.dispatcher.get_db_connection")
def test_feedback_pulse_appended_on_interval(mock_conn):
    from app.pipeline.dispatcher import _maybe_append_feedback_prompt

    agent = _make_agent()
    contact = _make_contact(interaction_count=9)

    ctx = MagicMock()
    # After increment, count = 10 (hits interval)
    ctx.execute.return_value.fetchone.return_value = {"interaction_count": 10}
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = _maybe_append_feedback_prompt("Here's the listing info.", contact, agent)
    assert "Was this helpful?" in result
    assert "Tap 1" in result


@patch("app.pipeline.dispatcher.get_db_connection")
def test_feedback_pulse_not_appended_off_interval(mock_conn):
    from app.pipeline.dispatcher import _maybe_append_feedback_prompt

    agent = _make_agent()
    contact = _make_contact(interaction_count=6)

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = {"interaction_count": 7}
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = _maybe_append_feedback_prompt("Here's the listing info.", contact, agent)
    assert "Was this helpful?" not in result


def test_message_model_has_feedback_score():
    from app.models.schemas import Message
    m = Message(
        agent_id=AGENT_ID, conversation_id=uuid4(),
        sender_type="ai", body="test", feedback_score=1,
    )
    assert m.feedback_score == 1


# ============================================================
# Step 44C: Monthly Value Report
# ============================================================

@patch("app.services.token_monitor.get_db_connection")
def test_generate_monthly_value_report(mock_conn):
    from app.services.token_monitor import generate_monthly_value_report

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.side_effect = [
        # monthly aggregates
        {"msgs_sent": 200, "msgs_received": 300, "llm_calls": 150,
         "tokens": 500000, "cost": 2500, "voice_mins": Decimal("30"),
         "showings": 12, "triggers": 45, "active_days": 28},
        # contacts added
        {"cnt": 15},
        # conversations
        {"cnt": 50},
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    report = generate_monthly_value_report(AGENT_ID)
    assert report["messages_handled"] == 500
    assert report["messages_sent"] == 200
    assert report["showings_booked"] == 12
    assert report["new_contacts"] == 15
    assert report["conversations"] == 50
    assert report["llm_cost_dollars"] == 25.0
    assert report["estimated_hours_saved"] > 0
    assert report["active_days"] == 28


def test_format_monthly_value_report():
    from app.services.token_monitor import format_monthly_value_report

    report = {
        "messages_handled": 500, "messages_sent": 200,
        "messages_received": 300, "conversations": 50,
        "showings_booked": 12, "new_contacts": 15,
        "triggers_fired": 45, "llm_cost_dollars": 25.0,
        "voice_minutes": 30.0, "active_days": 28,
        "estimated_hours_saved": 6.7,
    }

    text = format_monthly_value_report(report)
    assert "Monthly Performance Report" in text
    assert "500" in text  # messages handled
    assert "12" in text  # showings
    assert "$25.0" in text  # cost
    assert "6.7" in text  # hours saved


@patch("app.services.token_monitor.get_db_connection")
@patch("app.services.firebase_service.send_push_notification")
def test_send_monthly_value_report(mock_push, mock_conn):
    from app.services.token_monitor import send_monthly_value_report

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.side_effect = [
        {"msgs_sent": 100, "msgs_received": 150, "llm_calls": 80,
         "tokens": 200000, "cost": 1000, "voice_mins": Decimal("10"),
         "showings": 5, "triggers": 20, "active_days": 25},
        {"cnt": 8},
        {"cnt": 30},
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    send_monthly_value_report(AGENT_ID)
    mock_push.assert_called_once()
