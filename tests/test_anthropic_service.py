"""Tests for Anthropic API client wrapper."""
import json
import pytest
from unittest.mock import MagicMock, patch
from uuid import UUID

from app.services.anthropic_service import AnthropicClient, HAIKU_MODEL, SONNET_MODEL

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def make_mock_response(text="test response", input_tokens=100, output_tokens=50):
    response = MagicMock()
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text
    response.content = [content_block]
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def make_tool_use_response(tool_name="lookup_contact", tool_input=None, tool_id="tool_1"):
    response = MagicMock()
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input or {"phone": "+12675551234"}
    tool_block.id = tool_id
    response.content = [tool_block]
    response.usage = MagicMock()
    response.usage.input_tokens = 200
    response.usage.output_tokens = 100
    return response


@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_classify_returns_parsed_json(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(
        text='{"intent": "scheduling", "confidence": 0.95}'
    )

    client = AnthropicClient(api_key="test-key")
    result = client.classify("system prompt", "Can we see houses?", AGENT_ID)

    assert result["intent"] == "scheduling"
    assert result["confidence"] == 0.95
    assert "_tokens" in result


@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_classify_handles_markdown_json(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(
        text='```json\n{"intent": "listing_qa"}\n```'
    )

    client = AnthropicClient(api_key="test-key")
    result = client.classify("system prompt", "What's the HOA?", AGENT_ID)
    assert result["intent"] == "listing_qa"


@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_reason_returns_text_response(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(
        text="Saturday looks great! How about 11am?"
    )

    client = AnthropicClient(api_key="test-key")
    decision = client.reason(
        "system prompt",
        [{"role": "user", "content": "Can we see houses Saturday?"}],
        tools=[],
        agent_id=AGENT_ID,
    )

    assert decision.response_text == "Saturday looks great! How about 11am?"
    assert decision.model_used == "sonnet"
    assert decision.tokens_used > 0


@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_reason_handles_tool_use(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    # First call returns tool use, second returns text
    mock_client.messages.create.side_effect = [
        make_tool_use_response(),
        make_mock_response("Found Sarah Chen"),
    ]

    def mock_executor(tool_name, tool_input):
        return {"name": "Sarah Chen", "phone": "+12675551234"}

    client = AnthropicClient(api_key="test-key")
    decision = client.reason(
        "system prompt",
        [{"role": "user", "content": "Look up Sarah"}],
        tools=[{"name": "lookup_contact", "description": "Look up a contact"}],
        agent_id=AGENT_ID,
        tool_executor=mock_executor,
    )

    assert decision.response_text == "Found Sarah Chen"
    assert len(decision.tool_calls) == 1
    assert decision.tool_calls[0]["tool_name"] == "lookup_contact"


@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_reason_handles_tool_error(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_client.messages.create.side_effect = [
        make_tool_use_response(),
        make_mock_response("Sorry, I couldn't find that contact."),
    ]

    def failing_executor(tool_name, tool_input):
        raise Exception("Database connection failed")

    client = AnthropicClient(api_key="test-key")
    decision = client.reason(
        "system prompt",
        [{"role": "user", "content": "Look up unknown"}],
        tools=[{"name": "lookup_contact"}],
        agent_id=AGENT_ID,
        tool_executor=failing_executor,
    )

    assert decision.response_text is not None


@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_compose_returns_text(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(
        text="Hey Sarah, new listing that matches your preferences!"
    )

    client = AnthropicClient(api_key="test-key")
    text = client.compose(
        "system prompt", "context data", "compose a follow-up", AGENT_ID
    )

    assert "Sarah" in text


@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_token_tracking(mock_anthropic_cls):
    from datetime import date
    from unittest.mock import patch as _patch

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(
        input_tokens=500, output_tokens=200
    )

    # Mock DB so _track_usage and get_usage don't hit a real database
    mock_conn = MagicMock()
    mock_row = {"date": date.today(), "tokens": 700, "cost_cents": 0.0}
    mock_conn.execute.return_value.fetchone.return_value = mock_row
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with _patch("app.db.connection.get_db_connection", return_value=mock_cm):
        client = AnthropicClient(api_key="test-key")
        client.classify("system", "test message", AGENT_ID)

        usage = client.get_usage(AGENT_ID)
        assert len(usage) > 0
        today_usage = list(usage.values())[0]
        assert today_usage["tokens"] == 700


@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_retry_on_rate_limit(mock_anthropic_cls):
    import anthropic as anthropic_module

    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    # First call rate limited, second succeeds
    rate_limit_resp = MagicMock()
    rate_limit_resp.status_code = 429
    rate_limit_resp.headers = {}
    mock_client.messages.create.side_effect = [
        anthropic_module.RateLimitError(
            message="rate limited",
            response=rate_limit_resp,
            body={"error": {"message": "rate limited", "type": "rate_limit_error"}},
        ),
        make_mock_response(text='{"intent": "noise"}'),
    ]

    client = AnthropicClient(api_key="test-key")
    result = client.classify("system", "thanks", AGENT_ID)
    assert result["intent"] == "noise"
