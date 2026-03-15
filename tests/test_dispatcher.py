"""Unit tests for the response dispatcher (app/pipeline/dispatcher.py).

Tests the dispatch() function and its helpers: channel routing, consent gating,
notification delivery, trigger creation, conversation logging, and usage metrics.
"""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock, call

from app.models.schemas import (
    NormalizedEvent, Contact, AgentConfig, AgentDecision,
)
from app.pipeline.dispatcher import (
    dispatch,
    MODEL_COST_MAP,
    FEEDBACK_INTERVAL,
    _maybe_append_feedback_prompt,
)

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONTACT_ID = UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONV_ID = UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def _agent() -> AgentConfig:
    return AgentConfig(
        id=AGENT_ID, name="Jane Smith", email="jane@calloway.ai",
        phone="+12155551000", twilio_number="+12155559999",
    )


def _contact(**overrides) -> Contact:
    defaults = dict(
        id=CONTACT_ID, agent_id=AGENT_ID, name="Sarah Chen",
        phone="+12675551234", consent_status="granted",
    )
    defaults.update(overrides)
    return Contact(**defaults)


def _event(body: str = "Hello", channel: str = "sms") -> NormalizedEvent:
    return NormalizedEvent(
        sender_phone="+12675551234", channel=channel, body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id="SM123", raw_payload={}, agent_id=AGENT_ID,
    )


def _decision(**overrides) -> AgentDecision:
    defaults = dict(response_text="Hello there!", model_used="haiku", tokens_used=100)
    defaults.update(overrides)
    return AgentDecision(**defaults)


# ── Consent gate ─────────────────────────────────────────────


@patch("app.pipeline.dispatcher._update_usage_metrics")
@patch("app.pipeline.dispatcher._log_conversation")
@patch("app.pipeline.dispatcher.send_client_message")
@patch("app.services.cache.cache_invalidate")
@patch("app.pipeline.consent.check_consent_before_send", return_value=False)
def test_dispatch_blocks_revoked_consent(
    mock_consent, mock_cache, mock_send, mock_log, mock_metrics,
):
    """Dispatch blocks outbound messages when consent is revoked."""
    agent = _agent()
    contact = _contact(consent_status="revoked")
    event = _event()
    decision = _decision()

    dispatch(decision, event, contact, agent)

    mock_consent.assert_called_once_with(contact)
    mock_send.assert_not_called()
    # Still logs conversation for audit trail
    mock_log.assert_called_once()
    mock_metrics.assert_called_once()


# ── Channel routing ──────────────────────────────────────────


@patch("app.pipeline.dispatcher._background_summarize")
@patch("app.pipeline.dispatcher._update_usage_metrics")
@patch("app.pipeline.dispatcher._log_conversation")
@patch("app.pipeline.dispatcher._publish_ws_event")
@patch("app.pipeline.dispatcher._maybe_append_feedback_prompt", side_effect=lambda t, c, a: t)
@patch("app.pipeline.consent.check_consent_before_send", return_value=True)
@patch("app.pipeline.dispatcher.send_client_message")
def test_dispatch_sms_to_contact(
    mock_send, mock_consent, mock_feedback, mock_ws, mock_log, mock_metrics, mock_summarize,
):
    """SMS response is sent to contact via send_client_message."""
    agent = _agent()
    contact = _contact()
    event = _event(channel="sms")
    decision = _decision(response_text="Hi!")

    dispatch(decision, event, contact, agent)

    mock_send.assert_called_once_with(
        agent_id=agent.id, contact_id=contact.id,
        message="Hi!", from_number=agent.twilio_number,
        to_number=contact.phone,
    )


@patch("app.pipeline.dispatcher._background_summarize")
@patch("app.pipeline.dispatcher._update_usage_metrics")
@patch("app.pipeline.dispatcher._log_conversation")
@patch("app.pipeline.dispatcher._publish_ws_event")
@patch("app.pipeline.dispatcher.send_sms")
def test_dispatch_agent_command_replies_to_agent(
    mock_send_sms, mock_ws, mock_log, mock_metrics, mock_summarize,
):
    """Agent commands are replied via send_sms to agent's phone."""
    agent = _agent()
    event = _event(channel="sms_command")
    decision = _decision(response_text="Done!")

    dispatch(decision, event, None, agent, is_agent_command=True)

    mock_send_sms.assert_called_once_with(
        to=agent.phone, from_=agent.twilio_number,
        body="Done!", agent_id=agent.id,
    )


