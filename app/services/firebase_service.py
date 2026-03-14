"""Firebase Cloud Messaging service for push notifications.

Handles real FCM delivery via the firebase-admin SDK, device token
management, and graceful degradation when credentials are not configured.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

from app.config import get_settings
from app.db.connection import get_db_connection

import psycopg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Firebase Admin SDK initialisation (lazy, once)
# ---------------------------------------------------------------------------
_firebase_app = None
_firebase_init_attempted = False


def _get_firebase_app():
    """Lazily initialise and return the Firebase Admin app.

    Returns None if credentials are not configured — callers must handle this
    gracefully (log + skip).
    """
    global _firebase_app, _firebase_init_attempted

    if _firebase_init_attempted:
        return _firebase_app

    _firebase_init_attempted = True

    settings = get_settings()
    creds_value = settings.FIREBASE_CREDENTIALS_JSON

    if not creds_value:
        logger.info(
            "FIREBASE_CREDENTIALS_JSON not set — push notifications disabled"
        )
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Accept either inline JSON or a file path
        if creds_value.strip().startswith("{"):
            cred = credentials.Certificate(json.loads(creds_value))
        elif os.path.isfile(creds_value):
            cred = credentials.Certificate(creds_value)
        else:
            logger.error(
                "FIREBASE_CREDENTIALS_JSON is neither valid JSON nor a file path"
            )
            return None

        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialised successfully")
        return _firebase_app

    except Exception:  # Broad catch: Firebase SDK init (lazy-imported)
        logger.exception("Failed to initialise Firebase Admin SDK")
        return None


# ---------------------------------------------------------------------------
# Notification tier configuration
# ---------------------------------------------------------------------------
TIER_CONFIG = {
    "urgent": {"priority": "high", "sound": "alert", "android_priority": "high"},
    "action_needed": {"priority": "high", "sound": "default", "android_priority": "high"},
    "informational": {"priority": "normal", "sound": None, "android_priority": "normal"},
    "briefing": {"priority": "normal", "sound": "gentle", "android_priority": "normal"},
}


# ---------------------------------------------------------------------------
# Device token CRUD
# ---------------------------------------------------------------------------

def register_device_token(
    agent_id: UUID,
    fcm_token: str,
    device_name: str | None = None,
    platform: str | None = None,
) -> dict:
    """Register or re-activate an FCM device token for an agent.

    Uses upsert so that re-registering the same token just refreshes the
    timestamp and re-activates it if it was previously invalidated.
    """
    with get_db_connection() as conn:
        row = conn.execute(
            """INSERT INTO device_tokens (agent_id, fcm_token, device_name, platform)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (fcm_token) DO UPDATE
                 SET agent_id   = EXCLUDED.agent_id,
                     device_name = COALESCE(EXCLUDED.device_name, device_tokens.device_name),
                     platform    = COALESCE(EXCLUDED.platform, device_tokens.platform),
                     is_active   = true,
                     updated_at  = now()
               RETURNING id, agent_id, fcm_token, device_name, platform, is_active""",
            [str(agent_id), fcm_token, device_name, platform],
        ).fetchone()
        conn.commit()

    logger.info("Device token registered for agent %s (%s)", agent_id, platform or "unknown")
    return dict(row) if row else {}


def unregister_device_token(fcm_token: str) -> bool:
    """Deactivate a device token (e.g. on logout)."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE device_tokens SET is_active = false, updated_at = now() WHERE fcm_token = %s",
            [fcm_token],
        )
        conn.commit()
    return True


def _get_active_tokens(agent_id: UUID) -> list[str]:
    """Return all active FCM tokens for an agent."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT fcm_token FROM device_tokens WHERE agent_id = %s AND is_active = true",
            [str(agent_id)],
        ).fetchall()
    return [r["fcm_token"] for r in rows]


def _deactivate_token(fcm_token: str) -> None:
    """Mark a token as inactive (called when FCM reports it invalid)."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE device_tokens SET is_active = false, updated_at = now() WHERE fcm_token = %s",
                [fcm_token],
            )
            conn.commit()
        logger.info("Deactivated invalid FCM token: %s...%s", fcm_token[:8], fcm_token[-4:])
    except psycopg.Error:
        logger.exception("Failed to deactivate token")


# ---------------------------------------------------------------------------
# Core send logic
# ---------------------------------------------------------------------------

