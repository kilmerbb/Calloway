"""Response dispatcher — sends AI response via correct channel."""
import logging
import threading
from datetime import date
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import (
    NormalizedEvent, Contact, AgentConfig, AgentDecision,
)
from app.services.twilio_service import send_client_message, send_sms

logger = logging.getLogger(__name__)

# Cost in cents per 1M tokens
MODEL_COST_MAP = {
    "haiku": {"input": 100, "output": 500},
    "sonnet": {"input": 300, "output": 1500},
    "template": {"input": 0, "output": 0},
}


def dispatch(
    decision: AgentDecision,
    event: NormalizedEvent,
    contact: Contact | None,
    agent: AgentConfig,
    is_agent_command: bool = False,
) -> None:
    """
    Send the AI response via the correct channel and log everything.
    """
    # 0. CONSENT GATE — NEVER send to a contact with revoked consent
    if contact and not is_agent_command:
        from app.pipeline.consent import check_consent_before_send
        if not check_consent_before_send(contact):
            logger.warning(
                f"Blocked outbound message to {contact.name} — consent not granted "
                f"(status: {contact.consent_status})"
            )
            # Still log the interaction, but don't send
            _log_conversation(event, decision, contact, agent, is_agent_command)
            _update_usage_metrics(agent.id, event, decision, is_agent_command)
            return

    # 1. Send response text
    if decision.response_text:
        # Step 23A: Feedback pulse — every 10th substantive AI response
        if (
            contact
            and not is_agent_command
            and decision.model_used not in ("template", None)
        ):
            decision.response_text = _maybe_append_feedback_prompt(
                decision.response_text, contact, agent
            )

        if is_agent_command:
            # Reply to agent via SMS
            send_sms(
                to=agent.phone,
                from_=agent.twilio_number,
                body=decision.response_text,
                agent_id=agent.id,
            )
        elif contact and event.channel == "email" and contact.email:
            # Send to client via email
            from app.services.email_service import send_client_email
            send_client_email(
                agent_id=agent.id,
                contact_id=contact.id,
                message=decision.response_text,
                from_email=agent.email,
                to_email=contact.email,
            )
        elif contact:
            # Send to client via RCS/SMS
            send_client_message(
                agent_id=agent.id,
                contact_id=contact.id,
                message=decision.response_text,
                from_number=agent.twilio_number,
                to_number=contact.phone,
            )

    # 2. Send push notifications
    if decision.notifications:
        for notif in decision.notifications:
            _send_notification(agent, notif, contact)

    # 3. Create triggers
    if decision.triggers_to_create:
        for trigger_data in decision.triggers_to_create:
            _create_trigger(agent.id, trigger_data)

    # 4. Execute queued tool calls
    if decision.tool_calls:
        for tc in decision.tool_calls:
            _execute_queued_tool(agent, tc, contact)

    # 5. Log conversation
    _log_conversation(event, decision, contact, agent, is_agent_command)

    # 6. Update usage metrics
    _update_usage_metrics(agent.id, event, decision, is_agent_command)

    # 7. Trigger conversation summarization in background thread
    if contact and not is_agent_command:
        thread = threading.Thread(
            target=_background_summarize,
            args=(agent.id, contact.id),
            daemon=True,
        )
        thread.start()


def _send_notification(agent: AgentConfig, notif: dict, contact: Contact | None):
    """Send a push notification to the agent."""
    try:
        from app.services.firebase_service import send_push_notification
        send_push_notification(
            agent_id=agent.id,
            tier=notif.get("tier", "informational"),
            title=notif.get("title", "Notification"),
            body=notif.get("body", ""),
            contact_id=contact.id if contact else None,
        )
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


