"""Message handlers — command routing, reasoning, listing QA, and templates.

Command implementations live in app.pipeline.commands.*
This module provides:
  - handle_agent_command: classifies and routes agent SMS commands
  - handle_full_reasoning: Sonnet with tool use for client conversations
  - handle_escalation: escalate to agent with notification
  - handle_listing_qa: Haiku-powered listing Q&A
  - handle_template: zero-LLM template responses
"""

import json
import logging
from datetime import datetime
from uuid import UUID

from app.models.schemas import (
    NormalizedEvent, Contact, AgentConfig, AgentDecision,
    Listing, AssembledContext,
)
from app.services.anthropic_service import get_anthropic_client
from app.tools.contacts import lookup_contact
from app.tools.listings import get_listing, search_listings
from app.db.connection import get_db_connection

from app.pipeline.commands import (
    handle_listing_command,
    handle_listing_query,
    handle_broadcast,
    handle_client_instruction,
    handle_contact_query,
    handle_note_command,
    handle_connect_command,
    handle_status_change,
    handle_handoff_return,
    handle_schedule_query,
    handle_gap_query,
    handle_trigger_command,
    handle_cascade_command,
    handle_offer_command,
)

logger = logging.getLogger(__name__)

# ── Command Classification ────────────────────────────────────

COMMAND_CLASSIFY_PROMPT = """You are parsing a command from a real estate agent to their AI assistant.
Classify this command into exactly one type and extract structured data.

Command types:
- client_instruction: "Text Sarah and confirm Thursday"
- listing_update: "New listing 123 Oak, 3/2, 475K" or "Drop 123 Oak to 465K"
- broadcast: "Send 200 Front to matching buyers"
- status_change: "I'm in showings until 3" / "I'm back" / "I've got Sarah"
- query_contact: "What's going on with Mike?"
- query_gap: "Who needs follow-up?" / "Who's gone quiet?"
- query_schedule: "What's my day look like?"
- query_listing: "How many showings on 123 Oak this week?"
- trigger: "Remind me to follow up with Sarah Friday"
- cascade: "Open house Saturday 1-3" / "Sarah's deal: inspection March 10"
- offer: "Sarah wants to offer on 123 Oak"
- handoff_return: "Back from Sarah. We're seeing 123 Oak Saturday 11am." / "Back from Mike. He's pre-approved up to 500K."
- note: "Note on Sarah: lease ends June 30" / "Note on Mike: prefers morning showings"
- connect: "Connect Sarah Chen +12675551234" / "Connect John Doe +15551234567 buyer in Fishtown"

Return JSON:
{
  "command_type": string,
  "contact_name": string or null,
  "listing_address": string or null,
  "details": string (any additional info),
  "time_reference": string or null (e.g. "until 3pm", "Friday", "Saturday 1-3"),
  "raw_data": string (the full data to pass through)
}

Return ONLY valid JSON."""


# ── Command dispatch table ────────────────────────────────────

_COMMAND_HANDLERS = {
    "listing_update": lambda e, a, p: handle_listing_command(e, a, e.body.strip(), p),
    "client_instruction": lambda e, a, p: handle_client_instruction(e, a, p.get("contact_name"), p.get("details", ""), p),
    "status_change": lambda e, a, p: handle_status_change(e, a, p.get("contact_name"), p.get("time_reference"), e.body.strip()),
    "query_gap": lambda e, a, p: handle_gap_query(a),
    "query_contact": lambda e, a, p: handle_contact_query(a, p.get("contact_name")),
    "query_schedule": lambda e, a, p: handle_schedule_query(a),
    "query_listing": lambda e, a, p: handle_listing_query(a, p.get("listing_address")),
    "broadcast": lambda e, a, p: handle_broadcast(a, p.get("listing_address")),
    "trigger": lambda e, a, p: handle_trigger_command(a, p.get("contact_name"), p.get("time_reference"), p.get("details", "")),
    "cascade": lambda e, a, p: handle_cascade_command(a, p.get("listing_address"), p.get("contact_name"), p.get("time_reference"), p.get("details", ""), e.body.strip()),
    "offer": lambda e, a, p: handle_offer_command(a, p.get("contact_name"), p.get("listing_address")),
    "handoff_return": lambda e, a, p: handle_handoff_return(a, p.get("contact_name"), p.get("details", ""), p.get("listing_address"), p.get("time_reference"), e.body.strip()),
    "note": lambda e, a, p: handle_note_command(a, p.get("contact_name"), p.get("details", "")),
    "connect": lambda e, a, p: handle_connect_command(e, a, p.get("contact_name"), p.get("details", ""), e.body.strip()),
}


def handle_agent_command(
    event: NormalizedEvent, agent: AgentConfig,
) -> AgentDecision:
    """Parse and execute an agent SMS command."""
    body = event.body.strip()

    try:
        client = get_anthropic_client()
        parsed = client.classify(COMMAND_CLASSIFY_PROMPT, body, agent.id, max_tokens=300)
    except Exception as e:
        logger.error("Command parsing failed: %s", e, exc_info=True)
        return AgentDecision(
            response_text="Sorry, I didn't understand that command. Try again?",
            model_used="template",
            tokens_used=0,
        )

    cmd_type = parsed.get("command_type", "unknown")
    handler = _COMMAND_HANDLERS.get(cmd_type)

    if handler:
        return handler(event, agent, parsed)

    return AgentDecision(
        response_text="I received your message but wasn't sure what to do with it. Could you rephrase?",
        model_used="haiku",
        tokens_used=parsed.get("_tokens", 0),
    )


