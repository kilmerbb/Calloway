"""Console authentication — password-based session auth with CSRF protection."""
import hashlib
import hmac
import logging
import secrets
import time

from fastapi import Request, Response
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import get_settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "console_session"
CSRF_COOKIE = "console_csrf"
SESSION_MAX_AGE = 86400  # 24 hours


def _get_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.CONSOLE_SESSION_SECRET)


def _is_production() -> bool:
    return get_settings().ENVIRONMENT != "development"


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
        secure=_is_production(),
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
    response.delete_cookie(CSRF_COOKIE)


# ── CSRF protection ──────────────────────────────────────────

def generate_csrf_token(request: Request, response: Response) -> str:
    """Return a CSRF token, setting a cookie if one doesn't already exist."""
    token = request.cookies.get(CSRF_COOKIE)
    if not token:
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            CSRF_COOKIE,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=False,  # JS needs to read this for HTMX if needed
            samesite="lax",
            secure=_is_production(),
        )
    return token


def validate_csrf_token(request: Request, form_token: str | None) -> bool:
    """Validate that the form token matches the cookie token."""
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token or not form_token:
        return False
    return hmac.compare_digest(cookie_token, form_token)
