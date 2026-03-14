"""Vapi voice agent configuration and management."""
import json
import logging
from uuid import UUID

import httpx

from app.config import get_settings
from app.models.schemas import AgentConfig
from app.tools.listings import search_listings
from app.services.google_service import check_availability

logger = logging.getLogger(__name__)

VAPI_BASE_URL = "https://api.vapi.ai"

VOICE_SYSTEM_PROMPT = """You are the AI receptionist for {agent_name}'s real estate office at {brokerage} in {market}.

{agent_name} isn't available right now but you can help with:
- Property information and listing details
- Scheduling showings
- Taking detailed messages

Be warm, professional, and helpful. Keep responses concise (this is a phone call).

LISTINGS:
{listings_text}

AVAILABILITY:
{availability_text}

KEY RULES:
- Never provide legal, financial, or investment advice
- Never discuss pricing strategy or negotiation
- If asked about offers or complex topics: "I'll make sure {agent_name} gets back to you about that today."
- Ask if the caller has a buyer's agent
- If they don't, note that and let {agent_name} know (potential dual agency)

If asked "Is this AI?": "Yes, I'm {agent_name}'s digital assistant. I can help with property info and scheduling, or I can take a message for {agent_name} to call you back."

At the end of each call: confirm you have their name and number, summarize any actions, and assure them someone will follow up."""


def configure_vapi_assistant(agent: AgentConfig) -> dict:
    """Configure a Vapi voice assistant with agent's data."""
    settings = get_settings()

    # Build listings text
    listings = search_listings(agent.id, filters={"status": "active"})
    listings_text = "\n".join(
        f"- {l.address}: ${l.price:,}, {l.beds}bd/{l.baths}ba, {', '.join(l.features[:3])}"
        for l in listings
    ) or "No active listings currently."

    # Build availability text
    from datetime import date, timedelta
    availability_parts = []
    for i in range(7):
        d = date.today() + timedelta(days=i)
        avail = check_availability(agent, d)
        slot_count = len(avail.get("available_slots", []))
        if slot_count:
            availability_parts.append(f"- {d.strftime('%A %b %d')}: {slot_count} slots available")
    availability_text = "\n".join(availability_parts) or "Contact office for availability."

    system_prompt = VOICE_SYSTEM_PROMPT.format(
        agent_name=agent.name,
        brokerage=agent.brokerage or "their brokerage",
        market=agent.market or "their market",
        listings_text=listings_text,
        availability_text=availability_text,
    )

    assistant_config = {
        "name": f"{agent.name} Receptionist",
        "model": {
            "provider": "anthropic",
            "model": "claude-3-5-haiku-20241022",
            "systemPrompt": system_prompt,
        },
        "firstMessage": f"Hi, thanks for calling {agent.name}'s office! "
                        f"{agent.name} isn't available right now but I can help "
                        f"with property information, scheduling, or take a message. "
                        f"How can I help you?",
        "transcriber": {"provider": "deepgram", "model": "nova-2"},
        "voice": {"provider": "11labs", "voiceId": "21m00Tcm4TlvDq8ikWAM"},
        "serverUrl": f"{settings.SUPABASE_URL.replace('supabase.co', 'railway.app')}/webhooks/vapi/post-call",
    }

    # Create or update Vapi assistant
    if agent.vapi_assistant:
        return _update_assistant(settings.VAPI_API_KEY, agent.vapi_assistant, assistant_config)
    else:
        return _create_assistant(settings.VAPI_API_KEY, assistant_config, agent.id)


def update_vapi_context(agent: AgentConfig) -> dict:
    """Refresh listing data and calendar in Vapi assistant."""
    return configure_vapi_assistant(agent)


def _create_assistant(api_key: str, config: dict, agent_id: UUID) -> dict:
    """Create a new Vapi assistant."""
    try:
        response = httpx.post(
            f"{VAPI_BASE_URL}/assistant",
            headers={"Authorization": f"Bearer {api_key}"},
            json=config,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        # Store assistant ID in agents table
        from app.db.connection import get_db_connection
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE agents SET vapi_assistant = %s WHERE id = %s",
                [result.get("id"), str(agent_id)],
            )
            conn.commit()

        logger.info(f"Created Vapi assistant: {result.get('id')}")
        return result
    except Exception as e:  # Broad catch: Vapi HTTP API + DB call
        logger.error(f"Failed to create Vapi assistant: {e}")
        return {"error": str(e)}


def _update_assistant(api_key: str, assistant_id: str, config: dict) -> dict:
    """Update an existing Vapi assistant."""
    try:
        response = httpx.patch(
            f"{VAPI_BASE_URL}/assistant/{assistant_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            json=config,
            timeout=30,
        )
        response.raise_for_status()
        logger.info(f"Updated Vapi assistant: {assistant_id}")
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to update Vapi assistant: {e}")
        return {"error": str(e)}
