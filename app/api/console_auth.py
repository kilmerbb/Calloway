"""Console authentication — per-user accounts with hashed passwords, role-based
sessions, legacy single-password fallback, CSRF protection, and audit logging."""
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional

from fastapi import Request, Response

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import get_settings
from app.services.redis_pool import get_redis_pool

import psycopg
import redis

logger = logging.getLogger(__name__)

SESSION_COOKIE = "console_session"
CSRF_COOKIE = "console_csrf"
SESSION_MAX_AGE = 86400  # 24 hours


# ── Password hashing (scrypt via hashlib — no external dep) ─────────

def hash_password(password: str) -> str:
    """Hash a password using scrypt with a random salt.

    Returns a string in the format: salt$hash  (both hex-encoded).
    """
    salt = secrets.token_bytes(32)
    dk = hashlib.scrypt(
        password.encode(), salt=salt, n=16384, r=8, p=1, dklen=64,
    )
    return salt.hex() + "$" + dk.hex()


def verify_password_hash(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored scrypt hash (salt$hash)."""
    try:
        salt_hex, hash_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.scrypt(
        password.encode(), salt=salt, n=16384, r=8, p=1, dklen=64,
    )
    return hmac.compare_digest(dk, expected)


# ── Legacy single-password verification ─────────────────────────────

def _verify_legacy_password(password: str) -> bool:
    """Check password against the shared CONSOLE_PASSWORD setting."""
    settings = get_settings()
    return hmac.compare_digest(password, settings.CONSOLE_PASSWORD)


# ── User lookup ─────────────────────────────────────────────────────

def _lookup_user_by_email(email: str) -> Optional[dict]:
    """Look up a console user by email. Returns dict or None."""
    from app.db.connection import get_db_connection
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT id, email, password_hash, display_name, role, active "
                "FROM console_users WHERE email = %s",
                [email],
            ).fetchone()
            if row:
                return {
                    "id": str(row[0]),
                    "email": row[1],
                    "password_hash": row[2],
                    "display_name": row[3],
                    "role": row[4],
                    "active": row[5],
                }
    except psycopg.Error:
        logger.exception("Failed to look up console user by email")
    return None


# ── Serializer ───────────────────────────────────────────────────────

def _get_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.CONSOLE_SESSION_SECRET)


def _is_production() -> bool:
    return get_settings().ENVIRONMENT != "development"


# ── Authentication entry point ──────────────────────────────────────

def verify_password(password: str, email: str | None = None) -> Optional[dict]:
    """Authenticate a user. Returns session payload dict on success, None on failure.

    Per-user mode (email provided):
      Look up user → verify hash → return user info.
    Legacy mode (no email, LEGACY_AUTH_MODE=True):
      Verify against CONSOLE_PASSWORD → return legacy session.
    """
    settings = get_settings()

    # Per-user authentication
    if email:
        user = _lookup_user_by_email(email)
        if not user:
            return None
        if not user["active"]:
            return None
        if not verify_password_hash(password, user["password_hash"]):
            return None
        return {
            "authenticated": True,
            "user_id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "role": user["role"],
        }

    # Legacy single-password mode
    if settings.LEGACY_AUTH_MODE and _verify_legacy_password(password):
        return {
            "authenticated": True,
            "user_id": None,
            "email": None,
            "display_name": "Operator (legacy)",
            "role": "admin",
        }

    return None


# ── Session management ──────────────────────────────────────────────

def create_session(response: Response, user_info: dict) -> None:
    """Create a session cookie containing user identity and role."""
    s = _get_serializer()
    payload = {
        "authenticated": True,
        "user_id": user_info.get("user_id"),
        "email": user_info.get("email"),
        "display_name": user_info.get("display_name"),
        "role": user_info.get("role", "viewer"),
        "ts": int(time.time()),
    }
    token = s.dumps(payload)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_is_production(),
    )


def check_session(request: Request) -> Optional[dict]:
    """Check if the request has a valid session cookie.

    Returns a dict with user info on success:
      {"authenticated": True, "user_id": str|None, "email": str|None,
       "display_name": str, "role": str}
    Returns None if not authenticated.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    s = _get_serializer()
    try:
        data = s.loads(token, max_age=SESSION_MAX_AGE)
        if not data.get("authenticated"):
            return None
        return {
            "authenticated": True,
            "user_id": data.get("user_id"),
            "email": data.get("email"),
            "display_name": data.get("display_name", "Unknown"),
            "role": data.get("role", "viewer"),
        }
    except (BadSignature, SignatureExpired):
        return None


def clear_session(response: Response) -> None:
    """Remove the session cookie."""
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


# ── CSRF protection ─────────────────────────────────────────────────

def generate_csrf_token(request: Request, response: Response) -> str:
    """Return a CSRF token, setting a cookie if one doesn't already exist."""
    token = request.cookies.get(CSRF_COOKIE)
    if not token:
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            CSRF_COOKIE,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=False,  # JS needs to read this for HTMX
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


# ── Login rate limiting ─────────────────────────────────────────────

_RATE_LIMIT_MAX_ATTEMPTS = 5
_RATE_LIMIT_WINDOW = 900  # 15 minutes


def check_rate_limit(ip: str) -> tuple[bool, int]:
    """Check if an IP is rate-limited. Returns (allowed, retry_after_seconds)."""
    try:
        r = get_redis_pool()
        key = f"login_attempts:{ip}"
        attempts = r.get(key)
        if attempts and int(attempts) >= _RATE_LIMIT_MAX_ATTEMPTS:
            ttl = r.ttl(key)
            return False, max(ttl, 60)
        return True, 0
    except redis.RedisError:
        logger.warning("Redis unavailable for rate limiting — failing open")
        return True, 0


def record_failed_attempt(ip: str) -> None:
    """Increment the failed login counter for an IP.

    Uses SET NX on expire so the TTL is only set once (on key creation),
    preventing attackers from extending the window with repeated attempts.
    """
    try:
        r = get_redis_pool()
        key = f"login_attempts:{ip}"
        count = r.incr(key)
        if count == 1:
            # Only set expiry when the key is first created
            r.expire(key, _RATE_LIMIT_WINDOW)
    except redis.RedisError:
        logger.warning("Redis unavailable — failed attempt not recorded")


def reset_rate_limit(ip: str) -> None:
    """Clear the failed login counter for an IP after successful login."""
    try:
        r = get_redis_pool()
        r.delete(f"login_attempts:{ip}")
    except redis.RedisError:
        pass


# ── Audit logging ───────────────────────────────────────────────────

def log_audit(
    user_id: str | None,
    action: str,
    target_entity: str | None = None,
    target_id: str | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write an audit log entry. Fire-and-forget — never raises or blocks.

    Uses a background thread so a slow/unreachable DB never stalls request handling.
    """
    import threading

    def _write():
        try:
            from app.db.connection import get_db_connection
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO audit_log (user_id, action, target_entity, target_id, ip_address, metadata) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    [
                        user_id,
                        action,
                        target_entity,
                        target_id,
                        ip_address,
                        json.dumps(metadata) if metadata else None,
                    ],
                )
                conn.commit()
        except psycopg.Error:
            logger.warning("Failed to write audit log entry for action=%s", action)

    t = threading.Thread(target=_write, daemon=True)
    t.start()


# ── User management helpers ─────────────────────────────────────────

def validate_password_complexity(password: str) -> str | None:
    """Validate password meets minimum complexity requirements.

    Returns None if valid, or an error message string if invalid.
    Requires: 8+ chars, at least one uppercase, one lowercase, one digit.
    These thresholds balance security with usability for non-technical
    real estate agents who may not use password managers.
    """
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit"
    return None


def create_console_user(
    email: str,
    password: str,
    display_name: str,
    role: str = "viewer",
) -> dict:
    """Create a new console user. Returns the created user dict.

    Raises ValueError if email already exists, role is invalid,
    or password does not meet complexity requirements.
    """
    if role not in ("admin", "viewer"):
        raise ValueError(f"Invalid role: {role}. Must be 'admin' or 'viewer'.")

    complexity_error = validate_password_complexity(password)
    if complexity_error:
        raise ValueError(complexity_error)

    from app.db.connection import get_db_connection
    pw_hash = hash_password(password)
    with get_db_connection() as conn:
        try:
            row = conn.execute(
                "INSERT INTO console_users (email, password_hash, display_name, role) "
                "VALUES (%s, %s, %s, %s) RETURNING id, email, display_name, role, active, created_at",
                [email, pw_hash, display_name, role],
            ).fetchone()
            conn.commit()
        except psycopg.Error as e:
            conn.rollback()
            if "idx_console_users_email" in str(e) or "unique" in str(e).lower():
                raise ValueError(f"A user with email '{email}' already exists.") from e
            raise
    return {
        "id": str(row[0]),
        "email": row[1],
        "display_name": row[2],
        "role": row[3],
        "active": row[4],
        "created_at": str(row[5]),
    }
