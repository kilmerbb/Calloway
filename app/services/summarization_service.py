"""Conversation summarization service.

Generates and maintains running summaries of long conversations so the
context assembler can fit meaningful history into the token budget.

Design:
- Uses Haiku for summarization (cheap, fast).
- Summaries are structured: key facts, preferences, milestones, last topics.
- Incremental: when a conversation grows past the threshold, only the *new*
  messages since the last summary are fed into a "merge" prompt that folds
  them into the existing summary.
- Graceful fallback: if summarization fails, the assembler still loads
  recent messages (the old behavior).
"""

import json
import logging
from uuid import UUID

from app.db.connection import get_db_connection

import psycopg
from app.models.schemas import ConversationSummary, Message
from app.services.anthropic_service import get_anthropic_client, HAIKU_MODEL

logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────
SUMMARIZATION_THRESHOLD = 50   # Start summarizing after this many messages
INCREMENTAL_BATCH = 30         # Re-summarize when this many new msgs accumulate
SUMMARY_TOKEN_ESTIMATE = 450   # Rough token budget for the summary block
SUMMARY_MAX_TOKENS = 800       # Max output tokens for the summarization call
FULL_RESUMMARIZE_EVERY = 5     # Force full re-summarization every N incremental cycles

# ── Time-based thresholds ──────────────────────────────────────
TIME_BASED_MESSAGE_MIN = 25    # Minimum messages for time-based trigger
TIME_BASED_SPAN_DAYS = 30      # Minimum conversation span in days

# ── Prompts ─────────────────────────────────────────────────────

INITIAL_SUMMARY_PROMPT = """\
You are summarizing a conversation between a real estate agent's AI assistant \
and a client. Extract and organize the key information.

Produce a structured summary using this EXACT format. Use "unknown" for any field \
not explicitly mentioned in the conversation. Do not invent information.

CLIENT: {name} | ROLE: {buyer/seller/both}
BUDGET: ${min}-${max} | PRE-APPROVED: {yes/no/unknown}
REQUIREMENTS: {beds}BR/{baths}BA, {areas}
MUST-HAVES: {list of non-negotiable requirements}
DEALBREAKERS: {things client has explicitly rejected or ruled out}
TIMELINE: {description of when they need to buy/sell/move}

Then include these additional sections:
- **Property Interests**: specific listings discussed, property types
- **Key Dates & Milestones**: showings, offers, deadlines, closing dates, inspections
- **Relationship Context**: how they found the agent, rapport notes, communication preferences
- **Recent Topics**: the last 2-3 subjects discussed and their status (resolved/open)
- **Open Action Items**: anything promised or pending

Be concise but thorough. This summary must fit in ~450 tokens.
"""

INCREMENTAL_SUMMARY_PROMPT = """\
You are updating an existing conversation summary with new messages. \
The existing summary captures everything up to a certain point. \
New messages have come in since then.

Merge the new information into the existing summary. Rules:
1. Keep all still-relevant facts from the existing summary.
2. Update any facts that have changed (e.g., new price preference, rescheduled showing).
3. Move resolved topics out of "Recent Topics" if they are no longer active.
4. Add new topics, dates, and action items from the new messages.
5. Preserve the key-value header format (CLIENT, BUDGET, REQUIREMENTS, MUST-HAVES, \
DEALBREAKERS, TIMELINE) and the additional sections.
6. Pay special attention to BUDGET, REQUIREMENTS, and DEALBREAKERS — these are \
critical fields that must be kept accurate. If new messages contradict prior values, \
use the LATEST stated values.
7. Stay concise — this summary must fit in ~450 tokens.

Existing summary:
{existing_summary}

New messages follow below. Produce the updated summary.
"""

