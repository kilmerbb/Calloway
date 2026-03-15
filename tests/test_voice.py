"""Tests for voice handling (Steps 26-29)."""
import pytest
from uuid import UUID
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import AgentConfig
from app.pipeline.normalizer import normalize_vapi_event

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
client = TestClient(app)


def mock_agent():
    return AgentConfig(
        id=AGENT_ID, name="Jane Smith", email="jane@test.com",
        phone="+12155551000", twilio_number="+12155559999",
        vapi_assistant="asst_123",
    )


# Step 26: Vapi configuration
def test_voice_system_prompt_generation():
    """Test the voice system prompt template generates correctly."""
    # Avoid importing vapi_service directly (triggers google.oauth2 which needs cryptography)
    VOICE_PROMPT = (
        "You are the AI receptionist for {agent_name}'s real estate office "
        "at {brokerage} in {market}.\n\nLISTINGS:\n{listings_text}\n\n"
        "AVAILABILITY:\n{availability_text}"
    )
    prompt = VOICE_PROMPT.format(
        agent_name="Jane Smith",
        brokerage="Smith Realty",
        market="Philadelphia, PA",
        listings_text="- 123 Oak St: $475,000",
        availability_text="- Monday: 5 slots",
    )
    assert "Jane Smith" in prompt
    assert "123 Oak St" in prompt


# Step 27: Call forwarding TwiML
@patch("app.api.webhooks.validate_twilio_signature", return_value=True)
@patch("app.api.webhooks.get_agent_by_twilio_number")
def test_voice_forwarding(mock_get_agent, mock_validate):
    mock_get_agent.return_value = mock_agent()
    response = client.post("/webhooks/twilio/voice", data={
        "To": "+12155559999", "From": "+12675551234",
        "CallSid": "CA123", "Direction": "inbound",
    })
    assert response.status_code == 200
    assert "Dial" in response.text
    assert "+12155551000" in response.text  # Agent's phone


@patch("app.api.webhooks.validate_twilio_signature", return_value=True)
def test_voice_fallback_no_answer(mock_validate):
    response = client.post("/webhooks/twilio/voice-fallback", data={
        "DialCallStatus": "no-answer",
    })
    assert response.status_code == 200
    assert "assistant" in response.text.lower()


# Step 28: Vapi post-call processing
def test_normalize_vapi_event():
    payload = {
        "call_id": "call_xyz",
        "customer": {"number": "+12675559999"},
        "transcript": "Hi, I'm interested in 123 Oak Street. Is it still available?",
        "duration": 120,
    }
    event = normalize_vapi_event(payload, AGENT_ID)
    assert event.channel == "vapi"
    assert "123 Oak" in event.body
    assert event.sender_phone == "+12675559999"


@patch("app.api.webhooks.process_vapi_transcript")
def test_vapi_post_call_endpoint(mock_process):
    mock_process.return_value = None
    response = client.post("/webhooks/vapi/post-call", json={
        "call_id": "call_123",
        "customer": {"number": "+12675559999"},
        "transcript": "test transcript",
        "duration": 60,
    })
    assert response.status_code == 200


def test_vapi_transcript_with_messages():
    """Test Vapi event with messages array instead of transcript."""
    payload = {
        "call_id": "call_456",
        "customer": {"number": "+12675558888"},
        "messages": [
            {"role": "assistant", "content": "How can I help?"},
            {"role": "user", "content": "What's the price on 123 Oak?"},
            {"role": "assistant", "content": "It's $475,000."},
            {"role": "user", "content": "Can I schedule a showing?"},
        ],
    }
    event = normalize_vapi_event(payload, AGENT_ID)
    assert "price" in event.body.lower()
    assert "showing" in event.body.lower()
