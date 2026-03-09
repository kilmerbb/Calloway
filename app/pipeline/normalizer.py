"""Event normalization — converts raw provider payloads into NormalizedEvent."""
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.models.schemas import NormalizedEvent

logger = logging.getLogger(__name__)


def normalize_twilio_event(raw_payload: dict, agent_id: UUID) -> NormalizedEvent:
    """Convert raw Twilio SMS/RCS payload into a NormalizedEvent."""
    sender_phone = raw_payload.get("From", "")
    body = raw_payload.get("Body", "")
    message_sid = raw_payload.get("MessageSid", "")

    # Determine channel — Twilio doesn't explicitly flag RCS vs SMS in basic webhooks
    # but we can check for RCS-specific fields or default to sms
    channel = "rcs" if raw_payload.get("MessagingServiceSid") else "sms"

    return NormalizedEvent(
        sender_phone=sender_phone,
        sender_name=None,
        channel=channel,
        body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id=message_sid,
        raw_payload=raw_payload,
        agent_id=agent_id,
    )


def normalize_vapi_event(raw_payload: dict, agent_id: UUID) -> NormalizedEvent:
    """Convert Vapi post-call transcript into a NormalizedEvent."""
    # Extract caller info from Vapi payload
    caller = raw_payload.get("customer", {})
    caller_phone = caller.get("number", "")

    # Get transcript as body
    transcript = raw_payload.get("transcript", "")
    if not transcript:
        messages = raw_payload.get("messages", [])
        transcript = " ".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )

    return NormalizedEvent(
        sender_phone=caller_phone,
        sender_name=None,
        channel="vapi",
        body=transcript,
        timestamp=datetime.now(timezone.utc),
        provider_message_id=raw_payload.get("call_id", ""),
        raw_payload=raw_payload,
        agent_id=agent_id,
    )


def normalize_email_event(raw_payload: dict, agent_id: UUID) -> NormalizedEvent:
    """Convert inbound email payload into a NormalizedEvent."""
    return NormalizedEvent(
        sender_phone=raw_payload.get("from", ""),
        sender_name=raw_payload.get("from_name"),
        channel="email",
        body=raw_payload.get("text", raw_payload.get("html", "")),
        timestamp=datetime.now(timezone.utc),
        provider_message_id=raw_payload.get("message_id", ""),
        raw_payload=raw_payload,
        agent_id=agent_id,
    )
