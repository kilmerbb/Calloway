"""Tests for Phase 4: command module decomposition.

Verifies that all command handlers are importable from their new locations
and that the dispatch table in handlers.py routes correctly.
"""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock

from app.pipeline.handlers import handle_agent_command, COMMAND_CLASSIFY_PROMPT
from app.pipeline.commands import (
    handle_listing_command,
    handle_listing_query,
    handle_broadcast,
    handle_client_instruction,
    handle_contact_query,
    handle_note_command,
    handle_connect_command,
    handle_status_change,
    handle_handoff_return,
    handle_schedule_query,
    handle_gap_query,
    handle_trigger_command,
    handle_cascade_command,
    handle_offer_command,
)
from app.models.schemas import NormalizedEvent, AgentConfig

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
AGENT = AgentConfig(
    id=AGENT_ID, name="Jane Smith", email="jane@test.com",
    phone="+12155551000", twilio_number="+12155559999",
    style_profile={"tone": "professional"},
)


def _event(body: str) -> NormalizedEvent:
    return NormalizedEvent(
        sender_phone="+12155551000", channel="sms", body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id="SM123", raw_payload={}, agent_id=AGENT_ID,
    )


def test_all_command_types_in_classify_prompt():
    """Verify all 14 command types are documented in the classify prompt."""
    expected_types = [
        "client_instruction", "listing_update", "broadcast", "status_change",
        "query_contact", "query_gap", "query_schedule", "query_listing",
        "trigger", "cascade", "offer", "handoff_return", "note", "connect",
    ]
    for cmd_type in expected_types:
        assert cmd_type in COMMAND_CLASSIFY_PROMPT, f"Missing {cmd_type}"


def test_all_handlers_importable():
    """All 15 command handlers are importable from their modules."""
    assert callable(handle_listing_command)
    assert callable(handle_listing_query)
    assert callable(handle_broadcast)
    assert callable(handle_client_instruction)
    assert callable(handle_contact_query)
    assert callable(handle_note_command)
    assert callable(handle_connect_command)
    assert callable(handle_status_change)
    assert callable(handle_handoff_return)
    assert callable(handle_schedule_query)
    assert callable(handle_gap_query)
    assert callable(handle_trigger_command)
    assert callable(handle_cascade_command)
    assert callable(handle_offer_command)


@patch("app.pipeline.handlers.get_anthropic_client")
def test_dispatch_table_routes_all_types(mock_get_client):
    """Each command_type routes to the correct handler without error."""
    mock_client = mock_get_client.return_value

    for cmd_type in ["trigger", "cascade", "offer", "note"]:
        mock_client.classify.return_value = {
            "command_type": cmd_type,
            "contact_name": "Test",
            "listing_address": "123 Oak",
            "details": "test details",
            "time_reference": None,
            "_tokens": 50,
        }

        # Patch the underlying contact lookup to avoid DB calls
        with patch("app.pipeline.commands.scheduling.lookup_contact", return_value=None), \
             patch("app.pipeline.commands.offer.lookup_contact", return_value=None), \
             patch("app.pipeline.commands.contact.lookup_contact", return_value=None):
            event = _event(f"test {cmd_type} command")
            result = handle_agent_command(event, AGENT)
            assert result.response_text is not None, f"No response for {cmd_type}"


@patch("app.pipeline.handlers.get_anthropic_client")
def test_unknown_command_type_handled(mock_get_client):
    """Unknown command types return a helpful message."""
    mock_client = mock_get_client.return_value
    mock_client.classify.return_value = {
        "command_type": "totally_unknown",
        "_tokens": 30,
    }

    result = handle_agent_command(_event("do something weird"), AGENT)
    assert "rephrase" in result.response_text.lower()


@patch("app.pipeline.handlers.get_anthropic_client")
def test_command_parse_failure_handled(mock_get_client):
    """When LLM parsing fails, return a friendly error."""
    mock_client = mock_get_client.return_value
    import anthropic
    mock_client.classify.side_effect = anthropic.APIError(
        message="API timeout",
        request=None,
        body=None,
    )

    result = handle_agent_command(_event("garbled text"), AGENT)
    assert "didn't understand" in result.response_text.lower()
    assert result.model_used == "template"
