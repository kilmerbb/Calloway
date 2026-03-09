"""Intent classification using Claude Haiku."""
import logging
from uuid import UUID

from app.models.schemas import NormalizedEvent, Contact, AgentConfig, IntentClassification
from app.services.anthropic_service import get_anthropic_client

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Classify this message's intent and sender type.

Return JSON with these exact fields:
{
  "intent": one of: "scheduling", "listing_qa", "lead_qualification", "agent_command", "transaction", "personal", "escalation", "noise",
  "confidence": float 0-1,
  "needs_full_context": boolean
}

Intent definitions:
- scheduling: wants to schedule, reschedule, or cancel a showing/meeting
- listing_qa: asking about a specific property (price, features, HOA, availability)
- lead_qualification: new inquiry, expressing interest in buying/selling, budget/timeline questions
- agent_command: instruction from the agent to the AI (only if sender is agent)
- transaction: about an active deal (inspection, appraisal, closing, documents)
- personal: casual chat, thanks, greetings with no action needed
- escalation: asking about offers, pricing strategy, legal matters, expressing frustration, wanting to talk to the agent
- noise: spam, wrong number, unintelligible

needs_full_context rules:
- true for: scheduling, lead_qualification, transaction, escalation
- false for: listing_qa, noise, personal

Return ONLY valid JSON, no other text."""


KEYWORD_FALLBACK = {
    "schedule": "scheduling",
    "showing": "scheduling",
    "see": "scheduling",
    "tour": "scheduling",
    "visit": "scheduling",
    "appointment": "scheduling",
    "price": "listing_qa",
    "hoa": "listing_qa",
    "beds": "listing_qa",
    "bath": "listing_qa",
    "sqft": "listing_qa",
    "garage": "listing_qa",
    "available": "listing_qa",
    "still on": "listing_qa",
    "offer": "escalation",
    "frustrated": "escalation",
    "speak to": "escalation",
    "talk to": "escalation",
    "agent": "escalation",
    "inspection": "transaction",
    "appraisal": "transaction",
    "closing": "transaction",
    "deadline": "transaction",
    "financing": "transaction",
    "looking to buy": "lead_qualification",
    "pre-approved": "lead_qualification",
    "budget": "lead_qualification",
    "thanks": "personal",
    "thank you": "personal",
    "ok": "personal",
    "sounds good": "personal",
}


def _keyword_classify(body: str) -> str:
    """Fallback classification using keyword matching."""
    lower = body.lower()
    for keyword, intent in KEYWORD_FALLBACK.items():
        if keyword in lower:
            return intent
    return "personal"


def classify_intent(
    event: NormalizedEvent,
    contact: Contact | None,
    agent: AgentConfig,
    is_agent_command: bool = False,
) -> IntentClassification:
    """
    Classify the intent of an inbound message.
    Agent commands are detected without LLM call.
    """
    # Agent commands skip LLM classification
    if is_agent_command:
        return IntentClassification(
            intent="agent_command",
            sender_type="agent_command",
            confidence=1.0,
            needs_full_context=True,
        )

    # Determine sender type
    if contact:
        if contact.role in ("buyer_agent", "seller_agent"):
            sender_type = "known_agent"
        else:
            sender_type = "known_client"
    else:
        # Check if message mentions a listing/property
        body_lower = event.body.lower()
        listing_indicators = ["listing", "property", "house", "home", "address",
                              "oak", "elm", "front", "available", "showing"]
        if any(word in body_lower for word in listing_indicators):
            sender_type = "unknown_listing_inquiry"
        else:
            sender_type = "unknown_general"

    # Try LLM classification
    try:
        client = get_anthropic_client()
        sender_desc = f"known client ({contact.name}, {contact.lifecycle_stage})" if contact else sender_type
        message = f"Sender: {sender_desc}\nMessage: {event.body}"

        result = client.classify(CLASSIFY_PROMPT, message, event.agent_id)

        intent = result.get("intent", "personal")
        confidence = result.get("confidence", 0.5)
        needs_full_context = result.get("needs_full_context", True)

        # Validate intent is in allowed set
        valid_intents = {"scheduling", "listing_qa", "lead_qualification",
                         "agent_command", "transaction", "personal", "escalation", "noise"}
        if intent not in valid_intents:
            intent = _keyword_classify(event.body)
            confidence = 0.5

        return IntentClassification(
            intent=intent,
            sender_type=sender_type,
            confidence=confidence,
            needs_full_context=needs_full_context,
        )

    except Exception as e:
        logger.warning(f"LLM classification failed, using keyword fallback: {e}")
        intent = _keyword_classify(event.body)
        return IntentClassification(
            intent=intent,
            sender_type=sender_type,
            confidence=0.4,
            needs_full_context=intent in ("scheduling", "lead_qualification", "transaction", "escalation"),
        )
