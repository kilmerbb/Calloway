import logging
from fastapi import APIRouter, Request, Response, BackgroundTasks

from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.services.agent_config import get_agent_by_twilio_number

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def validate_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    """Validate that a request genuinely came from Twilio."""
    settings = get_settings()
    if settings.ENVIRONMENT == "development" and not settings.TWILIO_AUTH_TOKEN:
        return True  # Skip validation in dev without credentials
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    return validator.validate(request_url, params, signature)


async def process_inbound_message(agent_id: str, payload: dict):
    """Process an inbound message through the full pipeline."""
    from uuid import UUID
    from app.pipeline.normalizer import normalize_twilio_event
    from app.pipeline.resolver import resolve_contact
    from app.pipeline.classifier import classify_intent
    from app.pipeline.router import route_and_handle
    from app.pipeline.dispatcher import dispatch
    from app.services.agent_config import get_agent_by_id

    try:
        aid = UUID(agent_id)
        agent = get_agent_by_id(aid)
        if not agent:
            logger.error(f"Agent {agent_id} not found")
            return

        # 1. Normalize
        event = normalize_twilio_event(payload, aid)

        # 2. Resolve contact
        contact, is_agent_command = resolve_contact(event, agent)

        # 3. Classify intent
        intent = classify_intent(event, contact, agent, is_agent_command)

        # 4. Route and handle
        decision = route_and_handle(event, contact, intent, agent)

        # 5. Dispatch
        dispatch(decision, event, contact, agent, is_agent_command)

        logger.info(f"Processed message: intent={intent.intent}, model={decision.model_used}")

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)


@router.post("/twilio/inbound")
async def twilio_inbound(request: Request, background_tasks: BackgroundTasks):
    """Receives inbound SMS/RCS messages from Twilio."""
    form_data = await request.form()
    payload = dict(form_data)

    # Validate Twilio signature
    signature = request.headers.get("X-Twilio-Signature", "")
    request_url = str(request.url)
    if not validate_twilio_signature(request_url, payload, signature):
        logger.warning("Invalid Twilio signature rejected")
        return Response(status_code=403)

    # Resolve agent from the receiving Twilio number
    to_number = payload.get("To", "")
    agent = get_agent_by_twilio_number(to_number)
    if agent is None:
        logger.error(f"No agent found for Twilio number: {to_number}")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
            status_code=200,
        )

    # Enqueue for async processing and return 200 immediately
    background_tasks.add_task(process_inbound_message, str(agent.id), payload)

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
        status_code=200,
    )


@router.post("/twilio/status")
async def twilio_status(request: Request):
    """Receives delivery status updates from Twilio."""
    form_data = await request.form()
    payload = dict(form_data)

    message_sid = payload.get("MessageSid", "")
    status = payload.get("MessageStatus", "")
    logger.info(f"Message {message_sid} status: {status}")

    # TODO: Update message delivery status in messages table

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
        status_code=200,
    )


@router.post("/vapi/post-call")
async def vapi_post_call(request: Request):
    """Receives Vapi post-call transcript. Implemented in Step 28."""
    return {"status": "ok"}


@router.post("/email/inbound")
async def email_inbound(request: Request):
    """Receives BCC'd email. Implemented later."""
    return {"status": "ok"}
