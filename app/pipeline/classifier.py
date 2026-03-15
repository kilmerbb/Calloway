"""Intent classification using Claude Haiku."""
import logging
from uuid import UUID

from app.models.schemas import NormalizedEvent, Contact, AgentConfig, IntentClassification
from app.services.anthropic_service import get_anthropic_client

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Classify this message's intent, sender type, and language.

Return JSON with these exact fields:
{
  "intent": one of: "scheduling", "listing_qa", "lead_qualification", "agent_command", "transaction", "personal", "escalation", "noise", "feedback",
  "confidence": float 0-1,
  "needs_full_context": boolean,
  "language_code": ISO 639-1 code (e.g., "en", "es", "ko", "zh")
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
- feedback: a standalone "1" or "2" response (client feedback score)

needs_full_context rules:
- true for: scheduling, lead_qualification, transaction, escalation
- false for: listing_qa, noise, personal, feedback

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

    # Check for feedback response (standalone "1" or "2")
    stripped = event.body.strip()
    if stripped in ("1", "2") and contact:
        return IntentClassification(
            intent="feedback",
            sender_type=sender_type,
            confidence=1.0,
            needs_full_context=False,
            language_code=contact.language_detected if contact else "en",
        )

    # Try LLM classification
    try:
        client = get_anthropic_client()
        sender_desc = f"known client ({contact.name}, {contact.lifecycle_stage})" if contact else sender_type
        message = f"Sender: {sender_desc}\nMessage: {event.body}"

        result = client.classify(CLASSIFY_PROMPT, message, event.agent_id)

        intent = result.get("intent", "personal")
        confidence = result.get("confidence", 0.5)
        needs_full_context = result.get("needs_full_context", True)
        language_code = result.get("language_code", "en")

        # Validate intent is in allowed set
        valid_intents = {"scheduling", "listing_qa", "lead_qualification",
                         "agent_command", "transaction", "personal", "escalation",
                         "noise", "feedback"}
        if intent not in valid_intents:
            intent = _keyword_classify(event.body)
            confidence = 0.5

        # Update contact language if different
        if contact and language_code != contact.language_detected:
            try:
                from app.tools.contacts import update_contact
                update_contact(agent.id, contact.id, language_detected=language_code)
            except Exception:  # Broad catch: language update is non-critical
                pass

        return IntentClassification(
            intent=intent,
            sender_type=sender_type,
            confidence=confidence,
            needs_full_context=needs_full_context,
            language_code=language_code,
        )

    except Exception as e:  # Broad catch: LLM failure must fall back to keyword classifier
        logger.warning(f"LLM classification failed, using keyword fallback: {e}")
        intent = _keyword_classify(event.body)
        return IntentClassification(
            intent=intent,
            sender_type=sender_type,
            confidence=0.4,
            needs_full_context=intent in ("scheduling", "lead_qualification", "transaction", "escalation"),
        )
