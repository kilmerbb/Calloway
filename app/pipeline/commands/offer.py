"""Offer-related command handlers."""

import logging

from app.models.schemas import AgentConfig, AgentDecision
from app.tools.contacts import lookup_contact

logger = logging.getLogger(__name__)


def handle_offer_command(
    agent: AgentConfig, contact_name: str | None, listing_address: str | None,
) -> AgentDecision:
    """Handle offer preparation commands."""
    if not contact_name:
        return AgentDecision(
            response_text="Which client wants to make an offer?",
            model_used="template",
        )

    contact = lookup_contact(agent.id, name=contact_name)
    if contact is None or isinstance(contact, list):
        return AgentDecision(
            response_text="Could you clarify the client name?",
            model_used="template",
        )

    return AgentDecision(
        response_text=f"Offer prep started for {contact.name}. I'll request docs from them and notify you when ready.",
        tool_calls=[{
            "tool_name": "send_client_message",
            "input": {
                "agent_id": str(agent.id),
                "contact_id": str(contact.id),
                "message": (
                    f"Exciting! {agent.name} mentioned you're interested in making an offer. "
                    f"To get started, I'll need: (1) Current pre-approval letter "
                    f"(2) Proof of funds for earnest money. "
                    f"Can you send those over? {agent.name} will call you today to discuss strategy."
                ),
            },
        }],
        notifications=[{
            "tier": "action_needed",
            "title": f"Offer prep: {contact.name}",
            "body": (
                f"{contact.name} wants to offer"
                f"{' on ' + listing_address if listing_address else ''}. "
                f"Docs requested. Call them to discuss strategy."
            ),
        }],
        model_used="template",
    )
