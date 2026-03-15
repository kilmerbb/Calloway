import logging
import secrets
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.db.connection import get_async_db_connection
from app.services.redis_pool import get_redis_pool
from app.services.twilio_service import send_sms

from .deps import (
    create_access_token,
    create_refresh_token,
    get_current_agent,
    normalize_e164,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mobile/auth", tags=["mobile-auth"])


class LoginRequest(BaseModel):
    phone: str


class LoginResponse(BaseModel):
    message: str
    expires_in: int
    dev_code: str | None = None


class VerifyRequest(BaseModel):
    phone: str
    code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class MessageResponse(BaseModel):
    message: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    phone = normalize_e164(body.phone)
    settings = get_settings()

    try:
        r = get_redis_pool()
        r.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    agent = None
    async with get_async_db_connection() as conn:
        result = await conn.execute(
            "SELECT id, phone, twilio_number FROM agents WHERE phone = %s", [phone]
        )
        agent = await result.fetchone()

    response = LoginResponse(
        message="If an account exists, a verification code has been sent",
        expires_in=300,
    )

    if agent:
        code = f"{secrets.randbelow(1000000):06d}"
        r.setex(f"mobile_login_code:{phone}", 300, code)

        twilio_from = agent.get("twilio_number") or settings.TWILIO_PHONE_NUMBER

        send_sms(
            to=phone,
            from_=twilio_from,
            body=f"Your Calloway verification code is: {code}",
            agent_id=agent["id"],
        )
        logger.info("Login code sent", extra={"phone": phone, "agent_id": str(agent["id"])})

    if settings.ENVIRONMENT == "development" and agent:
        response.dev_code = code

    return response


@router.post("/verify", response_model=TokenResponse)
async def verify(body: VerifyRequest):
    phone = normalize_e164(body.phone)

    try:
        r = get_redis_pool()
        r.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    rate_key = f"mobile_verify_attempts:{phone}"
    attempts = r.get(rate_key)
    if attempts and int(attempts) >= 5:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")

    stored_code = r.get(f"mobile_login_code:{phone}")
    if not stored_code or stored_code.decode() != body.code:
        r.incr(rate_key)
        ttl = r.ttl(rate_key)
        if ttl < 0:
            r.expire(rate_key, 900)
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    async with get_async_db_connection() as conn:
        result = await conn.execute(
            "SELECT id FROM agents WHERE phone = %s", [phone]
        )
        agent = await result.fetchone()

    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    r.delete(f"mobile_login_code:{phone}")
    r.delete(rate_key)

    agent_id = str(agent["id"])
    access_token = create_access_token(agent_id)
    refresh_token, _ = create_refresh_token(agent_id)

    logger.info("Login verified", extra={"agent_id": agent_id})

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    try:
        r = get_redis_pool()
        r.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    redis_key = f"mobile_refresh:{body.refresh_token}"
    agent_id_bytes = r.get(redis_key)

    if not agent_id_bytes:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    agent_id = agent_id_bytes.decode()

    async with get_async_db_connection() as conn:
        result = await conn.execute(
            "SELECT id FROM agents WHERE id = %s::uuid", [agent_id]
        )
        agent = await result.fetchone()

    if not agent:
        r.delete(redis_key)
        raise HTTPException(status_code=401, detail="Agent no longer exists")

    r.delete(redis_key)

    access_token = create_access_token(agent_id)
    refresh_token, _ = create_refresh_token(agent_id)

    logger.info("Token refreshed", extra={"agent_id": agent_id})

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    body: LogoutRequest | None = None,
    agent_id: str = Depends(get_current_agent),
):
    settings = get_settings()
    try:
        r = get_redis_pool()
    except Exception:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:]  # Strip "Bearer "
    try:
        payload = jwt.decode(
            token,
            settings.MOBILE_JWT_SECRET,
            algorithms=["HS256"],
            leeway=30,
        )
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            remaining = int(exp - datetime.now(timezone.utc).timestamp())
            if remaining > 0:
                r.setex(f"mobile_jwt_deny:{jti}", remaining, "1")
    except jwt.PyJWTError:
        pass

    if body and body.refresh_token:
        r.delete(f"mobile_refresh:{body.refresh_token}")

    logger.info("Agent logged out", extra={"agent_id": agent_id})

    return MessageResponse(message="Logged out successfully")
