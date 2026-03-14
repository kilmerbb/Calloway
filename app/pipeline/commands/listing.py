"""Listing-related command handlers: create/update, query, and broadcast."""

import logging
from datetime import datetime

from app.models.schemas import NormalizedEvent, AgentConfig, AgentDecision
from app.tools.contacts import search_contacts
from app.tools.listings import ingest_listing, get_listing

logger = logging.getLogger(__name__)


def handle_listing_command(
    event: NormalizedEvent, agent: AgentConfig, body: str, parsed: dict,
) -> AgentDecision:
    """Handle listing creation/update commands."""
    try:
        listing, missing = ingest_listing(agent.id, body)
        response = f"Got it! Listing created:\n{listing.address} — ${listing.price:,}"
        if listing.beds:
            response += f"\n{listing.beds}bd/{listing.baths}ba"
        if missing:
            response += f"\n\nMissing: {', '.join(missing)}. Send those when you can."
        if listing.lockbox:
            response += f"\nLockbox: {listing.lockbox}"

        return AgentDecision(
            response_text=response,
            model_used="haiku",
            tokens_used=parsed.get("_tokens", 0),
        )
    except Exception as e:  # Broad catch: mixed LLM parsing + DB operations
        logger.error("Listing ingestion failed: %s", e, exc_info=True)
        return AgentDecision(
            response_text=f"Couldn't process that listing: {e}",
            model_used="template",
        )


def handle_listing_query(
    agent: AgentConfig, listing_address: str | None,
) -> AgentDecision:
    """Handle listing activity queries."""
    if not listing_address:
        return AgentDecision(
            response_text="Which listing are you asking about?",
            model_used="template",
        )

    listing = get_listing(agent.id, address=listing_address)
    if not listing:
        return AgentDecision(
            response_text=f"I don't have a listing matching '{listing_address}'.",
            model_used="template",
        )

    from app.db.connection import get_db_connection

    with get_db_connection() as conn:
        count = conn.execute(
            """SELECT COUNT(*) as cnt FROM showings
               WHERE listing_id = %s AND created_at > now() - interval '7 days'""",
            [str(listing.id)],
        ).fetchone()

    showing_count = count["cnt"] if count else 0
    dom = (datetime.now().date() - listing.list_date).days if listing.list_date else 0

    return AgentDecision(
        response_text=f"{listing.address}: {showing_count} showing(s) this week. "
                      f"DOM: {dom}. Status: {listing.status}. Price: ${listing.price:,}.",
        model_used="template",
    )


def handle_broadcast(
    agent: AgentConfig, listing_address: str | None,
) -> AgentDecision:
    """Handle broadcast commands — send listing to matching buyers."""
    if not listing_address:
        return AgentDecision(
            response_text="Which listing should I broadcast?",
            model_used="template",
        )

    listing = get_listing(agent.id, address=listing_address)
    if not listing:
        return AgentDecision(
            response_text=f"Listing '{listing_address}' not found.",
            model_used="template",
        )

    matching = search_contacts(agent.id, lifecycle_stage="active_buyer")

    if not matching:
        return AgentDecision(
            response_text="No active buyers in the system to notify.",
            model_used="template",
        )

    tool_calls = [
        {
            "tool_name": "send_personalized_listing_alert",
            "input": {
                "agent_id": str(agent.id),
                "contact_id": str(contact.id),
                "listing_id": str(listing.id),
            },
        }
        for contact in matching
    ]

    return AgentDecision(
        response_text=f"Sending {listing.address} (${listing.price:,}) to {len(matching)} active buyer(s).",
        tool_calls=tool_calls,
        model_used="template",
    )
