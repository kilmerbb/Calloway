"""Console authentication — simple password-based session auth."""
import hashlib
import hmac
import logging
import time

from fastapi import Request, Response
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import get_settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "console_session"
SESSION_MAX_AGE = 86400  # 24 hours


def _get_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.CONSOLE_SESSION_SECRET)


def verify_password(password: str) -> bool:
    """Check password against CONSOLE_PASSWORD setting."""
    settings = get_settings()
    return hmac.compare_digest(password, settings.CONSOLE_PASSWORD)


def create_session(response: Response) -> None:
    """Create a session cookie on the response."""
    s = _get_serializer()
    token = s.dumps({"authenticated": True, "ts": int(time.time())})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def check_session(request: Request) -> bool:
    """Check if the request has a valid session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    s = _get_serializer()
    try:
        data = s.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("authenticated", False)
    except (BadSignature, SignatureExpired):
        return False


def clear_session(response: Response) -> None:
    """Remove the session cookie."""
    response.delete_cookie(SESSION_COOKIE)
