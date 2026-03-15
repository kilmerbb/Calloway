"""Mobile API — Shared dependencies: JWT auth, E.164 validation, FastAPI deps."""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request

from app.config import get_settings
from app.services.redis_pool import get_redis_pool

logger = logging.getLogger(__name__)

E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")


def normalize_e164(phone: str) -> str:
    phone = phone.strip()
    if not E164_PATTERN.match(phone):
        raise HTTPException(status_code=422, detail="Invalid E.164 phone number")
    return phone


def create_access_token(agent_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "agent_id": agent_id,
        "type": "access",
        "jti": str(uuid4()),
        "exp": now + timedelta(minutes=30),
        "iat": now,
    }
    return jwt.encode(payload, settings.MOBILE_JWT_SECRET, algorithm="HS256")


def create_refresh_token(agent_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    r = get_redis_pool()
    key = f"mobile_refresh:{token}"
    r.setex(key, timedelta(days=30), agent_id)
    return token, key


async def get_current_agent(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.MOBILE_JWT_SECRET,
            algorithms=["HS256"],
            leeway=30,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Malformed token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    jti = payload.get("jti")
    if jti:
        try:
            r = get_redis_pool()
            if r.get(f"mobile_jwt_deny:{jti}"):
                raise HTTPException(status_code=401, detail="Token has been revoked")
        except HTTPException:
            raise
        except Exception:
            logger.warning("Redis unavailable for JWT deny-list check, failing open", extra={"jti": jti})

    return payload["agent_id"]
