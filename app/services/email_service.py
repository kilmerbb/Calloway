"""Email service — send and receive email via SendGrid."""

import logging
from uuid import UUID

from app.config import get_settings
from app.db.connection import get_db_connection

import psycopg

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    from_email: str,
    subject: str,
    body: str,
    agent_id: UUID | None = None,
    html_content: str | None = None,
) -> dict:
    """Send an email via SendGrid. Returns {"message_id": ..., "status": ...}."""
    settings = get_settings()
    api_key = settings.SENDGRID_API_KEY

    if not api_key:
        logger.warning("SENDGRID_API_KEY not configured — email not sent")
        return {"message_id": None, "status": "not_configured"}

    try:
        import sendgrid
        from sendgrid.helpers.mail import Content, Mail

        sg = sendgrid.SendGridAPIClient(api_key=api_key)

        # Build HTML content: use caller-provided HTML or wrap plain text
        if html_content:
            final_html = html_content
        else:
            escaped_body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            paragraphs = "".join(f"<p>{line}</p>" for line in escaped_body.split("\n") if line.strip())
            final_html = f"<html><body>{paragraphs}</body></html>"

        message = Mail(
            from_email=from_email,
            to_emails=to,
            subject=subject,
            plain_text_content=body,
            html_content=Content("text/html", final_html),
        )
        response = sg.send(message)
        message_id = response.headers.get("X-Message-Id", "")

        logger.info(
            "Email sent to %s (status %s)",
            to, response.status_code,
            extra={"agent_id": str(agent_id) if agent_id else None},
        )
        return {"message_id": message_id, "status": "sent"}

    except Exception as e:  # Broad catch: SendGrid SDK errors (lazy-imported)
        logger.error("Failed to send email to %s: %s", to, e, exc_info=True)
        return {"message_id": None, "status": "error", "error": str(e)}


def send_client_email(
    agent_id: UUID,
    contact_id: UUID,
    message: str,
    from_email: str,
    to_email: str,
    subject: str = "",
) -> dict:
    """Send email to a client, log to messages table, update last_contact_at."""
    if not subject:
        subject = "Message from your agent"

    result = send_email(
        to=to_email,
        from_email=from_email,
        subject=subject,
        body=message,
        agent_id=agent_id,
    )

    # Log to messages table
    try:
        with get_db_connection() as conn:
            conv = conn.execute(
                """SELECT id FROM conversations
                   WHERE agent_id = %s AND contact_id = %s AND channel = 'email'
                   ORDER BY created_at DESC LIMIT 1""",
                [str(agent_id), str(contact_id)],
            ).fetchone()

            if not conv:
                conv = conn.execute(
                    """INSERT INTO conversations (agent_id, contact_id, channel, last_message_at)
                       VALUES (%s, %s, 'email', now()) RETURNING id""",
                    [str(agent_id), str(contact_id)],
                ).fetchone()

            conn.execute(
                """INSERT INTO messages (agent_id, conversation_id, sender_type, body,
                    ai_generated, model_used)
                   VALUES (%s, %s, 'ai', %s, true, 'template')""",
                [str(agent_id), str(conv["id"]), message],
            )

            conn.execute(
                "UPDATE contacts SET last_contact_at = now() WHERE id = %s",
                [str(contact_id)],
            )
            conn.execute(
                "UPDATE conversations SET last_message_at = now() WHERE id = %s",
                [str(conv["id"])],
            )
            conn.commit()
    except psycopg.Error as e:
        logger.error("Failed to log email message: %s", e, exc_info=True)

    return result


def parse_inbound_email(raw_payload: dict) -> dict:
    """Parse an inbound email from SendGrid Inbound Parse webhook.

    SendGrid forwards emails as multipart/form-data with fields:
    from, to, subject, text, html, envelope, headers, etc.
    """
    envelope = raw_payload.get("envelope", "{}")
    if isinstance(envelope, str):
        import json
        try:
            envelope = json.loads(envelope)
        except (json.JSONDecodeError, TypeError):
            envelope = {}

    return {
        "from_address": raw_payload.get("from", ""),
        "from_name": _extract_name(raw_payload.get("from", "")),
        "to_address": raw_payload.get("to", ""),
        "subject": raw_payload.get("subject", ""),
        "text": raw_payload.get("text", ""),
        "html": raw_payload.get("html", ""),
        "message_id": raw_payload.get("Message-ID", raw_payload.get("message_id", "")),
        "envelope": envelope,
    }


def _extract_name(from_header: str) -> str:
    """Extract display name from 'Jane Smith <jane@test.com>' format."""
    if "<" in from_header:
        return from_header.split("<")[0].strip().strip('"')
    parts = from_header.split("@")
    return parts[0] if parts else from_header


def _extract_email(from_header: str) -> str:
    """Extract email address from 'Jane Smith <jane@test.com>' format."""
    if "<" in from_header:
        return from_header.split("<")[1].rstrip(">").strip()
    return from_header.strip()