# ── Full Reasoning (Sonnet with tools) ────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are the digital assistant for {agent_name}, a real estate agent at {brokerage} in {market}.

YOUR ROLE: Answer listing questions, schedule showings, qualify leads, handle inquiries, send follow-ups, and relay urgent items.

YOU NEVER: Provide legal/financial/investment advice, discuss pricing strategy or negotiation, make promises, share client info across clients, guess or fabricate information, deliver bad news, release lockbox codes before confirmation, confirm an action unless the tool returned success.

If uncertain: "Let me confirm that with {agent_name} and get right back to you."

STYLE: {tone}. Keep messages to 1-3 short paragraphs. Texts, not emails.

AUTONOMY: Handle listing Q&A, acknowledgments, and scheduling autonomously. Escalate offers, pricing, negotiation, legal matters, client frustration, and uncertainty.

If asked "Is this AI?": answer honestly, offer to connect with {agent_name} directly."""

TOOL_DEFINITIONS = [
    {
        "name": "lookup_contact",
        "description": "Look up a contact by phone or name",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Phone number to search"},
                "name": {"type": "string", "description": "Name to search"},
            },
        },
    },
    {
        "name": "get_listing",
        "description": "Get listing details by address or ID",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "listing_id": {"type": "string"},
            },
        },
    },
    {
        "name": "search_listings",
        "description": "Search listings by criteria",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "filters": {"type": "object"},
            },
        },
    },
    {
        "name": "check_calendar",
        "description": "Check calendar availability for a date",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "create_showing_hold",
        "description": "Create a showing hold (30-min expiry). Do NOT confirm until client agrees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "listing_id": {"type": "string"},
                "desired_time": {"type": "string", "description": "ISO datetime"},
            },
            "required": ["contact_id", "listing_id", "desired_time"],
        },
    },
    {
        "name": "confirm_showing",
        "description": "Confirm a showing hold after client agrees",
        "input_schema": {
            "type": "object",
            "properties": {"hold_id": {"type": "string"}},
            "required": ["hold_id"],
        },
    },
    {
        "name": "send_client_message",
        "description": "Send a text message to a client",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["contact_id", "message"],
        },
    },
    {
        "name": "notify_agent",
        "description": "Send a push notification to the agent",
        "input_schema": {
            "type": "object",
            "properties": {
                "tier": {"type": "string", "enum": ["urgent", "action_needed", "informational"]},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["tier", "title", "body"],
        },
    },
    {
        "name": "create_trigger",
        "description": "Schedule a future action (follow-up, reminder, deadline)",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "entity_id": {"type": "string"},
                "trigger_type": {"type": "string"},
                "scheduled_at": {"type": "string"},
                "action_type": {"type": "string"},
                "message_template": {"type": "string"},
            },
            "required": ["entity_type", "entity_id", "trigger_type", "scheduled_at", "action_type"],
        },
    },
]


def _execute_tool(tool_name: str, tool_input: dict, agent_id: UUID) -> dict:
    """Execute a tool call from the LLM and return the result."""
    from app.tools.showings import create_showing_hold, confirm_showing
    from app.tools.calendar_tools import check_calendar
    from datetime import date as date_type

    try:
        if tool_name == "lookup_contact":
            result = lookup_contact(agent_id, **tool_input)
            if result is None:
                return {"found": False}
            if isinstance(result, list):
                return {"found": True, "multiple": True, "contacts": [{"name": c.name, "id": str(c.id)} for c in result]}
            return {"found": True, "name": result.name, "id": str(result.id), "role": result.role, "lifecycle_stage": result.lifecycle_stage}

        elif tool_name == "get_listing":
            listing = get_listing(agent_id, address=tool_input.get("address"), listing_id=tool_input.get("listing_id"))
            if listing is None:
                return {"found": False}
            return {"found": True, "address": listing.address, "price": listing.price, "beds": listing.beds, "baths": str(listing.baths), "features": listing.features}

        elif tool_name == "search_listings":
            listings = search_listings(agent_id, query=tool_input.get("query"), filters=tool_input.get("filters"))
            return {"count": len(listings), "listings": [{"address": l.address, "price": l.price, "id": str(l.id)} for l in listings]}

        elif tool_name == "check_calendar":
            d = date_type.fromisoformat(tool_input["date"])
            return check_calendar(agent_id, d)

        elif tool_name == "create_showing_hold":
            return create_showing_hold(
                agent_id, UUID(tool_input["contact_id"]),
                UUID(tool_input["listing_id"]),
                datetime.fromisoformat(tool_input["desired_time"]),
            )

        elif tool_name == "confirm_showing":
            return confirm_showing(UUID(tool_input["hold_id"]))

        elif tool_name == "send_client_message":
            return {"queued": True, "contact_id": tool_input["contact_id"], "message": tool_input["message"]}

        elif tool_name == "notify_agent":
            return {"queued": True, **tool_input}

        elif tool_name == "create_trigger":
            return {"created": True, **tool_input}

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error("Tool execution error (%s): %s", tool_name, e, exc_info=True)
        return {"error": str(e)}


def handle_full_reasoning(
    event: NormalizedEvent,
    contact: Contact | None,
    context: AssembledContext,
    agent: AgentConfig,
) -> AgentDecision:
    """Full reasoning with Claude Sonnet and tools."""
    client = get_anthropic_client()

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=agent.name,
        brokerage=agent.brokerage or "their brokerage",
        market=agent.market or "their market",
        tone=agent.style_profile.get("tone", "professional"),
    )

    if contact:
        system_prompt += f"\n\nCURRENT CLIENT: {contact.name} ({contact.role}, {contact.lifecycle_stage})"
        if contact.preferences:
            system_prompt += f"\nPreferences: {json.dumps(contact.preferences)}"

    if context.listings:
        system_prompt += "\n\nAVAILABLE LISTINGS:"
        for l in context.listings:
            system_prompt += f"\n- {l.address}: ${l.price:,}, {l.beds}bd/{l.baths}ba"

    if context.calendar_slots:
        system_prompt += f"\n\nCALENDAR: {json.dumps(context.calendar_slots[:5])}"

    messages = []
    for msg in context.conversation_history:
        role = "user" if msg.sender_type == "client" else "assistant"
        messages.append({"role": role, "content": msg.body})
    messages.append({"role": "user", "content": event.body})

    def executor(name, inp):
        return _execute_tool(name, inp, agent.id)

    return client.reason(
        system_prompt, messages, TOOL_DEFINITIONS, agent.id,
        tool_executor=executor,
    )


# ── Escalation ────────────────────────────────────────────────

def handle_escalation(
    event: NormalizedEvent,
    contact: Contact | None,
    agent: AgentConfig,
    reason: str,
) -> AgentDecision:
    """Escalate to the agent with appropriate notification."""
    client_name = contact.name if contact else "Unknown sender"

    ack = handle_template(event, contact, agent, "escalation_ack")

    notification = {
        "tier": "urgent" if reason == "client_request" else "action_needed",
        "title": f"Escalation: {client_name}",
        "body": f"{client_name}: \"{event.body[:100]}\" (Reason: {reason})",
        "contact_id": str(contact.id) if contact else None,
    }

    ack.notifications = [notification]
    return ack


# ── Listing Q&A (Haiku) ──────────────────────────────────────

def handle_listing_qa(
    event: NormalizedEvent, contact: Contact | None,
    agent: AgentConfig, listing: Listing,
) -> AgentDecision:
    """Answer listing questions using Haiku. Fast and cheap."""
    client = get_anthropic_client()

    listing_data = (
        f"Address: {listing.address}\n"
        f"Price: ${listing.price:,}\n"
        f"Beds: {listing.beds}, Baths: {listing.baths}\n"
        f"Sqft: {listing.sqft or 'N/A'}\n"
        f"HOA: ${listing.hoa}/month\n" if listing.hoa else ""
        f"Features: {', '.join(listing.features)}\n"
        f"Status: {listing.status}\n"
        f"Showing instructions: {listing.showing_instructions or 'Contact for details'}"
    )

    tone = agent.style_profile.get("tone", "professional")
    prompt = (
        f"You are {agent.name}'s digital assistant. "
        f"Tone: {tone}. Keep answer brief (1-2 sentences). "
        f"Add one proactive detail the client didn't ask about."
    )

    instruction = f"Listing:\n{listing_data}\n\nQuestion: {event.body}"

    response = client.compose(prompt, listing_data, instruction, agent.id)

    return AgentDecision(
        response_text=response,
        model_used="haiku",
        tokens_used=0,
    )


# ── Template Responder (Zero LLM) ────────────────────────────

def handle_template(
    event: NormalizedEvent, contact: Contact | None,
    agent: AgentConfig, template_type: str,
    **kwargs,
) -> AgentDecision:
    """Handle simple messages with zero LLM calls."""
    templates = {
        "showing_confirmation": (
            "Confirmed! {address} at {time} with {agent_name}. "
            "Lockbox: {lockbox}."
        ),
        "appointment_reminder": (
            "Reminder: showing at {address} tomorrow at {time}."
        ),
        "acknowledgment": (
            "Got your message — {agent_name} will follow up shortly."
        ),
        "trigger_message": "{message}",
        "escalation_ack": (
            "Great question — let me have {agent_name} get back to you on that personally."
        ),
    }

    template = templates.get(template_type, templates["acknowledgment"])
    kwargs.setdefault("agent_name", agent.name)

    try:
        response_text = template.format(**kwargs)
    except KeyError:
        response_text = f"Got your message — {agent.name} will follow up shortly."

    return AgentDecision(
        response_text=response_text,
        model_used="template",
        tokens_used=0,
    )
