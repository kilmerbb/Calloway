"""Router — routes classified intents to the correct handler."""
import logging
from uuid import UUID

from app.db.connection import get_db_connection

import psycopg
from app.models.schemas import (
    NormalizedEvent, Contact, AgentConfig,
    IntentClassification, AgentDecision,
)
from app.pipeline.assembler import assemble_context, _find_referenced_listing
from app.pipeline.handlers import (
    handle_agent_command, handle_listing_qa,
    handle_template, handle_full_reasoning, handle_escalation,
)

logger = logging.getLogger(__name__)


def get_agent_status(agent_id: UUID) -> str:
    """Get current agent status."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT current_status FROM agents WHERE id = %s",
                [str(agent_id)],
            ).fetchone()
        return row["current_status"] if row else "available"
    except psycopg.Error:
        return "available"


def route_and_handle(
    event: NormalizedEvent,
    contact: Contact | None,
    intent: IntentClassification,
    agent: AgentConfig,
) -> AgentDecision:
    """Route to the correct handler based on intent and autonomy."""

    # Check agent status for autonomy override
    agent_status = get_agent_status(agent.id)
    if agent_status in ("in_showing", "after_hours", "vacation"):
        effective_autonomy = "autonomous"
    else:
        effective_autonomy = agent.autonomy_rules.get("level", "moderate")

    # Route based on intent
    if intent.intent == "noise":
        logger.info("Noise message, no response")
        return AgentDecision(response_text=None, model_used="template", tokens_used=0)

    if intent.intent == "agent_command":
        return handle_agent_command(event, agent)

    if intent.intent == "listing_qa":
        listing = _find_referenced_listing(event.body, agent.id)
        if listing:
            return handle_listing_qa(event, contact, agent, listing)
        else:
            # Can't find the listing, escalate
            return handle_escalation(event, contact, agent, "listing_not_found")

    if intent.intent == "escalation":
        return handle_escalation(event, contact, agent, "client_request")

    # For intents requiring full reasoning, check autonomy
    if intent.intent in ("scheduling", "lead_qualification", "transaction", "personal"):
        if effective_autonomy == "autonomous" or _is_always_autonomous(intent.intent):
            context = assemble_context(event, contact, intent, agent)
            return handle_full_reasoning(event, contact, context, agent)
        elif effective_autonomy in ("moderate", "low"):
            # For moderate: handle common cases, escalate complex ones
            if intent.intent == "personal":
                return handle_template(event, contact, agent, "acknowledgment")
            context = assemble_context(event, contact, intent, agent)
            return handle_full_reasoning(event, contact, context, agent)
        else:
            # Conservative — notify agent
            return handle_escalation(event, contact, agent, "autonomy_check")

    # Default: try full reasoning
    context = assemble_context(event, contact, intent, agent)
    return handle_full_reasoning(event, contact, context, agent)


def _is_always_autonomous(intent: str) -> bool:
    """Some actions are always autonomous regardless of setting."""
    return intent in ("listing_qa", "noise", "personal")
