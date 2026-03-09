"""Tests for event normalization."""
from uuid import UUID
from app.pipeline.normalizer import normalize_twilio_event, normalize_vapi_event

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def test_normalize_normal_sms():
    payload = {
        "From": "+12675551234",
        "To": "+12155559999",
        "Body": "What's the HOA on 123 Oak?",
        "MessageSid": "SM1234567890",
        "AccountSid": "AC0987654321",
        "NumMedia": "0",
    }
    event = normalize_twilio_event(payload, AGENT_ID)
    assert event.sender_phone == "+12675551234"
    assert event.body == "What's the HOA on 123 Oak?"
    assert event.provider_message_id == "SM1234567890"
    assert event.agent_id == AGENT_ID
    assert event.channel in ("sms", "rcs")


def test_normalize_rcs_message():
    payload = {
        "From": "+12675551234",
        "To": "+12155559999",
        "Body": "Can we see houses Saturday?",
        "MessageSid": "SM9999",
        "MessagingServiceSid": "MG1234",
    }
    event = normalize_twilio_event(payload, AGENT_ID)
    assert event.channel == "rcs"


def test_normalize_empty_body():
    payload = {
        "From": "+12675551234",
        "To": "+12155559999",
        "Body": "",
        "MessageSid": "SM0000",
    }
    event = normalize_twilio_event(payload, AGENT_ID)
    assert event.body == ""


def test_normalize_media_message():
    payload = {
        "From": "+12675551234",
        "To": "+12155559999",
        "Body": "",
        "MessageSid": "SM1111",
        "NumMedia": "1",
        "MediaUrl0": "https://example.com/image.jpg",
    }
    event = normalize_twilio_event(payload, AGENT_ID)
    assert event.raw_payload["NumMedia"] == "1"


def test_normalize_preserves_raw_payload():
    payload = {
        "From": "+12675551234",
        "To": "+12155559999",
        "Body": "Hello",
        "MessageSid": "SM2222",
        "CustomField": "custom_value",
    }
    event = normalize_twilio_event(payload, AGENT_ID)
    assert event.raw_payload["CustomField"] == "custom_value"


def test_normalize_vapi_transcript():
    payload = {
        "call_id": "call_123",
        "customer": {"number": "+12675559999"},
        "transcript": "I want to schedule a showing",
    }
    event = normalize_vapi_event(payload, AGENT_ID)
    assert event.sender_phone == "+12675559999"
    assert event.body == "I want to schedule a showing"
    assert event.channel == "vapi"


def test_normalize_vapi_messages_fallback():
    payload = {
        "call_id": "call_456",
        "customer": {"number": "+12675558888"},
        "messages": [
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Is 123 Oak still available"},
            {"role": "user", "content": "What's the price"},
        ],
    }
    event = normalize_vapi_event(payload, AGENT_ID)
    assert "Is 123 Oak still available" in event.body
    assert "What's the price" in event.body
