"""Tests for WebSocket event publishing wired into the dispatcher."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import UUID, uuid4

import pytest

from app.models.schemas import NormalizedEvent, Contact, AgentConfig, AgentDecision


AGENT_ID = UUID("12345678-1234-1234-1234-123456789012")
CONTACT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _make_agent() -> AgentConfig:
    return AgentConfig(
        id=AGENT_ID,
        name="Jane Smith",
        email="jane@test.com",
        phone="+12155551000",
        twilio_number="+12155559999",
        style_profile={"tone": "casual"},
    )


def _make_contact() -> Contact:
    return Contact(
        id=CONTACT_ID,
        agent_id=AGENT_ID,
        name="John Buyer",
        phone="+12155552000",
        email="john@test.com",
        consent_status="granted",
    )


def _make_event(body: str = "Hello") -> NormalizedEvent:
    return NormalizedEvent(
        sender_phone="+12155552000",
        channel="sms",
        body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id="SM123",
        raw_payload={},
        agent_id=AGENT_ID,
    )


class TestDispatcherWSEvents:
    """Verify that dispatch() publishes WebSocket events at the correct points."""

    @patch("app.pipeline.dispatcher._background_summarize")
    @patch("app.pipeline.dispatcher._update_usage_metrics")
    @patch("app.pipeline.dispatcher._log_conversation")
    @patch("app.pipeline.dispatcher.send_client_message")
    @patch("app.pipeline.dispatcher._publish_ws_event")
    @patch("app.pipeline.consent.check_consent_before_send", return_value=True)
    def test_new_message_publishes_ws_event(
        self, mock_consent, mock_ws, mock_send, mock_log, mock_metrics, mock_summarize
    ):
        from app.pipeline.dispatcher import dispatch

        agent = _make_agent()
        contact = _make_contact()
        event = _make_event()
        decision = AgentDecision(
            response_text="Thanks for reaching out!",
            model_used="haiku",
            tokens_used=100,
        )

        dispatch(decision, event, contact, agent)

        # Should publish a new_message WS event
        mock_ws.assert_any_call(
            agent.id,
            "new_message",
            {
                "contact_id": str(contact.id),
                "contact_name": contact.name,
                "message_preview": "Thanks for reaching out!",
                "channel": "sms",
            },
        )

    @patch("app.pipeline.dispatcher._background_summarize")
    @patch("app.pipeline.dispatcher._update_usage_metrics")
    @patch("app.pipeline.dispatcher._log_conversation")
    @patch("app.pipeline.dispatcher.send_client_message")
    @patch("app.pipeline.dispatcher._publish_ws_event")
    @patch("app.pipeline.consent.check_consent_before_send", return_value=True)
    def test_no_ws_event_for_agent_commands(
        self, mock_consent, mock_ws, mock_send, mock_log, mock_metrics, mock_summarize
    ):
        from app.pipeline.dispatcher import dispatch

        agent = _make_agent()
        event = _make_event("!status")
        decision = AgentDecision(
            response_text="All systems operational",
            model_used="template",
            tokens_used=0,
        )

        dispatch(decision, event, None, agent, is_agent_command=True)

        # Should NOT publish new_message for agent commands
        for call in mock_ws.call_args_list:
            assert call[0][1] != "new_message"

    @patch("app.pipeline.dispatcher._background_summarize")
    @patch("app.pipeline.dispatcher._update_usage_metrics")
    @patch("app.pipeline.dispatcher._log_conversation")
    @patch("app.pipeline.dispatcher._publish_ws_event")
    @patch("app.services.firebase_service.send_push_notification")
    @patch("app.pipeline.consent.check_consent_before_send", return_value=True)
    def test_notification_publishes_ws_event(
        self, mock_consent, mock_push, mock_ws, mock_log, mock_metrics, mock_summarize
    ):
        from app.pipeline.dispatcher import dispatch

        agent = _make_agent()
        contact = _make_contact()
        event = _make_event()
        decision = AgentDecision(
            response_text=None,
            model_used="template",
            tokens_used=0,
            notifications=[{
                "tier": "urgent",
                "title": "Escalation: John",
                "body": "Client requested a callback",
            }],
        )

        dispatch(decision, event, contact, agent)

        mock_ws.assert_any_call(
            agent.id,
            "notification",
            {
                "tier": "urgent",
                "title": "Escalation: John",
                "body": "Client requested a callback",
                "contact_id": str(contact.id),
            },
        )

    @patch("app.pipeline.dispatcher._background_summarize")
    @patch("app.pipeline.dispatcher._update_usage_metrics")
    @patch("app.pipeline.dispatcher._log_conversation")
    @patch("app.pipeline.dispatcher._publish_ws_event")
    @patch("app.pipeline.dispatcher._create_trigger")
    @patch("app.pipeline.consent.check_consent_before_send", return_value=True)
    def test_ask_agent_trigger_publishes_pending_approval(
        self, mock_consent, mock_create, mock_ws, mock_log, mock_metrics, mock_summarize
    ):
        from app.pipeline.dispatcher import dispatch

        agent = _make_agent()
        contact = _make_contact()
        event = _make_event()
        decision = AgentDecision(
            response_text=None,
            model_used="template",
            tokens_used=0,
            triggers_to_create=[{
                "trigger_type": "follow_up",
                "entity_id": str(CONTACT_ID),
                "entity_type": "contact",
                "autonomy_level": "ask_agent",
                "message_template": "Just checking in — still interested?",
            }],
        )

        dispatch(decision, event, contact, agent)

        mock_ws.assert_any_call(
            agent.id,
            "pending_approval",
            {
                "trigger_type": "follow_up",
                "contact_id": str(CONTACT_ID),
                "message_preview": "Just checking in — still interested?",
            },
        )

    @patch("app.pipeline.dispatcher._background_summarize")
    @patch("app.pipeline.dispatcher._update_usage_metrics")
    @patch("app.pipeline.dispatcher._log_conversation")
    @patch("app.pipeline.dispatcher._publish_ws_event")
    @patch("app.pipeline.dispatcher._create_trigger")
    @patch("app.pipeline.consent.check_consent_before_send", return_value=True)
    def test_autonomous_trigger_no_pending_approval(
        self, mock_consent, mock_create, mock_ws, mock_log, mock_metrics, mock_summarize
    ):
        from app.pipeline.dispatcher import dispatch

        agent = _make_agent()
        contact = _make_contact()
        event = _make_event()
        decision = AgentDecision(
            response_text=None,
            model_used="template",
            tokens_used=0,
            triggers_to_create=[{
                "trigger_type": "follow_up",
                "entity_id": str(CONTACT_ID),
                "autonomy_level": "autonomous",
                "message_template": "Auto follow-up",
            }],
        )

        dispatch(decision, event, contact, agent)

        # Should NOT publish pending_approval for autonomous triggers
        for call in mock_ws.call_args_list:
            assert call[0][1] != "pending_approval"


class TestPublishWSEventHelper:
    """Test the _publish_ws_event helper handles edge cases."""

    @patch("app.api.mobile.ws.get_async_redis")
    def test_publish_ws_event_async_context(self, mock_redis):
        """publish_mobile_event works in an async context."""
        from app.api.mobile.ws import publish_mobile_event

        mock_async_redis = AsyncMock()
        mock_redis.return_value = mock_async_redis

        asyncio.run(publish_mobile_event(str(AGENT_ID), {"type": "test"}))

        mock_async_redis.publish.assert_called_once()
        channel = mock_async_redis.publish.call_args[0][0]
        assert str(AGENT_ID) in channel

    def test_publish_ws_event_swallows_errors(self):
        """_publish_ws_event never raises — it's best-effort."""
        from app.pipeline.dispatcher import _publish_ws_event

        with patch("app.api.mobile.ws.get_async_redis", side_effect=RuntimeError("Redis down")):
            # Should not raise
            _publish_ws_event(AGENT_ID, "test", {"data": "value"})
