"""All message handlers — command, listing QA, template, and full reasoning."""
import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.models.schemas import (
    NormalizedEvent, Contact, AgentConfig, AgentDecision,
    Listing, AssembledContext, IntentClassification,
)
from app.services.anthropic_service import get_anthropic_client
from app.tools.contacts import (
    lookup_contact, create_contact, update_contact,
    search_contacts, analyze_contact_gaps,
)
from app.tools.listings import (
    ingest_listing, update_listing, get_listing, search_listings,
)
from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)

# ============================================================
# Step 10: Agent Command Handler
# ============================================================

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


def handle_agent_command(
    event: NormalizedEvent, agent: AgentConfig
) -> AgentDecision:
    """Parse and execute an agent SMS command."""
    body = event.body.strip()

    # Try LLM parsing
    try:
        client = get_anthropic_client()
        parsed = client.classify(COMMAND_CLASSIFY_PROMPT, body, agent.id, max_tokens=300)
    except Exception as e:
        logger.error(f"Command parsing failed: {e}")
        return AgentDecision(
            response_text=f"Sorry, I didn't understand that command. Try again?",
            model_used="template",
            tokens_used=0,
        )

    cmd_type = parsed.get("command_type", "unknown")
    contact_name = parsed.get("contact_name")
    listing_address = parsed.get("listing_address")
    details = parsed.get("details", "")
    time_ref = parsed.get("time_reference")

    # Route to handler
    if cmd_type == "listing_update":
        return _handle_listing_command(event, agent, body, parsed)
    elif cmd_type == "client_instruction":
        return _handle_client_instruction(event, agent, contact_name, details, parsed)
    elif cmd_type == "status_change":
        return _handle_status_change(event, agent, contact_name, time_ref, body)
    elif cmd_type == "query_gap":
        return _handle_gap_query(agent)
    elif cmd_type == "query_contact":
        return _handle_contact_query(agent, contact_name)
    elif cmd_type == "query_schedule":
        return _handle_schedule_query(agent)
    elif cmd_type == "query_listing":
        return _handle_listing_query(agent, listing_address)
    elif cmd_type == "broadcast":
        return _handle_broadcast(agent, listing_address)
    elif cmd_type == "trigger":
        return _handle_trigger_command(agent, contact_name, time_ref, details)
    elif cmd_type == "cascade":
        return _handle_cascade_command(agent, listing_address, contact_name, time_ref, details, body)
    elif cmd_type == "offer":
        return _handle_offer_command(agent, contact_name, listing_address)
    else:
        return AgentDecision(
            response_text=f"I received your message but wasn't sure what to do with it. Could you rephrase?",
            model_used="haiku",
            tokens_used=parsed.get("_tokens", 0),
        )


