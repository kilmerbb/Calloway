"""Context assembler — loads only what the route needs based on intent."""
import logging
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import (
    NormalizedEvent, Contact, AgentConfig, IntentClassification,
    AssembledContext, Listing, Trigger, Message,
)
from app.tools.listings import get_listing, search_listings

logger = logging.getLogger(__name__)

TOKEN_BUDGET = 8000
TOKENS_PER_MESSAGE = 50  # rough estimate


def assemble_context(
    event: NormalizedEvent,
    contact: Contact | None,
    intent: IntentClassification,
    agent: AgentConfig,
) -> AssembledContext:
    """Load the right context based on intent classification."""
    listings: list[Listing] = []
    triggers: list[Trigger] = []
    conversation_history: list[Message] = []
    calendar_slots: list[dict] | None = None

    # Load conversation history for known contacts
    if contact:
        conversation_history = _load_conversation_history(agent.id, contact.id)

    # Intent-specific loading
    if intent.intent == "listing_qa":
        listing = _find_referenced_listing(event.body, agent.id)
        if listing:
            listings = [listing]

    elif intent.intent == "scheduling":
        if contact:
            listings = _load_relevant_listings(agent.id, contact)
        calendar_slots = _load_calendar_placeholder(agent.id)
        if contact:
            triggers = _load_contact_triggers(agent.id, contact.id)

    elif intent.intent == "lead_qualification":
        listings = search_listings(agent.id, filters={"status": "active"})

    elif intent.intent == "transaction":
        if contact:
            triggers = _load_contact_triggers(agent.id, contact.id)

    elif intent.intent == "escalation":
        pass  # Just conversation history (already loaded)

    elif intent.intent == "agent_command":
        listings = search_listings(agent.id, filters={"status": "active"})
        calendar_slots = _load_calendar_placeholder(agent.id)

    # Token budget trimming
    total_tokens = _estimate_tokens(listings, conversation_history, triggers)
    if total_tokens > TOKEN_BUDGET:
        # Trim conversation history first
        while conversation_history and total_tokens > TOKEN_BUDGET:
            conversation_history.pop(0)
            total_tokens -= TOKENS_PER_MESSAGE
        # Then trim listings if still over
        while len(listings) > 3 and total_tokens > TOKEN_BUDGET:
            listings.pop()
            total_tokens -= 200

    return AssembledContext(
        agent=agent,
        contact=contact,
        listings=listings,
        calendar_slots=calendar_slots,
        triggers=triggers,
        conversation_history=conversation_history,
        intent=intent,
    )


def _load_conversation_history(
    agent_id: UUID, contact_id: UUID, limit: int = 20
) -> list[Message]:
    """Load the last N messages for a contact."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """SELECT m.* FROM messages m
                   JOIN conversations c ON m.conversation_id = c.id
                   WHERE c.agent_id = %s AND c.contact_id = %s
                   ORDER BY m.created_at DESC LIMIT %s""",
                [str(agent_id), str(contact_id), limit],
            ).fetchall()
        return [Message(**r) for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Failed to load conversation history: {e}")
        return []


def _find_referenced_listing(body: str, agent_id: UUID) -> Listing | None:
    """Try to find a listing referenced in the message body."""
    # Simple: check all listings for address match in the message
    listings = search_listings(agent_id, filters={"status": "active"})
    body_lower = body.lower()
    for listing in listings:
        addr_parts = listing.address.lower().split()
        if any(part in body_lower for part in addr_parts if len(part) > 2):
            return listing
    return None


def _load_relevant_listings(agent_id: UUID, contact: Contact) -> list[Listing]:
    """Load listings relevant to a contact's preferences."""
    return search_listings(agent_id, filters={"status": "active"})


def _load_contact_triggers(agent_id: UUID, contact_id: UUID) -> list[Trigger]:
    """Load active triggers for a contact."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM triggers
                   WHERE agent_id = %s AND entity_id = %s AND status = 'pending'
                   ORDER BY scheduled_at LIMIT 10""",
                [str(agent_id), str(contact_id)],
            ).fetchall()
        return [Trigger(**r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to load triggers: {e}")
        return []


def _load_calendar_placeholder(agent_id: UUID) -> list[dict]:
    """Placeholder for Google Calendar. Returns empty until Step 18."""
    return []


def _estimate_tokens(
    listings: list[Listing],
    messages: list[Message],
    triggers: list[Trigger],
) -> int:
    """Rough token count estimate."""
    return (
        len(listings) * 200
        + len(messages) * TOKENS_PER_MESSAGE
        + len(triggers) * 50
        + 500  # base system prompt
    )
