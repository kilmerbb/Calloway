"""Conversation view endpoint — deep link target for push notifications."""
import logging
from uuid import UUID

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import get_settings
from app.db.connection import get_db_connection

import psycopg

logger = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])

TOKEN_MAX_AGE = 86400  # 24 hours


def _get_serializer():
    settings = get_settings()
    secret = settings.TWILIO_AUTH_TOKEN
    if not secret:
        raise RuntimeError(
            "TWILIO_AUTH_TOKEN must be configured to sign conversation tokens"
        )
    return URLSafeTimedSerializer(secret)


def generate_conversation_token(contact_id: UUID, agent_id: UUID) -> str:
    """Generate a signed URL token for conversation access."""
    s = _get_serializer()
    return s.dumps({"contact_id": str(contact_id), "agent_id": str(agent_id)})


@router.get("/conversations/{contact_id}", response_class=HTMLResponse)
async def view_conversation(contact_id: str, token: str = ""):
    """Render a minimal conversation view for a contact."""
    # Validate token
    s = _get_serializer()
    try:
        data = s.loads(token, max_age=TOKEN_MAX_AGE)
        if data.get("contact_id") != contact_id:
            raise HTTPException(status_code=403, detail="Invalid token")
        agent_id = data["agent_id"]
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    # Load contact and messages
    try:
        with get_db_connection() as conn:
            contact = conn.execute(
                "SELECT * FROM contacts WHERE id = %s", [contact_id]
            ).fetchone()

            messages = conn.execute(
                """SELECT m.body, m.sender_type, m.created_at, m.ai_generated
                   FROM messages m
                   JOIN conversations c ON m.conversation_id = c.id
                   WHERE c.contact_id = %s AND c.agent_id = %s
                   ORDER BY m.created_at ASC LIMIT 100""",
                [contact_id, agent_id],
            ).fetchall()
    except psycopg.Error as e:
        logger.error(f"Conversation query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load conversation")

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Render simple HTML
    message_html = ""
    for msg in messages:
        css_class = "ai" if msg["sender_type"] == "ai" else "client"
        if msg["sender_type"] == "agent_command":
            css_class = "agent"
        label = {"client": "Client", "ai": "AI", "agent_command": "Agent", "system": "System"}.get(msg["sender_type"], msg["sender_type"])
        time_str = msg["created_at"].strftime("%I:%M %p") if msg["created_at"] else ""
        message_html += f'<div class="msg {css_class}"><span class="label">{label}</span> <span class="time">{time_str}</span><p>{msg["body"]}</p></div>'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{contact['name']} - Conversation</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 16px; background: #f5f5f5; }}
.header {{ background: #2563eb; color: white; padding: 16px; border-radius: 12px; margin-bottom: 16px; }}
.header h2 {{ margin: 0; }} .header p {{ margin: 4px 0 0; opacity: 0.8; font-size: 14px; }}
.msg {{ padding: 12px; margin: 8px 0; border-radius: 12px; background: white; }}
.msg.ai {{ background: #e0f2fe; border-left: 3px solid #2563eb; }}
.msg.client {{ background: white; border-left: 3px solid #10b981; }}
.msg.agent {{ background: #fef3c7; border-left: 3px solid #f59e0b; }}
.label {{ font-weight: 600; font-size: 12px; text-transform: uppercase; }}
.time {{ font-size: 11px; color: #888; }} .msg p {{ margin: 4px 0 0; }}
</style></head><body>
<div class="header"><h2>{contact['name']}</h2><p>{contact['role']} · {contact['lifecycle_stage']} · {contact['phone']}</p></div>
{message_html if message_html else '<p style="color:#888;text-align:center;">No messages yet</p>'}
</body></html>"""

    return HTMLResponse(content=html)
