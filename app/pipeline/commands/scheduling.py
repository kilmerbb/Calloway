"""Scheduling-related command handlers: schedule queries, gaps, triggers, cascades."""

import logging
from datetime import datetime, timezone, timedelta

from app.models.schemas import AgentConfig, AgentDecision
from app.tools.contacts import lookup_contact, analyze_contact_gaps
from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)


def handle_gap_query(agent: AgentConfig) -> AgentDecision:
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


def handle_schedule_query(agent: AgentConfig) -> AgentDecision:
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


def handle_trigger_command(
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
            logger.debug("Failed to parse time reference '%s', defaulting to tomorrow", time_ref, exc_info=True)
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


def handle_cascade_command(
    agent: AgentConfig, listing_address: str | None,
    contact_name: str | None, time_ref: str | None,
    details: str, body: str,
) -> AgentDecision:
    """Handle cascade commands (open house, transaction deadlines)."""
    lower = body.lower()

    if "open house" in lower:
        return AgentDecision(
            response_text="Open house cascade will be created. (Full implementation in Step 41)",
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
            response_text="Transaction deadline cascade created. I'll track all milestones.",
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
