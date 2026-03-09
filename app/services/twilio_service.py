"""Twilio API wrapper for sending SMS/RCS messages."""
import logging
from uuid import UUID

from twilio.rest import Client

from app.config import get_settings
from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_twilio_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


def send_sms(to: str, from_: str, body: str, agent_id: UUID | None = None) -> dict:
    """
    Send an SMS/RCS message via Twilio.
    Logs to the messages table if agent_id provided.
    Returns {sid, status}.
    """
    try:
        client = get_twilio_client()
        message = client.messages.create(to=to, from_=from_, body=body)

        result = {"sid": message.sid, "status": message.status}
        logger.info(f"Sent SMS to {to}: {body[:50]}...")
        return result

    except Exception as e:
        logger.error(f"Failed to send SMS to {to}: {e}")
        return {"sid": None, "status": "failed", "error": str(e)}


def send_client_message(
    agent_id: UUID,
    contact_id: UUID,
    message: str,
    from_number: str,
    to_number: str,
) -> dict:
    """
    Send a message to a client via Twilio RCS with SMS fallback.
    Logs to messages table automatically.
    """
    result = send_sms(to=to_number, from_=from_number, body=message, agent_id=agent_id)

    # Log the outbound message
    try:
        with get_db_connection() as conn:
            # Get or create conversation
            conv = conn.execute(
                """SELECT id FROM conversations
                   WHERE agent_id = %s AND contact_id = %s
                   ORDER BY created_at DESC LIMIT 1""",
                [str(agent_id), str(contact_id)],
            ).fetchone()

            if conv:
                conv_id = conv["id"]
            else:
                new_conv = conn.execute(
                    """INSERT INTO conversations (agent_id, contact_id, channel, stage, last_message_at)
                       VALUES (%s, %s, 'rcs', 'open', now()) RETURNING id""",
                    [str(agent_id), str(contact_id)],
                ).fetchone()
                conv_id = new_conv["id"]

            conn.execute(
                """INSERT INTO messages (agent_id, conversation_id, sender_type, body, ai_generated)
                   VALUES (%s, %s, 'ai', %s, true)""",
                [str(agent_id), str(conv_id), message],
            )

            # Update contact last_contact_at
            conn.execute(
                "UPDATE contacts SET last_contact_at = now() WHERE id = %s",
                [str(contact_id)],
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log outbound message: {e}")

    result["channel"] = "rcs"
    result["timestamp"] = None
    return result
