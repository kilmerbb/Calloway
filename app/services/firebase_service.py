"""Firebase Cloud Messaging service for push notifications."""
import logging
from uuid import UUID

from app.config import get_settings

logger = logging.getLogger(__name__)

# Notification priority by tier
TIER_CONFIG = {
    "urgent": {"priority": "high", "sound": "alert"},
    "action_needed": {"priority": "high", "sound": "default"},
    "informational": {"priority": "normal", "sound": None},
    "briefing": {"priority": "normal", "sound": "gentle"},
}


def send_push_notification(
    agent_id: UUID,
    tier: str,
    title: str,
    body: str,
    contact_id: UUID | None = None,
    listing_id: UUID | None = None,
    data: dict | None = None,
) -> dict:
    """
    Send a Firebase push notification to an agent's device.
    Returns {delivered: bool}.
    """
    settings = get_settings()
    tier_config = TIER_CONFIG.get(tier, TIER_CONFIG["informational"])

    # Build deep link URL
    deep_link = None
    if contact_id:
        deep_link = f"/conversations/{contact_id}"

    notification_data = {
        "tier": tier,
        "title": title,
        "body": body,
        "priority": tier_config["priority"],
        "agent_id": str(agent_id),
    }
    if deep_link:
        notification_data["deep_link_url"] = deep_link
    if contact_id:
        notification_data["contact_id"] = str(contact_id)
    if listing_id:
        notification_data["listing_id"] = str(listing_id)
    if data:
        notification_data.update(data)

    # In production, this would use firebase_admin to send
    # For now, log the notification
    logger.info(
        f"Push notification [{tier}] to agent {agent_id}: {title} - {body[:80]}"
    )

    # TODO: Implement actual Firebase sending:
    # from firebase_admin import messaging
    # message = messaging.Message(
    #     notification=messaging.Notification(title=title, body=body),
    #     data=notification_data,
    #     token=agent_device_token,
    # )
    # messaging.send(message)

    return {"delivered": True, "tier": tier}
