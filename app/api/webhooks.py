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
    from app.pipeline.consent import check_tcpa_keywords
    from app.pipeline.rate_limiter import check_rate_limits
    from app.services.agent_config import get_agent_by_id
    from app.services.twilio_service import send_sms
    from app.db.connection import get_db_connection

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

        # 2A. TCPA keyword check (STOP/HELP/START) — before any pipeline processing
        if not is_agent_command:
            tcpa_result = check_tcpa_keywords(event, contact, agent)
            if tcpa_result:
                if tcpa_result.get("response_text"):
                    send_sms(
                        to=event.sender_phone, from_=agent.twilio_number,
                        body=tcpa_result["response_text"], agent_id=agent.id,
                    )
                if tcpa_result.get("notify_agent") and tcpa_result.get("notification"):
                    try:
                        from app.services.firebase_service import send_push_notification
                        n = tcpa_result["notification"]
                        send_push_notification(agent.id, n["tier"], n["title"], n["body"])
                    except Exception:
                        pass
                return

        # 2B. Rate limiting check
        if not is_agent_command:
            rate_result = check_rate_limits(event, contact, agent)
            if rate_result:
                if rate_result.get("response_text"):
                    send_sms(
                        to=event.sender_phone, from_=agent.twilio_number,
                        body=rate_result["response_text"], agent_id=agent.id,
                    )
                return

        # 2C. Consent gate — block messages from contacts with revoked consent
        if contact and not is_agent_command and contact.consent_status == "revoked":
            logger.info(f"Blocked message from revoked contact {contact.name}")
            return

        # 3. Classify intent
        intent = classify_intent(event, contact, agent, is_agent_command)

        # 3A. Handle feedback intent (Step 23A)
        if intent.intent == "feedback":
            _log_feedback(event, contact, agent)
            return

        # 4. Route and handle
        decision = route_and_handle(event, contact, intent, agent)

        # 5. Dispatch (consent check is inside dispatcher)
        dispatch(decision, event, contact, agent, is_agent_command)

        logger.info(f"Processed message: intent={intent.intent}, model={decision.model_used}")

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)


