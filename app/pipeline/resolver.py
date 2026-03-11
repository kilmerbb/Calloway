"""Contact resolution — looks up sender in contacts database."""
import logging
from uuid import UUID

from app.db.connection import get_db_connection, set_agent_context
from app.models.schemas import NormalizedEvent, Contact, AgentConfig

logger = logging.getLogger(__name__)


def resolve_contact(
    event: NormalizedEvent, agent: AgentConfig
) -> tuple[Contact | None, bool]:
    """
    Look up the sender in the contacts database.

    Returns:
        (Contact or None, is_agent_command: bool)
        - If sender is the agent themselves, returns (None, True)
        - If sender is a known contact, returns (Contact, False)
        - If sender is unknown, returns (None, False)
    """
    # Check if sender is the agent themselves
    if event.sender_phone == agent.phone:
        return None, True
    if event.channel == "email" and event.sender_phone == agent.email:
        return None, True

    # Look up contact by phone or email
    try:
        with get_db_connection() as conn:
            if event.channel == "email":
                row = conn.execute(
                    """SELECT * FROM contacts
                       WHERE agent_id = %s AND (email = %s OR phone = %s)""",
                    [str(event.agent_id), event.sender_phone, event.sender_phone],
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT * FROM contacts
                       WHERE agent_id = %s AND phone = %s""",
                    [str(event.agent_id), event.sender_phone],
                ).fetchone()

        if row:
            contact = Contact(**row)
            logger.info("Resolved contact: %s (%s)", contact.name, contact.role)
            return contact, False

        logger.info("Unknown sender: %s (channel=%s)", event.sender_phone, event.channel)
        return None, False

    except Exception as e:
        logger.error("Contact resolution failed: %s", e, exc_info=True)
        return None, False
