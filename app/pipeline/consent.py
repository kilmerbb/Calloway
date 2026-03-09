"""TCPA consent handling — STOP/HELP/START keywords and consent gating."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import NormalizedEvent, Contact, AgentConfig

logger = logging.getLogger(__name__)

STOP_KEYWORDS = {"stop", "unsubscribe", "cancel", "quit", "end"}
HELP_KEYWORDS = {"help", "info"}
START_KEYWORDS = {"start", "subscribe", "resume"}

# Affirmative responses for consent granting
AFFIRMATIVE_KEYWORDS = {"yes", "yeah", "sure", "ok", "okay", "sounds good", "y", "yep", "yea"}


def check_tcpa_keywords(
    event: NormalizedEvent, contact: Contact | None, agent: AgentConfig
) -> dict | None:
    """
    Check for TCPA keywords BEFORE pipeline processing.
    Returns a dict with {action, response_text} if a keyword is matched,
    or None to continue normal processing.
    """
    body = event.body.strip().lower()

    if body in STOP_KEYWORDS:
        return _handle_stop(event, contact, agent)

    if body in HELP_KEYWORDS:
        return _handle_help(event, contact, agent)

    if body in START_KEYWORDS:
        return _handle_start(event, contact, agent)

    # Check if this is an affirmative response to a consent request
    if contact and contact.consent_status == "pending" and body in AFFIRMATIVE_KEYWORDS:
        return _handle_consent_granted(event, contact, agent)

    return None


def _handle_stop(
    event: NormalizedEvent, contact: Contact | None, agent: AgentConfig
) -> dict:
    """Handle STOP keyword — revoke consent."""
    if contact:
        with get_db_connection() as conn:
            conn.execute(
                """UPDATE contacts SET consent_status = 'revoked',
                   consent_revoked_at = now() WHERE id = %s""",
                [str(contact.id)],
            )
            conn.execute(
                """INSERT INTO consent_log (agent_id, contact_id, event_type,
                   message_text, response_text)
                   VALUES (%s, %s, 'revoked', %s, %s)""",
                [str(agent.id), str(contact.id), event.body,
                 "You've been unsubscribed and will not receive further messages. "
                 "Reply START to re-subscribe."],
            )
            conn.commit()

    logger.info(f"STOP received from {event.sender_phone} — consent revoked")
    return {
        "action": "stop",
        "response_text": (
            "You've been unsubscribed and will not receive further messages. "
            "Reply START to re-subscribe."
        ),
        "notify_agent": True,
        "notification": {
            "tier": "action_needed",
            "title": f"Opt-out: {contact.name if contact else event.sender_phone}",
            "body": f"{contact.name if contact else event.sender_phone} has opted out of messages.",
        },
    }


def _handle_help(
    event: NormalizedEvent, contact: Contact | None, agent: AgentConfig
) -> dict:
    """Handle HELP keyword."""
    return {
        "action": "help",
        "response_text": (
            f"This is {agent.name}'s digital assistant. "
            f"For help, contact {agent.name} at {agent.phone}. "
            f"Reply STOP to opt out."
        ),
        "notify_agent": False,
    }


def _handle_start(
    event: NormalizedEvent, contact: Contact | None, agent: AgentConfig
) -> dict:
    """Handle START keyword — re-initiate consent flow."""
    if contact:
        with get_db_connection() as conn:
            conn.execute(
                """UPDATE contacts SET consent_status = 'pending',
                   consent_revoked_at = NULL WHERE id = %s""",
                [str(contact.id)],
            )
            conn.commit()

        # Send opt-in message
        intro = _build_consent_message(agent, contact.name)
        return {
            "action": "start",
            "response_text": intro,
            "notify_agent": False,
        }

    return {
        "action": "start",
        "response_text": (
            f"Hi! I'm {agent.name}'s digital assistant. "
            f"Msg & data rates may apply. Reply STOP to opt out. "
            f"Reply YES to get started!"
        ),
        "notify_agent": False,
    }


def _handle_consent_granted(
    event: NormalizedEvent, contact: Contact, agent: AgentConfig
) -> dict:
    """Handle affirmative response to consent request."""
    with get_db_connection() as conn:
        conn.execute(
            """UPDATE contacts SET consent_status = 'granted',
               consent_granted_at = now(), consent_response = %s
               WHERE id = %s""",
            [event.body, str(contact.id)],
        )
        conn.execute(
            """INSERT INTO consent_log (agent_id, contact_id, event_type,
               message_text, response_text)
               VALUES (%s, %s, 'granted', %s, %s)""",
            [str(agent.id), str(contact.id), event.body,
             f"Welcome! {agent.name} is glad to have you connected."],
        )
        conn.commit()

    logger.info(f"Consent granted by {contact.name} ({contact.phone})")
    return {
        "action": "consent_granted",
        "response_text": (
            f"Welcome! I'm {agent.name}'s digital assistant. "
            f"I can help with scheduling showings, property info, and more. "
            f"How can I help you today?"
        ),
        "notify_agent": False,
    }


def check_consent_before_send(contact: Contact | None) -> bool:
    """
    CRITICAL: Hard check — NEVER send a message to a contact
    with consent_status != 'granted'.
    Returns True if sending is allowed.
    """
    if contact is None:
        return True  # Unknown contacts get one-off responses
    return contact.consent_status == "granted"


def _build_consent_message(agent: AgentConfig, client_name: str) -> str:
    """Build the TCPA-compliant consent request message."""
    return (
        f"Hi {client_name}! {agent.name} just connected us. "
        f"I'm {agent.name}'s digital assistant and I can help with "
        f"scheduling, property info, and more. "
        f"Msg & data rates may apply. Reply STOP to opt out. "
        f"Reply YES to get started!"
    )


def send_consent_request(
    agent: AgentConfig, contact: Contact
) -> str:
    """Send the initial consent request to a new contact. Returns the message text."""
    message = _build_consent_message(agent, contact.name)

    with get_db_connection() as conn:
        conn.execute(
            """UPDATE contacts SET consent_status = 'pending',
               consent_message = %s, consent_method = 'agent_intro'
               WHERE id = %s""",
            [message, str(contact.id)],
        )
        conn.commit()

    return message


def check_consent_expiry(agent_id: UUID) -> list[dict]:
    """Find contacts with pending consent > 48h — notify agent."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    expired = []

    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM contacts
               WHERE agent_id = %s AND consent_status = 'pending'
               AND created_at < %s""",
            [str(agent_id), cutoff],
        ).fetchall()

    for row in rows:
        expired.append({
            "contact_id": row["id"],
            "name": row["name"],
            "phone": row["phone"],
            "created_at": row["created_at"],
        })

    return expired