def _build_fcm_message(
    token: str,
    tier: str,
    title: str,
    body: str,
    data: dict,
):
    """Build a firebase_admin.messaging.Message."""
    from firebase_admin import messaging

    tier_cfg = TIER_CONFIG.get(tier, TIER_CONFIG["informational"])

    # Data payload — all values must be strings for FCM
    str_data = {k: str(v) for k, v in data.items()}

    # Notification payload (displayed in system tray)
    notification = messaging.Notification(title=title, body=body)

    # Platform-specific config
    android = messaging.AndroidConfig(
        priority=tier_cfg["android_priority"],
        notification=messaging.AndroidNotification(
            sound=tier_cfg["sound"] or "default",
            channel_id=f"calloway_{tier}",
        ),
    )

    apns_sound = tier_cfg["sound"] or "default"
    apns = messaging.APNSConfig(
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                sound=apns_sound,
                badge=1,
            ),
        ),
    )

    return messaging.Message(
        token=token,
        notification=notification,
        data=str_data,
        android=android,
        apns=apns,
    )


def _send_to_token(token: str, tier: str, title: str, body: str, data: dict) -> bool:
    """Send a single message to one FCM token. Returns True on success."""
    from firebase_admin import messaging
    from firebase_admin.exceptions import (
        InvalidArgumentError,
        NotFoundError,
    )

    msg = _build_fcm_message(token, tier, title, body, data)

    try:
        message_id = messaging.send(msg, app=_firebase_app)
        logger.debug("FCM sent OK: %s (message_id=%s)", token[:8], message_id)
        return True

    except (InvalidArgumentError, NotFoundError):
        # Token is no longer valid — deactivate it
        logger.warning("FCM token invalid, deactivating: %s...%s", token[:8], token[-4:])
        _deactivate_token(token)
        return False

    except messaging.UnregisteredError:
        # Device unregistered — deactivate the token
        logger.warning("FCM token unregistered, deactivating: %s...%s", token[:8], token[-4:])
        _deactivate_token(token)
        return False

    except Exception:  # Broad catch: Firebase SDK errors
        logger.exception("FCM send failed for token %s...%s", token[:8], token[-4:])
        return False


# ---------------------------------------------------------------------------
# Public API — same signature as the old stub
# ---------------------------------------------------------------------------

def send_push_notification(
    agent_id: UUID,
    tier: str,
    title: str,
    body: str,
    contact_id: UUID | None = None,
    listing_id: UUID | None = None,
    data: dict | None = None,
) -> dict:
    """Send a Firebase push notification to all of an agent's devices.

    Returns {delivered: bool, sent_count: int, token_count: int}.

    If Firebase is not configured, logs the notification and returns
    delivered=False gracefully (never crashes).
    """
    tier_config = TIER_CONFIG.get(tier, TIER_CONFIG["informational"])

    # Build the data payload
    notification_data: dict = {
        "tier": tier,
        "title": title,
        "body": body,
        "priority": tier_config["priority"],
        "agent_id": str(agent_id),
    }
    if contact_id:
        notification_data["contact_id"] = str(contact_id)
        notification_data["deep_link_url"] = f"/conversations/{contact_id}"
    if listing_id:
        notification_data["listing_id"] = str(listing_id)
    if data:
        notification_data.update(data)

    # Always log for observability
    logger.info(
        "Push notification [%s] to agent %s: %s - %s",
        tier, agent_id, title, body[:80],
    )

    # Check Firebase availability
    app = _get_firebase_app()
    if app is None:
        logger.debug("Firebase not configured — notification logged only")
        return {"delivered": False, "reason": "firebase_not_configured", "tier": tier}

    # Fetch device tokens
    tokens = _get_active_tokens(agent_id)
    if not tokens:
        logger.info("No active device tokens for agent %s — skipping FCM", agent_id)
        return {"delivered": False, "reason": "no_device_tokens", "tier": tier}

    # Send to all devices — fire-and-forget in background if there's a running
    # event loop, otherwise send synchronously.
    sent_count = 0
    try:
        loop = asyncio.get_running_loop()
        # We're inside an async context — offload blocking FCM calls to a thread
        loop.run_in_executor(
            None,
            _send_to_all_tokens_sync,
            tokens, tier, title, body, notification_data,
        )
        # Optimistically report delivered since we can't await the executor here
        # without changing the sync signature. Errors are logged inside the executor.
        return {"delivered": True, "sent_count": len(tokens), "token_count": len(tokens), "tier": tier}
    except RuntimeError:
        # No running event loop — send synchronously (workers, CLI, tests)
        sent_count = _send_to_all_tokens_sync(tokens, tier, title, body, notification_data)
        return {
            "delivered": sent_count > 0,
            "sent_count": sent_count,
            "token_count": len(tokens),
            "tier": tier,
        }


def _send_to_all_tokens_sync(
    tokens: list[str],
    tier: str,
    title: str,
    body: str,
    data: dict,
) -> int:
    """Send to all tokens synchronously. Returns count of successful sends."""
    sent = 0
    for token in tokens:
        if _send_to_token(token, tier, title, body, data):
            sent += 1
    if sent < len(tokens):
        logger.warning(
            "FCM: delivered to %d/%d devices", sent, len(tokens),
        )
    return sent
