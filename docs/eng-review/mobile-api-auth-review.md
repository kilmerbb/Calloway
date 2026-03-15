# Engineering Review: Epic 1 — Mobile API Authentication

**Reviewer:** Atlas (Engineering Lead)
**Date:** 2026-03-15
**Stories:** MOB-AUTH-001 through MOB-AUTH-004
**Status:** Approved with technical specs added

---

## Executive Summary

All four stories are feasible as specified. The existing codebase provides strong foundations to build on: the agent portal (`app/api/agent_portal.py`) already implements phone+code login via Redis, `app/db/connection.py` has RLS context helpers (`set_agent_context` / `async_set_agent_context`), and `app/api/console_auth.py` provides rate-limiting patterns we can reuse. The main new dependency is PyJWT (not currently in `requirements.txt`).

Overall, this is clean, well-scoped work. No architectural concerns.

---

## New Dependency

**PyJWT** (`pyjwt>=2.8,<3`) must be added to `requirements.txt`. PyJWT is the standard lightweight JWT library for Python. We will use HS256 signing, which is built-in and requires no additional crypto dependencies. Do NOT use `python-jose` — it's heavier and has had supply-chain concerns.

---

## New Files / Modules

| File | Purpose |
|------|---------|
| `app/api/mobile/__init__.py` | Package init |
| `app/api/mobile/auth.py` | Auth endpoints: login, verify, refresh, logout |
| `app/api/mobile/deps.py` | `get_current_agent` dependency + JWT utilities |
| `app/config.py` | Add `MOBILE_JWT_SECRET` field |
| `app/main.py` | Register mobile router |

No new database tables required. No schema migration needed.

---

## MOB-AUTH-001: Agent Login (JWT Issuance)

### Feasibility: Can do as specified

### Technical Spec

**Implementation approach:**

1. Create `app/api/mobile/auth.py` with a router prefixed at `/api/v1/mobile/auth`.
2. Reuse the existing `generate_login_code()` pattern from `app/api/agent_portal.py` (6-digit code via `secrets.randbelow`, stored in Redis with 5-min TTL). Use a distinct Redis key prefix: `mobile_login_code:{phone}` (as specified) to avoid collision with the agent portal's `login_code:{phone}` keys.
3. Phone lookup uses async DB pool via `get_async_db_connection()`, querying `agents.phone`.
4. On verify success:
   - Generate access token: JWT with `{"agent_id": str(uuid), "type": "access", "jti": uuid4()}`, signed with HS256, 30-min expiry.
   - Generate refresh token: `secrets.token_urlsafe(48)` — opaque, stored in Redis as `mobile_refresh:{token}` -> `agent_id`, 30-day TTL.
5. SMS delivery: Reuse `app/services/twilio_service.send_sms()`. Look up the agent's `twilio_number` for the `from_` param, same pattern as agent portal login.

**E.164 normalization:** Add a small utility function in `deps.py` that strips whitespace/dashes and validates the `+` prefix with country code. Use a simple regex (`^\+[1-9]\d{1,14}$`) rather than pulling in `phonenumbers` library. If validation fails, return 422. This keeps the dependency footprint small while handling the common cases.

**Anti-enumeration (AC4):** The current agent portal DOES reveal whether a phone exists (returns an error message). The mobile API correctly specifies returning 200 regardless. Implementation: always return success response; only actually generate code + send SMS if the agent exists. Log the attempt either way.

**Rate limiting (AC5):** Implement per-phone rate limiting (not per-IP, since the story specifies per-phone). Redis key: `mobile_verify_attempts:{phone}`, INCR on each failed verify, expire after 15 min. Check count before verify attempt. This mirrors the pattern in `console_auth.py` (`check_rate_limit` / `record_failed_attempt`) but keyed on phone instead of IP.

**Redis unavailable:** Return 503 as specified. Unlike the agent portal (which has an in-memory fallback), the mobile API should NOT fall back to in-memory storage — it's a multi-instance deployment and in-memory codes won't work across instances. The agent portal fallback is a legacy dev-mode convenience; don't replicate it.

**Double login race condition:** Not a real concern. Two simultaneous code requests for the same phone just overwrite the Redis key — the user gets whichever code arrived last via SMS. No atomicity issue.

### Effort Refinement

**Agree with PM estimate: M (1-3 days).** Likely 1.5 days including tests. Most of the logic has direct precedent in the codebase.

### Risks / Concerns

