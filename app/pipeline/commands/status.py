"""Status-related command handlers: status changes and handoff returns."""

import logging
from datetime import datetime, timezone, timedelta

from app.models.schemas import NormalizedEvent, AgentConfig, AgentDecision
from app.tools.contacts import lookup_contact, update_contact
from app.tools.listings import get_listing
from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)


def handle_status_change(
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
        try:
            from dateutil import parser as dateutil_parser
            status_until = dateutil_parser.parse(time_ref, fuzzy=True)
            if status_until.tzinfo is None:
                status_until = status_until.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if status_until < now:
                status_until = status_until.replace(
                    year=now.year, month=now.month, day=now.day,
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


def handle_handoff_return(
    agent: AgentConfig, contact_name: str | None, details: str,
    listing_address: str | None, time_ref: str | None, body: str,
) -> AgentDecision:
    """Handle 'Back from [Name]' command — reactivate contact, extract commitments."""
    if not contact_name:
        return AgentDecision(
            response_text="Which client are you back from?",
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

    # Reactivate contact (silent_mode = false)
    update_contact(contact.id, silent_mode=False)

    updates_made = [f"Reactivated AI messaging for {contact.name}"]
    triggers_to_create = []

    # Parse for showing commitments
    if listing_address and time_ref:
        listing = get_listing(agent.id, address=listing_address)
        if listing:
            try:
                from dateutil import parser as dateutil_parser
                showing_time = dateutil_parser.parse(time_ref, fuzzy=True)
                triggers_to_create.append({
                    "entity_type": "contact",
                    "entity_id": str(contact.id),
                    "trigger_type": "showing_reminder",
                    "scheduled_at": showing_time.isoformat(),
                    "action_type": "both",
                    "message_template": f"Reminder: showing at {listing.address} today",
                })
                updates_made.append(f"Showing scheduled: {listing.address} at {time_ref}")
            except Exception:
                pass

    # Add notes with the details
    if details:
        existing_notes = contact.notes or ""
        timestamp = datetime.now(timezone.utc).strftime("%m/%d")
        new_notes = f"{existing_notes}\n[{timestamp}] Agent handoff: {details}".strip()
        update_contact(contact.id, notes=new_notes)
        updates_made.append("Notes updated")

    response = f"Got it. I've updated {contact.name}'s profile:\n" + "\n".join(f"- {u}" for u in updates_made)
    response += f"\nI'm back on with {contact.name}."

    return AgentDecision(
        response_text=response,
        triggers_to_create=triggers_to_create,
        model_used="template",
    )
