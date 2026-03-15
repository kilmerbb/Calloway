"""Contact-related command handlers: instructions, queries, notes, connect."""

import anthropic
import logging
import re
from datetime import datetime, timezone

from app.models.schemas import NormalizedEvent, AgentConfig, AgentDecision
from app.services.anthropic_service import get_anthropic_client
from app.tools.contacts import lookup_contact, create_contact, update_contact
from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)


def handle_client_instruction(
    event: NormalizedEvent, agent: AgentConfig,
    contact_name: str | None, details: str, parsed: dict,
) -> AgentDecision:
    """Handle client instruction commands like 'Text Sarah and confirm Thursday'."""
    if not contact_name:
        return AgentDecision(
            response_text="Which client should I contact?",
            model_used="template",
        )

    contact = lookup_contact(agent.id, name=contact_name)
    if contact is None:
        return AgentDecision(
            response_text=f"I don't have a contact named {contact_name}. Want me to create one?",
            model_used="template",
        )
    if isinstance(contact, list):
        names = ", ".join(c.name for c in contact)
        return AgentDecision(
            response_text=f"I have multiple matches: {names}. Which one?",
            model_used="template",
        )

    # Compose and queue the message
    try:
        client = get_anthropic_client()
        composed = client.compose(
            f"You are composing a text message on behalf of {agent.name}. "
            f"Tone: {agent.style_profile.get('tone', 'professional')}. "
            f"Keep it brief (1-2 sentences).",
            f"Client: {contact.name}, {contact.lifecycle_stage}. "
            f"Last contact: {contact.last_contact_at}",
            details,
            agent.id,
        )
    except anthropic.APIError:
        logger.debug("Failed to compose message for %s, falling back to raw details", contact.name, exc_info=True)
        composed = details

    return AgentDecision(
        response_text=f"Sending to {contact.name}: \"{composed}\"",
        tool_calls=[{
            "tool_name": "send_client_message",
            "input": {
                "agent_id": str(agent.id),
                "contact_id": str(contact.id),
                "message": composed,
            },
        }],
        model_used="sonnet",
        tokens_used=parsed.get("_tokens", 0),
    )


def handle_contact_query(
    agent: AgentConfig, contact_name: str | None,
) -> AgentDecision:
    """Handle 'What's going on with Mike?' queries."""
    if not contact_name:
        return AgentDecision(
            response_text="Which client are you asking about?",
            model_used="template",
        )

    contact = lookup_contact(agent.id, name=contact_name)
    if contact is None:
        return AgentDecision(
            response_text=f"I don't have anyone named {contact_name}.",
            model_used="template",
        )
    if isinstance(contact, list):
        names = ", ".join(c.name for c in contact)
        return AgentDecision(
            response_text=f"Which one? I have: {names}",
            model_used="template",
        )

    # Build summary
    lines = [f"{contact.name} ({contact.role}, {contact.lifecycle_stage})"]
    if contact.last_contact_at:
        days = (datetime.now(timezone.utc) - contact.last_contact_at.replace(tzinfo=timezone.utc)).days
        lines.append(f"Last contact: {days} day(s) ago")
    if contact.notes:
        lines.append(f"Notes: {contact.notes}")

    # Get recent messages
    with get_db_connection() as conn:
        msgs = conn.execute(
            """SELECT body, sender_type, created_at FROM messages m
               JOIN conversations c ON m.conversation_id = c.id
               WHERE c.contact_id = %s AND c.agent_id = %s
               ORDER BY m.created_at DESC LIMIT 3""",
            [str(contact.id), str(agent.id)],
        ).fetchall()

    if msgs:
        lines.append("Recent:")
        for m in reversed(msgs):
            prefix = "Client" if m["sender_type"] == "client" else "AI"
            lines.append(f"  {prefix}: {m['body'][:80]}")

    return AgentDecision(
        response_text="\n".join(lines),
        model_used="template",
    )


def handle_note_command(
    agent: AgentConfig, contact_name: str | None, details: str,
) -> AgentDecision:
    """Handle 'Note on [Name]' — add timestamped note without changing status."""
    if not contact_name:
        return AgentDecision(
            response_text="Which client should I note this on?",
            model_used="template",
        )

    contact = lookup_contact(agent.id, name=contact_name)
    if contact is None:
        return AgentDecision(
            response_text=f"I don't have a contact named {contact_name}.",
            model_used="template",
        )
    if isinstance(contact, list):
        names = ", ".join(c.name for c in contact)
        return AgentDecision(
            response_text=f"Which one? {names}",
            model_used="template",
        )

    existing_notes = contact.notes or ""
    timestamp = datetime.now(timezone.utc).strftime("%m/%d %I:%M%p")
    new_notes = f"{existing_notes}\n[{timestamp}] {details}".strip()
    update_contact(agent.id, contact.id, notes=new_notes)

    return AgentDecision(
        response_text=f"Noted on {contact.name}: {details}",
        model_used="template",
    )


def handle_connect_command(
    event: NormalizedEvent, agent: AgentConfig,
    contact_name: str | None, details: str, body: str,
) -> AgentDecision:
    """Handle 'Connect [Name] [Phone]' — create contact + send consent request."""
    if not contact_name:
        return AgentDecision(
            response_text="Who should I connect?",
            model_used="template",
        )

    phone_match = re.search(r'\+?\d[\d\s-]{9,}', body)
    phone = phone_match.group().strip().replace(" ", "").replace("-", "") if phone_match else None

    if not phone:
        return AgentDecision(
            response_text=f"I need a phone number for {contact_name}.",
            model_used="template",
        )

    existing = lookup_contact(agent.id, phone=phone)
    if existing:
        return AgentDecision(
            response_text=f"I already have {existing.name} at {phone}.",
            model_used="template",
        )

    contact = create_contact(
        agent_id=agent.id,
        name=contact_name,
        phone=phone,
        role="lead",
        lifecycle_stage="new_lead",
    )

    from app.pipeline.consent import send_consent_request
    consent_msg = send_consent_request(agent, contact)

    return AgentDecision(
        response_text=f"Created {contact_name} ({phone}). Sent intro message — waiting for their opt-in reply.",
        tool_calls=[{
            "tool_name": "send_client_message",
            "input": {
                "agent_id": str(agent.id),
                "contact_id": str(contact.id),
                "message": consent_msg,
            },
        }],
        model_used="template",
    )