def _handle_listing_command(
    event: NormalizedEvent, agent: AgentConfig, body: str, parsed: dict
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
    except Exception as e:
        return AgentDecision(
            response_text=f"Couldn't process that listing: {e}",
            model_used="template",
        )


def _handle_client_instruction(
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
    except Exception:
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


def _handle_status_change(
    event: NormalizedEvent, agent: AgentConfig,
    contact_name: str | None, time_ref: str | None, body: str,
) -> AgentDecision:
    """Handle status change commands."""
    lower = body.lower()

    # "I've got Sarah" → silent mode for that contact
    if contact_name and ("got" in lower or "have" in lower or "handling" in lower):
        contact = lookup_contact(agent.id, name=contact_name)
        if contact and not isinstance(contact, list):
            update_contact(contact.id, silent_mode=True)
            return AgentDecision(
                response_text=f"Got it — stepping back on {contact.name}. I'll observe but won't message them.",
                model_used="template",
            )
        elif isinstance(contact, list):
            names = ", ".join(c.name for c in contact)
            return AgentDecision(
                response_text=f"Which one? I have: {names}",
                model_used="template",
            )

    # "I'm back" → revert to available
    if "back" in lower or "available" in lower:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE agents SET current_status = 'available', status_until = NULL WHERE id = %s",
                [str(agent.id)],
            )
            conn.commit()
        return AgentDecision(
            response_text="Welcome back! Status set to available.",
            model_used="template",
        )

    # "I'm in showings until 3" → set status + auto-revert trigger
    new_status = "in_showing"
    if "vacation" in lower:
        new_status = "vacation"
    elif "after hours" in lower or "done for" in lower or "off" in lower:
        new_status = "after_hours"

    status_until = None
    if time_ref:
        # Parse simple time references
        try:
            from dateutil import parser as dateutil_parser
            status_until = dateutil_parser.parse(time_ref, fuzzy=True)
            if status_until.tzinfo is None:
                status_until = status_until.replace(tzinfo=timezone.utc)
            # If parsed time is in the past, assume it's today at that time
            now = datetime.now(timezone.utc)
            if status_until < now:
                status_until = status_until.replace(
                    year=now.year, month=now.month, day=now.day
                )
                if status_until < now:
                    status_until += timedelta(days=1)
        except Exception:
            status_until = None

    with get_db_connection() as conn:
        conn.execute(
            "UPDATE agents SET current_status = %s, status_until = %s WHERE id = %s",
            [new_status, status_until, str(agent.id)],
        )
        conn.commit()

    response = f"Status set to '{new_status}'."
    if status_until:
        response += f" Will auto-revert at {status_until.strftime('%I:%M %p')}."
    else:
        response += " Text 'I'm back' when you're available."

    # Create triggers for auto-revert if time specified
    triggers = []
    if status_until:
        triggers.append({
            "entity_type": "agent",
            "entity_id": str(agent.id),
            "trigger_type": "status_revert",
            "scheduled_at": status_until.isoformat(),
            "action_type": "notify_agent",
        })

    return AgentDecision(
        response_text=response,
        triggers_to_create=triggers,
        model_used="template",
    )


def _handle_gap_query(agent: AgentConfig) -> AgentDecision:
    """Handle 'Who needs follow-up?' queries."""
    gaps = analyze_contact_gaps(agent.id)

    if not gaps:
        return AgentDecision(
            response_text="All caught up! No contacts need attention right now.",
            model_used="template",
        )

    lines = [f"{len(gaps)} client(s) need attention:"]
    for g in gaps[:5]:
        c = g["contact"]
        lines.append(
            f"- {c.name} ({g['lifecycle_stage']}, {g['days_since_contact']}d, {g['suggested_action'].lower()})"
        )
    if len(gaps) > 5:
        lines.append(f"...and {len(gaps) - 5} more")

    return AgentDecision(
        response_text="\n".join(lines),
        model_used="template",
    )


def _handle_contact_query(agent: AgentConfig, contact_name: str | None) -> AgentDecision:
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


def _handle_schedule_query(agent: AgentConfig) -> AgentDecision:
    """Handle 'What's my day look like?' queries."""
    with get_db_connection() as conn:
        showings = conn.execute(
            """SELECT s.*, c.name as contact_name, l.address
               FROM showings s
               JOIN contacts c ON s.contact_id = c.id
               JOIN listings l ON s.listing_id = l.id
               WHERE s.agent_id = %s
               AND DATE(s.start_time) = CURRENT_DATE
               AND s.status IN ('confirmed', 'hold')
               ORDER BY s.start_time""",
            [str(agent.id)],
        ).fetchall()

    if not showings:
        return AgentDecision(
            response_text="No showings scheduled for today.",
            model_used="template",
        )

    lines = [f"{len(showings)} showing(s) today:"]
    for s in showings:
        time_str = s["start_time"].strftime("%I:%M %p") if s["start_time"] else "TBD"
        lines.append(f"- {time_str}: {s['contact_name']} at {s['address']} ({s['status']})")

    return AgentDecision(
        response_text="\n".join(lines),
        model_used="template",
    )


def _handle_listing_query(agent: AgentConfig, listing_address: str | None) -> AgentDecision:
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


def _handle_broadcast(agent: AgentConfig, listing_address: str | None) -> AgentDecision:
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

    # Find matching buyers
    matching = search_contacts(
        agent.id,
        lifecycle_stage="active_buyer",
    )

    if not matching:
        return AgentDecision(
            response_text="No active buyers in the system to notify.",
            model_used="template",
        )

    # Queue messages for each matching buyer
    tool_calls = []
    for contact in matching:
        tool_calls.append({
            "tool_name": "send_personalized_listing_alert",
            "input": {
                "agent_id": str(agent.id),
                "contact_id": str(contact.id),
                "listing_id": str(listing.id),
            },
        })

    return AgentDecision(
        response_text=f"Sending {listing.address} (${listing.price:,}) to {len(matching)} active buyer(s).",
        tool_calls=tool_calls,
        model_used="template",
    )


def _handle_trigger_command(
    agent: AgentConfig, contact_name: str | None,
    time_ref: str | None, details: str,
) -> AgentDecision:
    """Handle trigger creation commands."""
    if not contact_name:
        return AgentDecision(
            response_text="Who should I follow up with?",
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

    # Parse time reference
    scheduled_at = None
    if time_ref:
        try:
            from dateutil import parser as dateutil_parser
            scheduled_at = dateutil_parser.parse(time_ref, fuzzy=True)
        except Exception:
            scheduled_at = datetime.now(timezone.utc) + timedelta(days=1)

    if scheduled_at is None:
        scheduled_at = datetime.now(timezone.utc) + timedelta(days=1)

    return AgentDecision(
        response_text=f"Reminder set: follow up with {contact.name} on {scheduled_at.strftime('%A %B %d')}.",
        triggers_to_create=[{
            "entity_type": "contact",
            "entity_id": str(contact.id),
            "trigger_type": "follow_up",
            "scheduled_at": scheduled_at.isoformat(),
            "action_type": "notify_agent",
            "message_template": details or f"Follow up with {contact.name}",
            "autonomy_level": "ask_agent",
        }],
        model_used="template",
    )


def _handle_cascade_command(
    agent: AgentConfig, listing_address: str | None,
    contact_name: str | None, time_ref: str | None,
    details: str, body: str,
) -> AgentDecision:
    """Handle cascade commands (open house, transaction deadlines)."""
    lower = body.lower()

    if "open house" in lower:
        return AgentDecision(
            response_text=f"Open house cascade will be created. (Full implementation in Step 41)",
            triggers_to_create=[{
                "entity_type": "listing",
                "entity_id": listing_address or "unknown",
                "trigger_type": "open_house",
                "cascade_type": "open_house",
                "time_reference": time_ref,
                "details": details,
            }],
            model_used="template",
        )

    if "deal" in lower or "inspection" in lower or "closing" in lower:
        return AgentDecision(
            response_text=f"Transaction deadline cascade created. I'll track all milestones.",
            triggers_to_create=[{
                "entity_type": "contact",
                "entity_id": contact_name or "unknown",
                "trigger_type": "transaction_deadlines",
                "cascade_type": "transaction_deadlines",
                "time_reference": time_ref,
                "details": details,
            }],
            model_used="template",
        )

    return AgentDecision(
        response_text="I'm not sure what cascade to create. Could you clarify?",
        model_used="template",
    )


def _handle_offer_command(
    agent: AgentConfig, contact_name: str | None, listing_address: str | None,
) -> AgentDecision:
    """Handle offer preparation commands."""
    if not contact_name:
        return AgentDecision(response_text="Which client wants to make an offer?", model_used="template")

    contact = lookup_contact(agent.id, name=contact_name)
    if contact is None or isinstance(contact, list):
        return AgentDecision(response_text=f"Could you clarify the client name?", model_used="template")

    return AgentDecision(
        response_text=f"Offer prep started for {contact.name}. I'll request docs from them and notify you when ready.",
        tool_calls=[{
            "tool_name": "send_client_message",
            "input": {
                "agent_id": str(agent.id),
                "contact_id": str(contact.id),
                "message": f"Exciting! {agent.name} mentioned you're interested in making an offer. "
                           f"To get started, I'll need: (1) Current pre-approval letter (2) Proof of funds for earnest money. "
                           f"Can you send those over? {agent.name} will call you today to discuss strategy.",
            },
        }],
        notifications=[{
            "tier": "action_needed",
            "title": f"Offer prep: {contact.name}",
            "body": f"{contact.name} wants to offer{' on ' + listing_address if listing_address else ''}. Docs requested. Call them to discuss strategy.",
        }],
        model_used="template",
    )


# ============================================================
# Step 20: Full Agent Reasoner (Sonnet with tools)
# ============================================================

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
        logger.error(f"Tool execution error ({tool_name}): {e}")
        return {"error": str(e)}


def handle_full_reasoning(
    event: NormalizedEvent,
    contact: Contact | None,
    context: AssembledContext,
    agent: AgentConfig,
) -> AgentDecision:
    """Full reasoning with Claude Sonnet and tools."""
    client = get_anthropic_client()

    # Build system prompt
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=agent.name,
        brokerage=agent.brokerage or "their brokerage",
        market=agent.market or "their market",
        tone=agent.style_profile.get("tone", "professional"),
    )

    # Add dynamic context
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

    # Build messages
    messages = []
    for msg in context.conversation_history:
        role = "user" if msg.sender_type == "client" else "assistant"
        messages.append({"role": role, "content": msg.body})
    messages.append({"role": "user", "content": event.body})

    # Tool executor
    def executor(name, inp):
        return _execute_tool(name, inp, agent.id)

    decision = client.reason(
        system_prompt, messages, TOOL_DEFINITIONS, agent.id,
        tool_executor=executor,
    )

    return decision


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


# ============================================================
# Step 15: Listing Q&A Handler (Lightweight, Haiku)
# ============================================================

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
        tokens_used=0,  # tracked by the compose call internally
    )


# ============================================================
# Step 21: Template Responder (Zero LLM)
# ============================================================

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
