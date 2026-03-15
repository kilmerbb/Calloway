"""WebSocket endpoint for real-time mobile conversation updates via Redis pub/sub."""

import asyncio
import json
import logging

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.services.redis_async import get_async_redis
from app.services.redis_pool import get_redis_pool

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["mobile-ws"])


@ws_router.websocket("/api/v1/mobile/ws/conversations")
async def ws_conversations(websocket: WebSocket, token: str = Query(...)):
    """Real-time conversation updates for a mobile client.

    Authentication is via JWT passed as a query parameter (WebSocket does not
    support custom headers in browser clients).  The connection subscribes to
    the agent's Redis pub/sub channel and forwards every published event as a
    JSON text frame.  A ping frame is sent every 30 s to keep the connection
    alive; token expiry is re-checked on each ping.
    """

    # 1. Validate JWT from query param ----------------------------------------
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.MOBILE_JWT_SECRET,
            algorithms=["HS256"],
            leeway=30,
        )
        if payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token type")
            return
        agent_id = payload["agent_id"]

        # Check JWT deny-list
        jti = payload.get("jti")
        if jti:
            try:
                r = get_redis_pool()
                if r.get(f"mobile_jwt_deny:{jti}"):
                    await websocket.close(code=4001, reason="Token revoked")
                    return
            except Exception:
                # Same fail-open policy as deps.py:get_current_agent — see comment there
                logger.warning("Redis unavailable for WS deny-list check, failing open")
    except jwt.ExpiredSignatureError:
        await websocket.close(code=4001, reason="Token expired")
        return
    except jwt.DecodeError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # 2. Accept connection -----------------------------------------------------
    await websocket.accept()
    logger.debug("WS connected", extra={"agent_id": agent_id})

    # 3. Subscribe to Redis pub/sub channel ------------------------------------
    async_redis = get_async_redis()
    pubsub = async_redis.pubsub()
    channel = f"mobile:agent:{agent_id}"
    await pubsub.subscribe(channel)

    try:
        # Run ping loop and message listener concurrently
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_ping_loop(websocket, settings.MOBILE_JWT_SECRET, token))
            tg.create_task(_listen_loop(websocket, pubsub))
    except* WebSocketDisconnect:
        logger.info("WS disconnected", extra={"agent_id": agent_id})
    except* Exception as eg:
        for exc in eg.exceptions:
            if not isinstance(exc, WebSocketDisconnect):
                logger.warning("WS error: %s", exc, extra={"agent_id": agent_id})
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _ping_loop(websocket: WebSocket, jwt_secret: str, token: str) -> None:
    """Send a JSON ping every 30 s. Close the socket if the token has expired."""
    while True:
        await asyncio.sleep(30)
        # Re-check token expiry
        try:
            jwt.decode(token, jwt_secret, algorithms=["HS256"], leeway=30)
        except jwt.ExpiredSignatureError:
            await websocket.close(code=4001, reason="Token expired")
            return
        await websocket.send_json({"type": "ping"})


async def _listen_loop(websocket: WebSocket, pubsub) -> None:
    """Forward Redis pub/sub messages to the WebSocket client."""
    async for message in pubsub.listen():
        if message["type"] == "message":
            # data is already a string since decode_responses=True
            await websocket.send_text(message["data"])


# ---------------------------------------------------------------------------
# Publish helper (called from pipeline / other modules)
# ---------------------------------------------------------------------------

async def publish_mobile_event(agent_id: str, event: dict) -> None:
    """Publish an event to the mobile WebSocket channel for an agent.

    Safe to call even if no WebSocket clients are connected — Redis pub/sub
    simply drops the message when there are no subscribers.
    """
    try:
        async_redis = get_async_redis()
        channel = f"mobile:agent:{agent_id}"
        await async_redis.publish(channel, json.dumps(event, default=str))
    except Exception:  # Broad catch: Redis pub/sub is fire-and-forget
        logger.warning("Failed to publish mobile event", extra={"agent_id": agent_id})