FULL_RESUMMARIZE_PROMPT = """\
You are re-summarizing an ENTIRE conversation between a real estate agent's AI \
assistant and a client from scratch. A prior summary existed but may have drifted \
from accuracy over multiple incremental updates. Ignore the old summary — work \
only from the raw messages below.

Produce a structured summary using this EXACT format. Use "unknown" for any field \
not explicitly mentioned in the conversation. Do not invent information.

CLIENT: {{name}} | ROLE: {{buyer/seller/both}}
BUDGET: ${{min}}-${{max}} | PRE-APPROVED: {{yes/no/unknown}}
REQUIREMENTS: {{beds}}BR/{{baths}}BA, {{areas}}
MUST-HAVES: {{list of non-negotiable requirements}}
DEALBREAKERS: {{things client has explicitly rejected or ruled out}}
TIMELINE: {{description of when they need to buy/sell/move}}

Then include these additional sections:
- **Property Interests**: specific listings discussed, property types
- **Key Dates & Milestones**: showings, offers, deadlines, closing dates, inspections
- **Relationship Context**: how they found the agent, rapport notes, communication preferences
- **Recent Topics**: the last 2-3 subjects discussed and their status (resolved/open)
- **Open Action Items**: anything promised or pending

Be concise but thorough. This summary must fit in ~450 tokens.
"""


def get_conversation_summary(
    agent_id: UUID, contact_id: UUID
) -> ConversationSummary | None:
    """Load the most recent summary for a contact's conversation."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """SELECT cs.* FROM conversation_summaries cs
                   JOIN conversations c ON cs.conversation_id = c.id
                   WHERE cs.tenant_id = %s AND cs.contact_id = %s
                   ORDER BY cs.updated_at DESC LIMIT 1""",
                [str(agent_id), str(contact_id)],
            ).fetchone()
        if row:
            return ConversationSummary(**row)
        return None
    except psycopg.Error as e:
        logger.error(f"Failed to load conversation summary: {e}")
        return None


def get_message_count(agent_id: UUID, contact_id: UUID) -> int:
    """Return total message count for a contact's conversation."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM messages m
                   JOIN conversations c ON m.conversation_id = c.id
                   WHERE c.agent_id = %s AND c.contact_id = %s""",
                [str(agent_id), str(contact_id)],
            ).fetchone()
        return row["cnt"] if row else 0
    except psycopg.Error as e:
        logger.error(f"Failed to get message count: {e}")
        return 0


def get_conversation_span_days(agent_id: UUID, contact_id: UUID) -> int:
    """Return the span in days between the first and last message."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """SELECT
                       EXTRACT(DAY FROM (MAX(m.created_at) - MIN(m.created_at)))::int AS span_days
                   FROM messages m
                   JOIN conversations c ON m.conversation_id = c.id
                   WHERE c.agent_id = %s AND c.contact_id = %s""",
                [str(agent_id), str(contact_id)],
            ).fetchone()
        return row["span_days"] if row and row["span_days"] else 0
    except psycopg.Error as e:
        logger.error(f"Failed to get conversation span: {e}")
        return 0


def should_summarize(agent_id: UUID, contact_id: UUID) -> bool:
    """Check whether this conversation needs a (new or updated) summary."""
    total = get_message_count(agent_id, contact_id)

    # Standard threshold check
    above_threshold = total >= SUMMARIZATION_THRESHOLD

    # Time-based trigger: 25+ messages spanning 30+ days (catches slow-burn buyers)
    time_based_trigger = False
    if not above_threshold and total >= TIME_BASED_MESSAGE_MIN:
        span_days = get_conversation_span_days(agent_id, contact_id)
        time_based_trigger = span_days >= TIME_BASED_SPAN_DAYS

    if not above_threshold and not time_based_trigger:
        return False

    existing = get_conversation_summary(agent_id, contact_id)
    if existing is None:
        # Never been summarized and over threshold — yes
        return True

    # Check if enough new messages have come in since last summary
    unsummarized = total - existing.messages_summarized_count
    return unsummarized >= INCREMENTAL_BATCH


def generate_or_update_summary(agent_id: UUID, contact_id: UUID) -> ConversationSummary | None:
    """Generate an initial summary or incrementally update an existing one.

    Returns the saved ConversationSummary, or None on failure.
    """
    existing = get_conversation_summary(agent_id, contact_id)

    try:
        with get_db_connection() as conn:
            # Get conversation id
            conv_row = conn.execute(
                """SELECT id FROM conversations
                   WHERE agent_id = %s AND contact_id = %s
                   ORDER BY created_at DESC LIMIT 1""",
                [str(agent_id), str(contact_id)],
            ).fetchone()

        if not conv_row:
            logger.warning(f"No conversation found for agent={agent_id}, contact={contact_id}")
            return None

        conversation_id = conv_row["id"]

        if existing is None:
            return _generate_initial_summary(agent_id, contact_id, conversation_id)
        else:
            return _update_existing_summary(agent_id, contact_id, conversation_id, existing)

    except psycopg.Error as e:
        logger.error(f"Summarization failed for contact {contact_id}: {e}", exc_info=True)
        return None


def _load_messages_for_summary(
    agent_id: UUID,
    contact_id: UUID,
    after_message_id: UUID | None = None,
    limit: int = 200,
) -> list[Message]:
    """Load messages, optionally after a specific message id."""
    try:
        with get_db_connection() as conn:
            if after_message_id:
                # Get the created_at of the marker message
                marker = conn.execute(
                    "SELECT created_at FROM messages WHERE id = %s",
                    [str(after_message_id)],
                ).fetchone()

                if marker:
                    rows = conn.execute(
                        """SELECT m.* FROM messages m
                           JOIN conversations c ON m.conversation_id = c.id
                           WHERE c.agent_id = %s AND c.contact_id = %s
                             AND m.created_at > %s
                           ORDER BY m.created_at ASC LIMIT %s""",
                        [str(agent_id), str(contact_id), marker["created_at"], limit],
                    ).fetchall()
                else:
                    # Marker not found — load all
                    rows = conn.execute(
                        """SELECT m.* FROM messages m
                           JOIN conversations c ON m.conversation_id = c.id
                           WHERE c.agent_id = %s AND c.contact_id = %s
                           ORDER BY m.created_at ASC LIMIT %s""",
                        [str(agent_id), str(contact_id), limit],
                    ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT m.* FROM messages m
                       JOIN conversations c ON m.conversation_id = c.id
                       WHERE c.agent_id = %s AND c.contact_id = %s
                       ORDER BY m.created_at ASC LIMIT %s""",
                    [str(agent_id), str(contact_id), limit],
                ).fetchall()

        return [Message(**r) for r in rows]
    except psycopg.Error as e:
        logger.error(f"Failed to load messages for summarization: {e}")
        return []