def _create_trigger(agent_id: UUID, trigger_data: dict):
    """Create a trigger in the database."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO triggers (agent_id, entity_type, entity_id, trigger_type,
                    scheduled_at, action_type, message_template, autonomy_level)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    str(agent_id),
                    trigger_data.get("entity_type", "contact"),
                    trigger_data.get("entity_id"),
                    trigger_data.get("trigger_type", "custom"),
                    trigger_data.get("scheduled_at"),
                    trigger_data.get("action_type", "notify_agent"),
                    trigger_data.get("message_template"),
                    trigger_data.get("autonomy_level", "ask_agent"),
                ],
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to create trigger: {e}")


def _execute_queued_tool(agent: AgentConfig, tool_call: dict, contact: Contact | None):
    """Execute a tool call that was queued in the decision."""
    tool_name = tool_call.get("tool_name")
    tool_input = tool_call.get("input", {})

    if tool_name == "send_client_message" and contact:
        send_client_message(
            agent_id=agent.id,
            contact_id=UUID(tool_input.get("contact_id", str(contact.id))),
            message=tool_input.get("message", ""),
            from_number=agent.twilio_number,
            to_number=contact.phone,
        )
    elif tool_name == "send_personalized_listing_alert":
        # Will be fully implemented with broadcast feature
        logger.info(f"Queued listing alert for contact {tool_input.get('contact_id')}")


def _log_conversation(
    event: NormalizedEvent,
    decision: AgentDecision,
    contact: Contact | None,
    agent: AgentConfig,
    is_agent_command: bool,
):
    """Log the conversation to the database."""
    try:
        with get_db_connection() as conn:
            # Get or create conversation
            if contact:
                conv = conn.execute(
                    """SELECT id FROM conversations
                       WHERE agent_id = %s AND contact_id = %s
                       ORDER BY created_at DESC LIMIT 1""",
                    [str(agent.id), str(contact.id)],
                ).fetchone()
            else:
                conv = None

            if conv:
                conv_id = conv["id"]
                conn.execute(
                    "UPDATE conversations SET last_message_at = now() WHERE id = %s",
                    [str(conv_id)],
                )
            else:
                channel = "sms_command" if is_agent_command else event.channel
                result = conn.execute(
                    """INSERT INTO conversations (agent_id, contact_id, channel, last_message_at)
                       VALUES (%s, %s, %s, now()) RETURNING id""",
                    [str(agent.id), str(contact.id) if contact else None, channel],
                ).fetchone()
                conv_id = result["id"]

            # Log inbound message
            sender = "agent_command" if is_agent_command else "client"
            conn.execute(
                """INSERT INTO messages (agent_id, conversation_id, sender_type, body, intent)
                   VALUES (%s, %s, %s, %s, %s)""",
                [str(agent.id), str(conv_id), sender, event.body, None],
            )

            # Log outbound response
            if decision.response_text:
                conn.execute(
                    """INSERT INTO messages (agent_id, conversation_id, sender_type, body,
                        ai_generated, model_used, tokens_used)
                       VALUES (%s, %s, 'ai', %s, true, %s, %s)""",
                    [str(agent.id), str(conv_id), decision.response_text,
                     decision.model_used, decision.tokens_used],
                )

            # Update contact.last_contact_at
            if contact:
                conn.execute(
                    "UPDATE contacts SET last_contact_at = now() WHERE id = %s",
                    [str(contact.id)],
                )

            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log conversation: {e}")


def _update_usage_metrics(
    agent_id: UUID,
    event: NormalizedEvent,
    decision: AgentDecision,
    is_agent_command: bool,
):
    """Update daily usage metrics."""
    try:
        # Calculate cost
        cost_rates = MODEL_COST_MAP.get(decision.model_used, MODEL_COST_MAP["template"])
        cost_cents = int(decision.tokens_used * (cost_rates["input"] + cost_rates["output"]) / 2_000_000)

        llm_calls = 1 if decision.model_used not in ("template", None) else 0
        msg_sent = 1 if decision.response_text else 0

        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO usage_metrics (agent_id, date, messages_received, messages_sent,
                    llm_calls, llm_tokens_used, llm_cost_cents)
                   VALUES (%s, CURRENT_DATE, 1, %s, %s, %s, %s)
                   ON CONFLICT (agent_id, date)
                   DO UPDATE SET
                    messages_received = usage_metrics.messages_received + 1,
                    messages_sent = usage_metrics.messages_sent + %s,
                    llm_calls = usage_metrics.llm_calls + %s,
                    llm_tokens_used = usage_metrics.llm_tokens_used + %s,
                    llm_cost_cents = usage_metrics.llm_cost_cents + %s""",
                [str(agent_id), msg_sent, llm_calls, decision.tokens_used, cost_cents,
                 msg_sent, llm_calls, decision.tokens_used, cost_cents],
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to update usage metrics: {e}")


FEEDBACK_INTERVAL = 10  # Append feedback prompt every N substantive responses


def _maybe_append_feedback_prompt(
    response_text: str, contact: Contact, agent: AgentConfig
) -> str:
    """
    Step 23A: Every FEEDBACK_INTERVAL-th substantive AI response,
    append a feedback pulse question.
    """
    try:
        with get_db_connection() as conn:
            # Increment interaction_count and return new value
            row = conn.execute(
                """UPDATE contacts SET interaction_count = interaction_count + 1
                   WHERE id = %s RETURNING interaction_count""",
                [str(contact.id)],
            ).fetchone()
            conn.commit()

        count = row["interaction_count"] if row else 0
        if count > 0 and count % FEEDBACK_INTERVAL == 0:
            response_text += (
                "\n\nPS — Was this helpful? Tap 1 for yes, 2 for not really."
            )
    except Exception as e:
        logger.debug(f"Feedback pulse check skipped: {e}")

    return response_text


def _background_summarize(agent_id: UUID, contact_id: UUID) -> None:
    """Run summarization in a background daemon thread with Redis dedup lock."""
    from app.services.redis_pool import get_redis_pool

    lock_key = f"summarize:{contact_id}"
    r = get_redis_pool()

    # Acquire dedup lock (SET NX EX) — skip if another summarization is running
    if not r.set(lock_key, "1", nx=True, ex=30):
        logger.debug(
            f"Skipping summarization for contact {contact_id} — "
            "another summarization is in progress"
        )
        return

    try:
        _maybe_summarize_conversation(agent_id, contact_id)
    except Exception:
        logger.exception("Background summarization failed")
    finally:
        r.delete(lock_key)


def _maybe_summarize_conversation(agent_id: UUID, contact_id: UUID) -> None:
    """Check if conversation needs summarization and generate/update if so.

    Called from a background daemon thread — never blocks the dispatch hot path.
    If it fails, the error is logged and the next request falls back to
    recent-messages-only context.
    """
    try:
        from app.services.summarization_service import (
            should_summarize,
            generate_or_update_summary,
        )

        if should_summarize(agent_id, contact_id):
            summary = generate_or_update_summary(agent_id, contact_id)
            if summary:
                logger.info(
                    f"Conversation summary updated for contact {contact_id}: "
                    f"{summary.messages_summarized_count} msgs summarized"
                )
    except Exception as e:
        # Non-fatal — assembler will fall back to recent messages only
        logger.warning(f"Conversation summarization skipped: {e}")
