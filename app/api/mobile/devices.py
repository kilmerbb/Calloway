import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.firebase_service import register_device_token, unregister_device_token
from .deps import get_current_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mobile/devices", tags=["mobile-devices"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RegisterDeviceRequest(BaseModel):
    fcm_token: str
    device_name: str | None = None
    platform: str | None = None


class RegisterDeviceResponse(BaseModel):
    status: str
    device_id: str


class UnregisterDeviceRequest(BaseModel):
    fcm_token: str


class UnregisterDeviceResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=RegisterDeviceResponse)
async def register_device(body: RegisterDeviceRequest, agent_id: str = Depends(get_current_agent)):
    """Register an FCM device token for push notifications."""
    if not body.fcm_token or not body.fcm_token.strip():
        raise HTTPException(status_code=422, detail="fcm_token must be a non-empty string")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, register_device_token, UUID(agent_id), body.fcm_token, body.device_name, body.platform
    )

    device_id = str(result.get("id", "")) if result else ""
    return RegisterDeviceResponse(status="registered", device_id=device_id)


@router.post("/unregister", response_model=UnregisterDeviceResponse)
async def unregister_device(body: UnregisterDeviceRequest, agent_id: str = Depends(get_current_agent)):
    """Unregister an FCM device token (e.g. on logout)."""
    if not body.fcm_token or not body.fcm_token.strip():
        raise HTTPException(status_code=422, detail="fcm_token must be a non-empty string")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, unregister_device_token, body.fcm_token)

    logger.info("Device token unregistered", extra={"agent_id": agent_id, "fcm_token_prefix": body.fcm_token[:8]})
    return UnregisterDeviceResponse(status="unregistered")