@patch("app.pipeline.dispatcher._background_summarize")
@patch("app.pipeline.dispatcher._update_usage_metrics")
@patch("app.pipeline.dispatcher._log_conversation")
@patch("app.pipeline.dispatcher._publish_ws_event")
@patch("app.pipeline.dispatcher._maybe_append_feedback_prompt", side_effect=lambda t, c, a: t)
@patch("app.pipeline.consent.check_consent_before_send", return_value=True)
@patch("app.services.email_service.send_client_email")
def test_dispatch_email_to_contact(
    mock_email, mock_consent, mock_feedback, mock_ws, mock_log, mock_metrics, mock_summarize,
):
    """Email channel responses are sent via send_client_email."""
    agent = _agent()
    contact = _contact(email="sarah@example.com")
    event = _event(channel="email")
    decision = _decision(response_text="Email reply")

    dispatch(decision, event, contact, agent)

    mock_email.assert_called_once_with(
        agent_id=agent.id, contact_id=contact.id,
        message="Email reply", from_email=agent.email,
        to_email="sarah@example.com",
    )


# ── No response text ─────────────────────────────────────────


@patch("app.pipeline.dispatcher._background_summarize")
@patch("app.pipeline.dispatcher._update_usage_metrics")
@patch("app.pipeline.dispatcher._log_conversation")
@patch("app.pipeline.dispatcher.send_client_message")
@patch("app.pipeline.dispatcher.send_sms")
@patch("app.pipeline.consent.check_consent_before_send", return_value=True)
def test_dispatch_no_response_text_sends_nothing(
    mock_consent, mock_sms, mock_send, mock_log, mock_metrics, mock_summarize,
):
    """When decision has empty response_text, no message is sent."""
    agent = _agent()
    contact = _contact()
    event = _event()
    decision = _decision(response_text="")

    dispatch(decision, event, contact, agent)

    mock_sms.assert_not_called()
    mock_send.assert_not_called()


# ── Notifications ────────────────────────────────────────────


@patch("app.pipeline.dispatcher._background_summarize")
@patch("app.pipeline.dispatcher._update_usage_metrics")
@patch("app.pipeline.dispatcher._log_conversation")
@patch("app.pipeline.dispatcher._publish_ws_event")
@patch("app.pipeline.dispatcher._maybe_append_feedback_prompt", side_effect=lambda t, c, a: t)
@patch("app.pipeline.consent.check_consent_before_send", return_value=True)
@patch("app.pipeline.dispatcher.send_client_message")
@patch("app.services.firebase_service.send_push_notification")
def test_dispatch_sends_notifications(
    mock_push, mock_send, mock_consent, mock_feedback, mock_ws,
    mock_log, mock_metrics, mock_summarize,
):
    """Notifications in the decision are sent via Firebase."""
    agent = _agent()
    contact = _contact()
    event = _event()
    decision = _decision(notifications=[
        {"tier": "urgent", "title": "Alert", "body": "Showing conflict"},
    ])

    dispatch(decision, event, contact, agent)

    mock_push.assert_called_once_with(
        agent_id=agent.id, tier="urgent",
        title="Alert", body="Showing conflict",
        contact_id=contact.id,
    )


# ── Triggers ─────────────────────────────────────────────────


@patch("app.pipeline.dispatcher._background_summarize")
@patch("app.pipeline.dispatcher._update_usage_metrics")
@patch("app.pipeline.dispatcher._log_conversation")
@patch("app.pipeline.dispatcher._publish_ws_event")
@patch("app.pipeline.dispatcher._maybe_append_feedback_prompt", side_effect=lambda t, c, a: t)
@patch("app.pipeline.consent.check_consent_before_send", return_value=True)
@patch("app.pipeline.dispatcher.send_client_message")
@patch("app.pipeline.dispatcher.get_db_connection")
def test_dispatch_creates_triggers(
    mock_db, mock_send, mock_consent, mock_feedback, mock_ws,
    mock_log, mock_metrics, mock_summarize,
):
    """Triggers in the decision are created in the database."""
    mock_conn = MagicMock()
    mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_db.return_value.__exit__ = MagicMock(return_value=False)

    agent = _agent()
    contact = _contact()
    event = _event()
    decision = _decision(triggers_to_create=[
        {"trigger_type": "follow_up", "entity_id": str(CONTACT_ID),
         "scheduled_at": "2026-03-16T10:00:00Z", "action_type": "send_message",
         "message_template": "Following up", "autonomy_level": "ask_agent"},
    ])

    dispatch(decision, event, contact, agent)

    # Verify INSERT INTO triggers was called
    insert_call = mock_conn.execute.call_args
    assert "INSERT INTO triggers" in insert_call[0][0]