def _format_messages_for_prompt(messages: list[Message]) -> str:
    """Format messages into a readable transcript for the LLM."""
    lines = []
    for msg in messages:
        sender = msg.sender_type
        if sender == "ai":
            sender = "Assistant"
        elif sender == "client":
            sender = "Client"
        elif sender == "agent_command":
            sender = "Agent"
        else:
            sender = sender.capitalize()

        timestamp = msg.created_at.strftime("%m/%d %H:%M") if msg.created_at else ""
        lines.append(f"[{timestamp}] {sender}: {msg.body}")
    return "\n".join(lines)


def _generate_initial_summary(
    agent_id: UUID,
    contact_id: UUID,
    conversation_id: UUID,
) -> ConversationSummary | None:
    """Generate the first summary for a conversation."""
    messages = _load_messages_for_summary(agent_id, contact_id)
    if not messages:
        return None

    transcript = _format_messages_for_prompt(messages)
    client = get_anthropic_client()

    summary_text = client.compose(
        system_prompt=INITIAL_SUMMARY_PROMPT,
        context=f"Conversation transcript ({len(messages)} messages):\n\n{transcript}",
        instruction="Produce the structured summary now.",
        agent_id=agent_id,
        max_tokens=SUMMARY_MAX_TOKENS,
        model=HAIKU_MODEL,
    )

    last_msg = messages[-1]

    return _save_summary(
        agent_id=agent_id,
        contact_id=contact_id,
        conversation_id=conversation_id,
        summary_text=summary_text,
        messages_summarized_count=len(messages),
        last_message_id=last_msg.id,
    )


def _needs_full_resummarization(existing: ConversationSummary) -> bool:
    """Check if the summary has had enough incremental updates to warrant a full refresh."""
    return existing.incremental_count >= FULL_RESUMMARIZE_EVERY