- **SMS cost:** Each login attempt sends an SMS segment. The anti-enumeration behavior (no SMS for unknown phones) mitigates spam-driven cost inflation. No additional mitigation needed now, but consider IP-level rate limiting in a future pass if abuse is observed.
- **Code deletion on verify:** Delete the code from Redis after successful verify (same as agent portal `_delete_login_code`). Also delete on successful rate-limit trigger to prevent locked-out users from retrying with old codes after the window expires.

### Tightened Acceptance Criteria

- AC-T1: Phone input must be validated as E.164 format. Invalid format returns 422 `{"detail": "Invalid phone number format. Use E.164 (e.g., +15551234567)."}`.
- AC-T2: Login code must be deleted from Redis after successful verification (single-use).
- AC-T3: Rate limit counter must be reset on successful verification.
- AC-T4: The Redis key for login codes must use the prefix `mobile_login_code:` (not `login_code:`) to avoid collision with the agent portal.
- AC-T5: When `ENVIRONMENT == "development"`, include the code in the response JSON for testing convenience: `{"message": "Verification code sent", "expires_in": 300, "dev_code": "123456"}`.

---

## MOB-AUTH-002: Token Refresh

### Feasibility: Can do as specified

### Technical Spec

**Implementation approach:**

1. `POST /api/v1/mobile/auth/refresh` accepts `{"refresh_token": "..."}`. No access token required (it may be expired — that's the whole point of refresh).
2. Look up `mobile_refresh:{token}` in Redis. If missing/expired, return 401.
3. On success:
   - Delete old refresh token from Redis.
   - Generate new refresh token, store in Redis with 30-day TTL.
   - Generate new access token JWT with same claims (re-read agent_id from the Redis value, not from the old JWT).
   - Return both tokens.

**Token rotation + replay detection (AC3-4, edge case):**

The PM specifies: "Replay attack -> revoke ALL tokens for agent + log security warning." This requires a token family tracking mechanism. Implementation:

- When a refresh token is created, associate it with a `family_id` (a UUID generated at initial login). Store in Redis: `mobile_refresh:{token}` -> `{"agent_id": "...", "family_id": "..."}`.
- Also maintain a set: `mobile_refresh_family:{family_id}` containing all active refresh tokens for that family.
- On refresh: delete old token, create new token in same family.
- On replay of an already-consumed token: the key won't exist in Redis (it was deleted during rotation). When a refresh token is not found AND we can detect it was previously valid (by checking a short-lived "used token" marker), revoke all tokens in that family.
- **Simpler alternative (recommended):** Skip family tracking for v1. If a refresh token doesn't exist in Redis, just return 401. The attacker can't do anything with a consumed token. Full replay detection with family revocation adds complexity without meaningful security gain for a solo-agent app with 1-2 devices. Add it later if multi-device becomes common.

**Recommendation:** Go with the simpler approach. A consumed refresh token returns 401. No family tracking. Revisit if/when we see multi-device usage patterns that warrant it.

**Concurrent multi-device:** Each device gets its own independent refresh token at login. Refreshing one doesn't affect the other. This works naturally since each token is a distinct Redis key.

### Effort Refinement

**Agree with PM estimate: S (<1 day).** This is straightforward Redis get/delete/set.

### Risks / Concerns

None significant. The simpler approach avoids over-engineering.

### Tightened Acceptance Criteria

- AC-T1: The refresh endpoint must NOT require an access token in the Authorization header (the access token may be expired).
- AC-T2: The new refresh token must have a fresh 30-day TTL (not the remaining TTL of the old one).
- AC-T3: Agent existence must be re-verified on refresh — if the agent has been deleted/deactivated between refreshes, return 401. (Query `agents` table to confirm the agent_id still exists.)

---

## MOB-AUTH-003: Logout (Token Revocation)

### Feasibility: Can do as specified

### Technical Spec

**Implementation approach:**

1. `POST /api/v1/mobile/auth/logout` — requires access token in header (via `get_current_agent` dependency), optionally accepts `{"refresh_token": "..."}` in body.
2. If refresh token provided: delete `mobile_refresh:{token}` from Redis.
3. Extract JTI from the access token, compute remaining lifetime (`exp - now`), and add to deny list: `mobile_jwt_deny:{jti}` with TTL = remaining lifetime. This is the standard JWT revocation pattern — the deny-list entry auto-expires when the JWT would have expired anyway.
4. Return 200 `{"message": "Logged out"}`.

**Idempotency (AC3):** Deleting a non-existent Redis key is a no-op. Adding a JTI to the deny list that's already there is also a no-op (SET with TTL overwrites). Natural idempotency, no special handling needed.

**Lost refresh token (edge case):** If the body has no refresh_token or it's null, just deny-list the access token JTI. The refresh token will expire naturally (30 days). Acceptable tradeoff — forcing a "logout all devices" for a lost token is overkill for v1.

### Effort Refinement

**Agree with PM estimate: S (<1 day).** Very simple — two Redis operations.

### Risks / Concerns

- **Deny list size:** Each deny-list entry lives for at most 30 minutes (access token lifetime). Even with aggressive logout patterns, this is negligible Redis memory. No concern.

### Tightened Acceptance Criteria

- AC-T1: The deny-list TTL must equal the remaining lifetime of the access token, NOT the full 30 minutes. This prevents stale entries from accumulating if the token is close to expiry.
- AC-T2: If the refresh_token field is omitted or null, the endpoint must still succeed (deny-listing the access token only). Do not return 422 for missing refresh_token.
- AC-T3: Response body: `{"message": "Logged out successfully"}` with status 200.

---

## MOB-AUTH-004: JWT Authentication Middleware

### Feasibility: Can do as specified

### Technical Spec

**Implementation approach:**

1. Create `app/api/mobile/deps.py` containing:
   - `MOBILE_JWT_SECRET` read from `get_settings().MOBILE_JWT_SECRET`.
   - `create_access_token(agent_id: str) -> str` — builds JWT with `{"agent_id": agent_id, "type": "access", "jti": str(uuid4()), "exp": now + 30min, "iat": now}`, signs with HS256.
   - `get_current_agent(request: Request) -> str` — FastAPI `Depends()` function.

2. `get_current_agent` logic:
   - Extract `Authorization: Bearer <token>` header. Missing header -> 401 `{"detail": "Not authenticated"}`.
   - Decode JWT with `jwt.decode(token, MOBILE_JWT_SECRET, algorithms=["HS256"], leeway=30)`. PyJWT handles signature validation, expiration check, and clock skew leeway natively via the `leeway` parameter.
   - Verify `type == "access"`. Wrong type -> 401 `{"detail": "Invalid token type"}`.
   - Check JTI against Redis deny list: `mobile_jwt_deny:{jti}`. If exists -> 401 `{"detail": "Token has been revoked"}`.
   - On success: call `async_set_agent_context(conn, agent_id)` to set RLS context. **Important detail:** RLS context is set per-connection via `SET app.current_agent_id`. Since connections are pooled and shared, we must set this at the start of each request handler's DB transaction, not as a global middleware side-effect. The dependency should return the `agent_id` string; individual handlers set RLS context when they acquire a connection.

3. **Malformed token handling:** PyJWT raises `jwt.DecodeError` for malformed tokens and `jwt.ExpiredSignatureError` for expired ones. Map these to appropriate 401 responses with distinct messages:
   - `DecodeError` -> `{"detail": "Malformed token"}`
   - `ExpiredSignatureError` -> `{"detail": "Token has expired"}`
   - `InvalidTokenError` (catch-all) -> `{"detail": "Invalid token"}`

4. **Router registration:** In `app/main.py`, add a new router for mobile API endpoints. Apply `get_current_agent` as a dependency at the router level for all non-auth routes under `/api/v1/mobile/`.

**Config addition:**

Add to `app/config.py` `Settings` class:
```python
MOBILE_JWT_SECRET: str = ""
```

Add to `validate_production_secrets()`:
```python
if not self.MOBILE_JWT_SECRET:
    errors.append("MOBILE_JWT_SECRET is not set")
```

**RLS context pattern:** The existing codebase sets RLS context per-query in `execute_query()` / `async_execute_query()` via the `agent_id` parameter. The mobile API should follow the same pattern — pass `agent_id` (returned by `get_current_agent`) to each query helper. Do NOT try to set RLS in middleware; it won't work with connection pooling (the connection used in middleware is different from the one used in the handler).

### Effort Refinement

**Agree with PM estimate: M (1-3 days).** The dependency itself is ~1 day. The remaining time covers wiring it into the router structure, adding config, and writing thorough tests for all failure modes.

### Risks / Concerns

- **`MOBILE_JWT_SECRET` must be strong:** Document that this must be at least 32 bytes of randomness. Add a length check in `validate_production_secrets()` (min 32 chars).
- **HS256 is appropriate here:** The PM specified HS256, which is correct for a single-service architecture where the same service signs and verifies. If we ever need third-party token verification, we'd switch to RS256, but that's not on the horizon.
- **Redis dependency for deny-list check:** Every authenticated request checks Redis. If Redis is down, we should fail open or fail closed? **Recommendation: fail open with a warning log.** The deny list only matters for explicit logouts, which are rare. A brief Redis outage shouldn't lock out all mobile users. Log a warning so we notice and fix it.

### Tightened Acceptance Criteria

- AC-T1: `MOBILE_JWT_SECRET` must be a non-empty config value. App must refuse to start in production without it (enforced in `validate_production_secrets()`).
- AC-T2: `MOBILE_JWT_SECRET` must be at least 32 characters in production. Warn (don't block) in development.
- AC-T3: Clock skew leeway must be exactly 30 seconds (not configurable — keep it simple).
- AC-T4: Redis deny-list check must fail open (allow request) if Redis is unavailable, with a WARNING-level log entry.
- AC-T5: The `get_current_agent` dependency must return the `agent_id` as a `str` (UUID string). It must NOT set RLS context directly — handlers are responsible for setting RLS context when they acquire a DB connection.
- AC-T6: Auth endpoints (`/api/v1/mobile/auth/*`) must be excluded from the authentication dependency.
- AC-T7: JWT payload must include `iat` (issued-at) claim for auditing purposes.

---

## Cross-Cutting Concerns

### Testing Strategy

Each story needs unit tests covering the happy path and all specified edge cases. Recommended test structure:

| Test File | Coverage |
|-----------|----------|
| `tests/test_mobile_auth_login.py` | Login flow: code generation, SMS send, verify success, verify failure, rate limiting, E.164 validation, anti-enumeration |
| `tests/test_mobile_auth_tokens.py` | Token refresh, rotation, expired refresh, agent deletion between refreshes |
| `tests/test_mobile_auth_logout.py` | Logout with/without refresh token, idempotency, deny-list expiry |
| `tests/test_mobile_auth_middleware.py` | JWT decode, expiry, clock skew, deny-list check, malformed token, missing header, wrong token type |

Mock Redis and DB for unit tests. Integration tests should use the real Redis + test DB.

### CORS

The mobile app will make requests from a native app context (React Native or similar), so CORS is not directly relevant for native requests. However, if there's a web-based companion or the app uses a WebView, ensure `/api/v1/mobile/*` endpoints are included in CORS allowed origins. No action needed now — the existing CORS config in `main.py` handles this via the `CORS_ALLOWED_ORIGINS` env var.

### Logging

All auth events should use structured logging (already configured via `app/pipeline/structured_logging.py`). Key events to log:
- Login code requested (phone, masked)
- Login code verified (agent_id)
- Login failed (reason, phone masked)
- Token refreshed (agent_id)
- Logout (agent_id)
- Rate limit triggered (phone masked)
- Redis failure in auth path (operation, error)

### Security Checklist

- [x] No user enumeration on login (AC4 of MOB-AUTH-001)
- [x] Rate limiting on verify attempts (AC5 of MOB-AUTH-001)
- [x] JWT signed with dedicated secret, not reusing console secret
- [x] Refresh tokens are opaque (not JWTs — no information leakage)
- [x] Token rotation on refresh (old token invalidated)
- [x] Deny-list for revoked access tokens
- [x] RLS context set per-connection, not in middleware
- [x] Production startup blocked without JWT secret
- [x] Clock skew handled with bounded leeway

---

## Summary

| Story | Feasibility | Effort (PM) | Effort (Eng) | Notes |
|-------|-------------|-------------|--------------|-------|
| MOB-AUTH-001 | Approved | M | M (1.5 days) | Straightforward; reuses existing patterns |
| MOB-AUTH-002 | Approved | S | S (0.5 days) | Skip family tracking for v1 |
| MOB-AUTH-003 | Approved | S | S (0.5 days) | Natural idempotency |
| MOB-AUTH-004 | Approved | M | M (1.5 days) | Core dependency; must be solid |

**Total estimated effort:** 4 days for implementation + tests. All stories can proceed to implementation. The one new dependency (PyJWT) is well-maintained and lightweight.

**Implementation order:** MOB-AUTH-004 (middleware) first, then MOB-AUTH-001 (login), then MOB-AUTH-002 (refresh), then MOB-AUTH-003 (logout). The middleware is a dependency for everything else, and login must exist before refresh/logout make sense.