# ── Usage metrics ────────────────────────────────────────────


@patch("app.pipeline.dispatcher._background_summarize")
@patch("app.pipeline.dispatcher._log_conversation")
@patch("app.pipeline.dispatcher._publish_ws_event")
@patch("app.pipeline.dispatcher._maybe_append_feedback_prompt", side_effect=lambda t, c, a: t)
@patch("app.pipeline.consent.check_consent_before_send", return_value=True)
@patch("app.pipeline.dispatcher.send_client_message")
@patch("app.pipeline.dispatcher.get_db_connection")
def test_dispatch_tracks_usage_metrics(
    mock_db, mock_send, mock_consent, mock_feedback, mock_ws,
    mock_log, mock_summarize,
):
    """Usage metrics are updated with token counts and costs."""
    mock_conn = MagicMock()
    mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_db.return_value.__exit__ = MagicMock(return_value=False)

    agent = _agent()
    contact = _contact()
    event = _event()
    decision = _decision(model_used="sonnet", tokens_used=500)

    dispatch(decision, event, contact, agent)

    # Verify usage_metrics INSERT was called
    calls = mock_conn.execute.call_args_list
    usage_call = [c for c in calls if "usage_metrics" in str(c)]
    assert len(usage_call) > 0


# ── Conversation logging ─────────────────────────────────────


@patch("app.pipeline.dispatcher._background_summarize")
@patch("app.pipeline.dispatcher._update_usage_metrics")
@patch("app.pipeline.dispatcher._publish_ws_event")
@patch("app.pipeline.dispatcher._maybe_append_feedback_prompt", side_effect=lambda t, c, a: t)
@patch("app.pipeline.consent.check_consent_before_send", return_value=True)
@patch("app.pipeline.dispatcher.send_client_message")
@patch("app.pipeline.dispatcher.get_db_connection")
def test_dispatch_logs_conversation(
    mock_db, mock_send, mock_consent, mock_feedback, mock_ws,
    mock_metrics, mock_summarize,
):
    """Dispatch logs both inbound and outbound messages."""
    mock_conn = MagicMock()
    mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_db.return_value.__exit__ = MagicMock(return_value=False)
    # Simulate existing conversation
    mock_conn.execute.return_value.fetchone.return_value = {"id": str(CONV_ID)}

    agent = _agent()
    contact = _contact()
    event = _event(body="What time is the showing?")
    decision = _decision(response_text="The showing is at 2pm.")

    dispatch(decision, event, contact, agent)

    # Should have conversation lookup + 2 message inserts + contact update + commit
    assert mock_conn.execute.call_count >= 3


# ── Feedback pulse ───────────────────────────────────────────


@patch("app.pipeline.dispatcher.get_db_connection")
def test_feedback_prompt_appended_at_interval(mock_db):
    """Feedback prompt is appended every FEEDBACK_INTERVAL responses."""
    mock_conn = MagicMock()
    mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_db.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchone.return_value = {
        "interaction_count": FEEDBACK_INTERVAL,
    }

    contact = _contact()
    agent = _agent()
    result = _maybe_append_feedback_prompt("Great!", contact, agent)

    assert "helpful" in result.lower()
    assert "1" in result and "2" in result


@patch("app.pipeline.dispatcher.get_db_connection")
def test_feedback_prompt_not_appended_off_interval(mock_db):
    """Feedback prompt is NOT appended when not at interval."""
    mock_conn = MagicMock()
    mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_db.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchone.return_value = {
        "interaction_count": FEEDBACK_INTERVAL + 3,
    }

    contact = _contact()
    agent = _agent()
    result = _maybe_append_feedback_prompt("Great!", contact, agent)

    assert result == "Great!"


# ── Model cost map ───────────────────────────────────────────


def test_model_cost_map_has_required_models():
    """MODEL_COST_MAP contains haiku, sonnet, and template."""
    assert "haiku" in MODEL_COST_MAP
    assert "sonnet" in MODEL_COST_MAP
    assert "template" in MODEL_COST_MAP
    assert MODEL_COST_MAP["template"]["input"] == 0
    assert MODEL_COST_MAP["template"]["output"] == 0


def test_model_cost_map_sonnet_more_expensive_than_haiku():
    """Sonnet costs more than Haiku."""
    haiku_cost = MODEL_COST_MAP["haiku"]["input"] + MODEL_COST_MAP["haiku"]["output"]
    sonnet_cost = MODEL_COST_MAP["sonnet"]["input"] + MODEL_COST_MAP["sonnet"]["output"]
    assert sonnet_cost > haiku_cost