def _update_existing_summary(
    agent_id: UUID,
    contact_id: UUID,
    conversation_id: UUID,
    existing: ConversationSummary,
) -> ConversationSummary | None:
    """Incrementally update an existing summary, or do a full re-summarization
    every FULL_RESUMMARIZE_EVERY cycles to prevent contextual drift."""

    # Check if we need a full re-summarization to combat drift
    if _needs_full_resummarization(existing):
        logger.info(
            f"Full re-summarization triggered for contact {contact_id} "
            f"(incremental_count={existing.incremental_count})"
        )
        return _full_resummarize(agent_id, contact_id, conversation_id, existing)

    new_messages = _load_messages_for_summary(
        agent_id, contact_id, after_message_id=existing.last_message_id
    )
    if not new_messages:
        return existing

    transcript = _format_messages_for_prompt(new_messages)
    system_prompt = INCREMENTAL_SUMMARY_PROMPT.format(
        existing_summary=existing.summary_text,
    )

    client = get_anthropic_client()

    updated_text = client.compose(
        system_prompt=system_prompt,
        context=f"New messages ({len(new_messages)} messages):\n\n{transcript}",
        instruction="Produce the updated, merged summary now.",
        agent_id=agent_id,
        max_tokens=SUMMARY_MAX_TOKENS,
        model=HAIKU_MODEL,
    )

    last_msg = new_messages[-1]
    total_count = existing.messages_summarized_count + len(new_messages)

    return _save_summary(
        agent_id=agent_id,
        contact_id=contact_id,
        conversation_id=conversation_id,
        summary_text=updated_text,
        messages_summarized_count=total_count,
        last_message_id=last_msg.id,
        existing_id=existing.id,
        incremental_count=existing.incremental_count + 1,
    )


def _full_resummarize(
    agent_id: UUID,
    contact_id: UUID,
    conversation_id: UUID,
    existing: ConversationSummary,
) -> ConversationSummary | None:
    """Do a full re-summarization from ALL messages to correct drift."""
    all_messages = _load_messages_for_summary(agent_id, contact_id, limit=500)
    if not all_messages:
        return existing

    transcript = _format_messages_for_prompt(all_messages)
    client = get_anthropic_client()

    summary_text = client.compose(
        system_prompt=FULL_RESUMMARIZE_PROMPT,
        context=f"Full conversation transcript ({len(all_messages)} messages):\n\n{transcript}",
        instruction="Produce the structured summary now from the full transcript.",
        agent_id=agent_id,
        max_tokens=SUMMARY_MAX_TOKENS,
        model=HAIKU_MODEL,
    )

    last_msg = all_messages[-1]

    return _save_summary(
        agent_id=agent_id,
        contact_id=contact_id,
        conversation_id=conversation_id,
        summary_text=summary_text,
        messages_summarized_count=len(all_messages),
        last_message_id=last_msg.id,
        existing_id=existing.id,
        incremental_count=0,  # Reset after full re-summarization
    )


def _save_summary(
    agent_id: UUID,
    contact_id: UUID,
    conversation_id: UUID,
    summary_text: str,
    messages_summarized_count: int,
    last_message_id: UUID | None,
    existing_id: UUID | None = None,
    incremental_count: int = 0,
) -> ConversationSummary | None:
    """Upsert a conversation summary row."""
    token_estimate = max(1, len(summary_text.split()) * 4 // 3)  # rough word→token

    try:
        with get_db_connection() as conn:
            if existing_id:
                row = conn.execute(
                    """UPDATE conversation_summaries
                       SET summary_text = %s,
                           messages_summarized_count = %s,
                           last_message_id = %s,
                           token_estimate = %s,
                           incremental_count = %s,
                           updated_at = now()
                       WHERE id = %s
                       RETURNING *""",
                    [summary_text, messages_summarized_count,
                     str(last_message_id) if last_message_id else None,
                     token_estimate, incremental_count, str(existing_id)],
                ).fetchone()
            else:
                row = conn.execute(
                    """INSERT INTO conversation_summaries
                           (tenant_id, contact_id, conversation_id, summary_text,
                            messages_summarized_count, last_message_id, token_estimate,
                            incremental_count)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (conversation_id) DO UPDATE SET
                           summary_text = EXCLUDED.summary_text,
                           messages_summarized_count = EXCLUDED.messages_summarized_count,
                           last_message_id = EXCLUDED.last_message_id,
                           token_estimate = EXCLUDED.token_estimate,
                           incremental_count = EXCLUDED.incremental_count,
                           updated_at = now()
                       RETURNING *""",
                    [str(agent_id), str(contact_id), str(conversation_id),
                     summary_text, messages_summarized_count,
                     str(last_message_id) if last_message_id else None,
                     token_estimate, incremental_count],
                ).fetchone()
            conn.commit()

        if row:
            return ConversationSummary(**row)
        return None
    except psycopg.Error as e:
        logger.error(f"Failed to save conversation summary: {e}")
        return None
