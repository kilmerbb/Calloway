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

    # Look up contact by phone
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """SELECT * FROM contacts
                   WHERE agent_id = %s AND phone = %s""",
                [str(event.agent_id), event.sender_phone],
            ).fetchone()

        if row:
            contact = Contact(**row)
            logger.info(f"Resolved contact: {contact.name} ({contact.role})")
            return contact, False

        logger.info(f"Unknown sender: {event.sender_phone}")
        return None, False

    except Exception as e:
        logger.error(f"Contact resolution failed: {e}")
        # On DB error, process as unknown rather than failing
        return None, False