def _log_feedback(event, contact, agent):
    """Log client feedback score without sending a response (Step 23A)."""
    from app.db.connection import get_db_connection

    body = event.body.strip()
    score = 1 if body == "1" else (0 if body == "2" else None)
    if score is not None and contact:
        try:
            with get_db_connection() as conn:
                conn.execute(
                    """UPDATE messages SET feedback_score = %s
                       WHERE conversation_id IN (
                           SELECT id FROM conversations
                           WHERE contact_id = %s AND agent_id = %s
                       )
                       AND ai_generated = true
                       ORDER BY created_at DESC LIMIT 1""",
                    [score, str(contact.id), str(agent.id)],
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log feedback: {e}")
        logger.info(f"Feedback logged from {contact.name}: score={score}")


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


@router.post("/twilio/voice")
async def twilio_voice(request: Request):
    """Handle inbound voice calls. Forward to Vapi after 4 rings."""
    form_data = await request.form()
    payload = dict(form_data)

    to_number = payload.get("To", "")
    agent = get_agent_by_twilio_number(to_number)

    if not agent:
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Sorry, this number is not configured.</Say></Response>'
        return Response(content=twiml, media_type="application/xml")

    # Check if agent has a Vapi assistant
    vapi_number = agent.vapi_assistant or ""

    # Forward to Vapi after timeout (20 seconds / ~4 rings)
    twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial timeout="20" action="/webhooks/twilio/voice-fallback">
        <Number>{agent.phone}</Number>
    </Dial>
</Response>'''

    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/voice-fallback")
async def twilio_voice_fallback(request: Request):
    """If agent doesn't answer, forward to Vapi."""
    form_data = await request.form()
    payload = dict(form_data)
    dial_status = payload.get("DialCallStatus", "no-answer")

    if dial_status in ("no-answer", "busy", "failed"):
        # Forward to Vapi — in production, this would be the Vapi SIP/number
        twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Please hold while I connect you with our office assistant.</Say>
    <Pause length="1"/>
    <Say>Hi, thanks for calling! I'm the digital assistant. How can I help you today?</Say>
</Response>'''
    else:
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

    return Response(content=twiml, media_type="application/xml")


@router.post("/vapi/post-call")
async def vapi_post_call(request: Request, background_tasks: BackgroundTasks):
    """Process Vapi post-call transcript."""
    payload = await request.json()
    logger.info(f"Vapi post-call received: {payload.get('call_id', 'unknown')}")

    background_tasks.add_task(process_vapi_transcript, payload)
    return {"status": "ok"}


async def process_vapi_transcript(payload: dict):
    """Process a Vapi call transcript through the pipeline."""
    from uuid import UUID
    from app.pipeline.normalizer import normalize_vapi_event
    from app.pipeline.resolver import resolve_contact
    from app.pipeline.classifier import classify_intent
    from app.pipeline.router import route_and_handle
    from app.pipeline.dispatcher import dispatch
    from app.services.agent_config import get_agent_by_id
    from app.tools.contacts import create_contact
    from app.db.connection import get_db_connection
    from decimal import Decimal

    try:
        # Determine agent from call metadata
        agent_phone = payload.get("phoneNumber", {}).get("number", "")
        agent = get_agent_by_twilio_number(agent_phone)
        if not agent:
            # Try to get from assistant ID
            logger.warning("Could not resolve agent from Vapi payload")
            return

        event = normalize_vapi_event(payload, agent.id)
        contact, is_agent = resolve_contact(event, agent)

        # Create contact if new caller
        if not contact and event.sender_phone:
            contact = create_contact(
                agent.id,
                name=f"Caller {event.sender_phone[-4:]}",
                phone=event.sender_phone,
                role="lead",
                lifecycle_stage="new_lead",
                lead_source="voice",
            )

        # Classify and route
        intent = classify_intent(event, contact, agent)
        decision = route_and_handle(event, contact, intent, agent)

        # Send push notification to agent with call summary
        call_duration = payload.get("duration", 0)
        transcript = event.body[:200]

        decision.notifications.append({
            "tier": "action_needed",
            "title": f"Call from {contact.name if contact else 'Unknown'}",
            "body": f"Duration: {call_duration}s. Summary: {transcript}",
            "contact_id": str(contact.id) if contact else None,
        })

        # Update voice minutes in usage metrics
        voice_mins = Decimal(str(call_duration / 60)) if call_duration else Decimal("0")
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO usage_metrics (agent_id, date, voice_minutes)
                   VALUES (%s, CURRENT_DATE, %s)
                   ON CONFLICT (agent_id, date)
                   DO UPDATE SET voice_minutes = usage_metrics.voice_minutes + %s""",
                [str(agent.id), voice_mins, voice_mins],
            )
            conn.commit()

        dispatch(decision, event, contact, agent)

        # Send RCS follow-up to caller
        if contact and decision.response_text:
            from app.services.twilio_service import send_client_message
            send_client_message(
                agent.id, contact.id,
                f"Thanks for calling {agent.name}'s office! "
                f"Here's a summary of what we discussed: {transcript[:100]}. "
                f"We'll follow up soon.",
                agent.twilio_number, contact.phone,
            )

        logger.info(f"Processed Vapi call: {payload.get('call_id')}")

    except Exception as e:
        logger.error(f"Vapi processing error: {e}", exc_info=True)


@router.post("/email/inbound")
async def email_inbound(request: Request, background_tasks: BackgroundTasks):
    """Receives inbound email via SendGrid Inbound Parse webhook."""
    form_data = await request.form()
    payload = dict(form_data)

    to_address = payload.get("to", "")
    agent = _resolve_agent_from_email(to_address)
    if agent is None:
        logger.warning("No agent found for email address: %s", to_address)
        return {"status": "no_agent"}

    background_tasks.add_task(process_inbound_email, str(agent.id), payload)
    return {"status": "ok"}


def _resolve_agent_from_email(to_address: str):
    """Find the agent whose email matches the To address."""
    from app.db.connection import get_db_connection
    from app.services.agent_config import get_agent_by_id
    from uuid import UUID

    email = to_address
    if "<" in to_address:
        email = to_address.split("<")[1].rstrip(">").strip()

    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT id FROM agents WHERE email = %s",
                [email],
            ).fetchone()
        if row:
            return get_agent_by_id(UUID(str(row["id"])))
    except Exception as e:
        logger.error("Agent email lookup failed: %s", e)
    return None


async def process_inbound_email(agent_id: str, payload: dict):
    """Process an inbound email through the full pipeline."""
    from uuid import UUID
    from app.pipeline.normalizer import normalize_email_event
    from app.pipeline.resolver import resolve_contact
    from app.pipeline.classifier import classify_intent
    from app.pipeline.router import route_and_handle
    from app.pipeline.dispatcher import dispatch
    from app.services.agent_config import get_agent_by_id
    from app.services.email_service import parse_inbound_email, _extract_email
    from app.tools.contacts import create_contact
    from app.db.connection import get_db_connection

    try:
        aid = UUID(agent_id)
        agent = get_agent_by_id(aid)
        if not agent:
            logger.error("Agent %s not found", agent_id)
            return

        parsed = parse_inbound_email(payload)
        event = normalize_email_event(payload, aid)

        # Archive email
        try:
            with get_db_connection() as conn:
                conn.execute(
                    """INSERT INTO emails (agent_id, from_address, to_address, subject, body)
                       VALUES (%s, %s, %s, %s, %s)""",
                    [agent_id, parsed["from_address"], parsed["to_address"],
                     parsed["subject"], parsed["text"]],
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to archive email: %s", e)

        # Resolve contact
        contact, is_agent_command = resolve_contact(event, agent)

        # Auto-create contact for unknown email senders
        if not contact and not is_agent_command and parsed["from_address"]:
            sender_email = _extract_email(parsed["from_address"])
            sender_name = parsed["from_name"] or sender_email.split("@")[0]
            contact = create_contact(
                agent_id=aid,
                name=sender_name,
                phone=sender_email,
                email=sender_email,
                role="lead",
                lifecycle_stage="new_lead",
                lead_source="email",
            )
            logger.info("Auto-created contact from email: %s", sender_name)

        # Classify and route
        intent = classify_intent(event, contact, agent)
        decision = route_and_handle(event, contact, intent, agent)

        # Dispatch
        dispatch(decision, event, contact, agent, is_agent_command)

        logger.info("Processed email: from=%s intent=%s model=%s",
                     parsed["from_address"], intent.intent, decision.model_used)

    except Exception as e:
        logger.error("Email pipeline error: %s", e, exc_info=True)
