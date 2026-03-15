# Mobile API Backend (Phase 1) — User Stories

**Epic Collection:** Mobile API Backend
**Created:** 2026-03-15
**Status:** Finalized — Ready for Stakeholder Approval
**Version:** 2.0

---

## Scope

This document defines the backend API work required to support the Calloway mobile app for solo real estate agents. The scope is strictly the FastAPI server-side endpoints, authentication layer, WebSocket support, and push notification integration. It does not cover the React Native/Expo mobile app itself, nor any admin console changes.

All endpoints live under `/api/v1/mobile/` and are authenticated via JWT (access + refresh token pair). The backend reuses existing PostgreSQL tables, RLS policies, and service layers wherever possible. The only new table required is `device_tokens`, which already exists in the schema.

**Design principle:** Keep it lean. Ship the minimum backend surface to unblock mobile MVP development. We can always expand later.

### Prerequisites (from Engineering Review)

Before implementation begins, the following must be in place:

1. **New dependency:** `pyjwt>=2.8,<3` added to `requirements.txt`. Use PyJWT (not `python-jose`). HS256 signing is built-in — no additional crypto dependencies required.
2. **Schema change:** `ALTER TABLE conversations ADD COLUMN last_read_at TIMESTAMPTZ;` — required for unread count tracking in MOB-CONV-001. Non-breaking additive change; NULL means "never read" (all messages count as unread).
3. **New file structure:**
   - `app/api/mobile/__init__.py` — Package init / router aggregation
   - `app/api/mobile/auth.py` — Auth endpoints (login, verify, refresh, logout)
   - `app/api/mobile/deps.py` — `get_current_agent` dependency + JWT utilities
   - `app/api/mobile/briefing.py` — Briefing and schedule endpoints
   - `app/api/mobile/devices.py` — Push device registration/deregistration
   - `app/api/mobile/ws.py` — WebSocket endpoint
   - `app/api/mobile/utils.py` — Shared utilities (timezone helpers, etc.)
4. **Config addition:** `MOBILE_JWT_SECRET` field in `app/config.py` with production validation.

### PM Decisions on Engineering Open Questions

The following decisions resolve open questions raised during engineering review:

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Is `last_read_at` per-conversation sufficient for unread tracking, or do we need per-message read receipts? | **Per-conversation is sufficient.** | MVP simplicity. Per-message tracking adds storage and query cost with no user-visible benefit for a solo agent. Revisit if we add multi-user teams. |
| 2 | Draft expiration window — what TTL for a pending `ask_agent` trigger before it returns 410 Gone? | **24 hours.** | Balances agent responsiveness with avoiding stale drafts. A draft older than 24 hours is likely contextually stale anyway. |
| 3 | Is a 2-character minimum for contact search acceptable? | **Yes, 2-character minimum.** | Prevents overly broad single-character searches that return nearly all contacts. Consistent with standard search UX. |
| 4 | Should the trigger worker fix (handling `ask_agent` approval flow) be a separate story? | **No — include as a prerequisite sub-task within MOB-CONV-003.** | The worker change only exists to support the approval flow; it has no standalone value. Keeping it within MOB-CONV-003 ensures it's implemented and tested as a unit. This is reflected in the effort bump from M to L. |

---

## Epic 1: Authentication

### MOB-AUTH-001: Agent Login (JWT Issuance)

**Priority:** P0 — Must-have
**Effort:** M (1-3 days)

#### User Story

> As a real estate agent, I want to log in to the mobile app with my phone number and a verification code, so that I can securely access my Calloway account on the go.

#### Background

The existing agent portal (`/agent`) uses a phone-based SMS code login flow with itsdangerous session cookies. The mobile API needs a similar phone+code flow but issues JWT tokens (access + refresh) instead of cookies. The agent is identified via the `agents.phone` column. Argon2 password hashing is not needed for this flow — we reuse the existing SMS verification code pattern already implemented in `agent_portal.py`.

#### Acceptance Criteria

1. **Given** a registered agent's phone number, **when** they POST to `/api/v1/mobile/auth/login` with `{"phone": "+1234567890"}`, **then** the server generates a 6-digit code, stores it in Redis with a 5-minute TTL (key: `mobile_login_code:{phone}`), and sends it via Twilio SMS. Response: `{"message": "Verification code sent", "expires_in": 300}` with status 200.
2. **Given** a valid verification code, **when** they POST to `/api/v1/mobile/auth/verify` with `{"phone": "+1234567890", "code": "123456"}`, **then** the server returns `{"access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 1800}` with status 200.
3. **Given** an invalid or expired code, **when** they POST to `/api/v1/mobile/auth/verify`, **then** the server returns 401 with `{"detail": "Invalid or expired verification code"}`.
4. **Given** a phone number not matching any agent in the `agents` table, **when** they POST to `/api/v1/mobile/auth/login`, **then** the server returns 200 with the same "code sent" response (no user enumeration) but does not actually send an SMS.
5. **Given** 5 failed verification attempts for the same phone within 15 minutes, **when** a 6th attempt is made, **then** the server returns 429 with `{"detail": "Too many attempts. Try again later."}`.
6. Access token: JWT with 30-minute expiry, contains `{"agent_id": "<uuid>", "type": "access"}`.
7. Refresh token: opaque token stored in Redis with 30-day TTL, keyed by token value, maps to agent_id.
8. *[ENG AC-T1]* Phone input must be validated as E.164 format (`^\+[1-9]\d{1,14}$`). Invalid format returns 422 `{"detail": "Invalid phone number format. Use E.164 (e.g., +15551234567)."}`.
9. *[ENG AC-T2]* Login code must be deleted from Redis after successful verification (single-use).
10. *[ENG AC-T3]* Rate limit counter must be reset on successful verification.
11. *[ENG AC-T4]* The Redis key for login codes must use the prefix `mobile_login_code:` (not `login_code:`) to avoid collision with the agent portal.
12. *[ENG AC-T5]* When `ENVIRONMENT == "development"`, include the code in the response JSON for testing convenience: `{"message": "Verification code sent", "expires_in": 300, "dev_code": "123456"}`.

#### Edge Cases

- Phone number normalization: strip spaces, ensure E.164 format. Reject non-E.164 numbers with 422.
- Race condition: two login requests in quick succession — second code should overwrite the first.
- Redis unavailable: return 503 with `{"detail": "Service temporarily unavailable"}`. Do NOT fall back to in-memory storage (multi-instance deployment).

#### Engineering Notes

- Reuse `generate_login_code()` pattern from `app/api/agent_portal.py` (6-digit code via `secrets.randbelow`).
- Use distinct Redis key prefix `mobile_login_code:{phone}` to avoid collision with agent portal's `login_code:{phone}`.
- SMS delivery: reuse `app/services/twilio_service.send_sms()`.
- Rate limiting: mirror `console_auth.py` pattern (`check_rate_limit` / `record_failed_attempt`) keyed on phone.
- Delete code from Redis on rate-limit trigger to prevent stale code reuse after window expires.

---

### MOB-AUTH-002: Token Refresh

**Priority:** P0 — Must-have
**Effort:** S (<1 day)

#### User Story

> As a real estate agent, I want my app to silently refresh my session, so that I don't get logged out while I'm actively using Calloway throughout the day.

#### Acceptance Criteria

1. **Given** a valid refresh token, **when** the client POSTs to `/api/v1/mobile/auth/refresh` with `{"refresh_token": "..."}`, **then** the server returns a new access token (and rotates the refresh token). Status 200.
2. **Given** an expired or revoked refresh token, **when** the client POSTs to `/api/v1/mobile/auth/refresh`, **then** the server returns 401 with `{"detail": "Invalid or expired refresh token"}`.
3. **Token rotation:** On each refresh, the old refresh token is invalidated and a new one is issued. This limits the window of a stolen refresh token.
4. The new access token contains the same claims as the original.
5. *[ENG AC-T1]* The refresh endpoint must NOT require an access token in the Authorization header (the access token may be expired).
6. *[ENG AC-T2]* The new refresh token must have a fresh 30-day TTL (not the remaining TTL of the old one).
7. *[ENG AC-T3]* Agent existence must be re-verified on refresh — if the agent has been deleted/deactivated between refreshes, return 401. (Query `agents` table to confirm the agent_id still exists.)

#### Edge Cases

- Replay attack: if a revoked refresh token is reused, return 401. Skip refresh token family tracking for v1 — a consumed token simply doesn't exist in Redis and returns 401. This is sufficient for a solo-agent app with 1-2 devices. Revisit family tracking if multi-device usage patterns warrant it.
- Concurrent refresh from multiple devices: each device holds its own refresh token; rotation only invalidates the specific token being refreshed.

#### Engineering Notes

- Skip family tracking for v1 (engineering recommendation, accepted). Simpler approach: consumed token returns 401.
- Agent_id is read from Redis value, not from old JWT.

---

### MOB-AUTH-003: Logout (Token Revocation)

**Priority:** P0 — Must-have
**Effort:** S (<1 day)

#### User Story

> As a real estate agent, I want to log out of the mobile app, so that my session is terminated and no one else can use my device to access my account.

#### Acceptance Criteria

1. **Given** a valid access token, **when** the client POSTs to `/api/v1/mobile/auth/logout` with `{"refresh_token": "..."}` (Authorization header carries the access token), **then** the server deletes the refresh token from Redis and adds the access token's JTI to a deny list in Redis (TTL = remaining access token lifetime). Status 200.
2. **Given** a subsequent request using the revoked access token, **when** any authenticated endpoint is called, **then** the server returns 401.
3. Logout is idempotent — calling it with an already-revoked token returns 200, not an error.
4. *[ENG AC-T1]* The deny-list TTL must equal the remaining lifetime of the access token, NOT the full 30 minutes. This prevents stale entries from accumulating if the token is close to expiry.
5. *[ENG AC-T2]* If the refresh_token field is omitted or null, the endpoint must still succeed (deny-listing the access token only). Do not return 422 for missing refresh_token.
6. *[ENG AC-T3]* Response body: `{"message": "Logged out successfully"}` with status 200.

#### Edge Cases

- If the client has lost the refresh token (e.g., app crash), logout with just the access token should still deny-list the access token. The orphaned refresh token expires naturally (30 days). Acceptable tradeoff for v1.

---

### MOB-AUTH-004: JWT Authentication Middleware

**Priority:** P0 — Must-have
**Effort:** M (1-3 days)

#### User Story

> As the system, I need a reusable authentication dependency that validates JWT access tokens on every mobile API request, so that all mobile endpoints are protected and tenant-isolated.

#### Acceptance Criteria

1. A FastAPI dependency (`get_current_agent`) decodes and validates the JWT access token from the `Authorization: Bearer <token>` header.
2. Validation checks: signature, expiration, token type ("access"), and JTI not in Redis deny list.
3. On success, returns the agent_id (UUID string). Individual handlers are responsible for setting the PostgreSQL RLS context (`SET app.current_agent_id = '<agent_id>'`) when they acquire a DB connection.
4. On failure (missing, expired, malformed, revoked), returns 401 with `{"detail": "..."}`.
5. All `/api/v1/mobile/` endpoints (except `/auth/login`, `/auth/verify`, `/auth/refresh`) require this dependency.
6. JWT signing uses HS256 with a server-side secret from config (`MOBILE_JWT_SECRET`).
7. *[ENG AC-T1]* `MOBILE_JWT_SECRET` must be a non-empty config value. App must refuse to start in production without it (enforced in `validate_production_secrets()`).
8. *[ENG AC-T2]* `MOBILE_JWT_SECRET` must be at least 32 characters in production. Warn (don't block) in development.
9. *[ENG AC-T3]* Clock skew leeway must be exactly 30 seconds (not configurable).
10. *[ENG AC-T4]* Redis deny-list check must fail open (allow request) if Redis is unavailable, with a WARNING-level log entry. The deny list only matters for explicit logouts; a brief Redis outage should not lock out all mobile users.
11. *[ENG AC-T5]* The `get_current_agent` dependency must return the `agent_id` as a `str` (UUID string). It must NOT set RLS context directly — handlers are responsible for setting RLS context when they acquire a DB connection.
12. *[ENG AC-T6]* Auth endpoints (`/api/v1/mobile/auth/*`) must be excluded from the authentication dependency.
13. *[ENG AC-T7]* JWT payload must include `iat` (issued-at) claim for auditing purposes.

#### Edge Cases

- Clock skew: allow up to 30 seconds of leeway on expiration checks.
- Missing `Authorization` header vs. malformed token: both return 401 but with distinct detail messages for client debugging (`"Not authenticated"` vs. `"Malformed token"` vs. `"Token has expired"` vs. `"Invalid token"`).

#### Engineering Notes

- PyJWT handles signature validation, expiration check, and clock skew leeway natively via the `leeway` parameter.
- RLS context follows the existing codebase pattern: pass `agent_id` to query helpers rather than setting RLS in middleware (connection pooling makes middleware-level RLS unreliable).
- Implementation order: build middleware first (MOB-AUTH-004), then login (MOB-AUTH-001), then refresh (MOB-AUTH-002), then logout (MOB-AUTH-003).

---

## Epic 2: Conversation Endpoints

### MOB-CONV-001: List Conversations

**Priority:** P0 — Must-have
**Effort:** M (1-3 days)

#### User Story

> As a real estate agent, I want to see a list of my recent conversations on my phone, so that I can quickly check who has messaged me and respond to urgent conversations.

#### Prerequisites

- Schema change: `ALTER TABLE conversations ADD COLUMN last_read_at TIMESTAMPTZ;` must be applied before implementation.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they GET `/api/v1/mobile/conversations`, **then** the server returns a paginated list of conversations ordered by `last_message_at DESC`.
2. Response shape per conversation:
   ```json
   {
     "id": "uuid",
     "contact_id": "uuid",
     "contact_name": "string",
     "contact_phone": "string",
     "channel": "sms|voice|email",
     "stage": "open|closed",
     "last_message_body": "string (truncated to 150 chars)",
     "last_message_at": "ISO8601",
     "unread_count": 0,
     "has_pending_draft": false
   }
   ```
3. Pagination: `?page=1&per_page=25` (defaults). Response includes `total`, `page`, `per_page`, `pages`.
4. Filter support: `?stage=open` to show only open conversations.
5. Queries use existing `conversations`, `messages`, and `contacts` tables. RLS enforces tenant isolation.
6. *[ENG AC6]* Response must include `contact_phone` for display when `contact_name` is null (deleted contact fallback). `contact_name` falls back to `COALESCE(c.name, c.phone)`.
7. *[ENG AC7]* `last_message_body` must be HTML-escaped to prevent XSS if rendered raw.
8. *[ENG AC8]* When `stage` filter is provided, validate against known values (`open`, `closed`, `snoozed`) — return 422 for unknown stages.
9. *[ENG AC9]* Unread count is calculated as messages created after `conversations.last_read_at` where `sender_type IN ('client', 'ai')`. NULL `last_read_at` means all messages are unread.

#### Edge Cases

- Conversations with no messages yet (just created): `last_message_body` is null, `last_message_at` is null. These sort to the bottom.
- Deleted/orphaned contacts: `contact_name` falls back to `contact_phone` if the contact record is missing.
- Performance: use a lateral join for `last_message_body` rather than a correlated subquery. Keep query under 100ms for 500 conversations.

#### Engineering Notes

- Use `LEFT JOIN LATERAL` for `last_message_body` (performance at scale).
- `has_pending_draft`: EXISTS subquery against `triggers` where `entity_id = contact_id`, `status = 'pending'`, `autonomy_level = 'ask_agent'`. Covered by `idx_triggers_agent_entity`.
- `unread_count`: lateral join on messages where `created_at > COALESCE(cv.last_read_at, '1970-01-01'::timestamptz)`. Covered by `idx_messages_conversation_created`.

---

### MOB-CONV-002: View Conversation Messages

**Priority:** P0 — Must-have
**Effort:** M (1-3 days)

#### User Story

> As a real estate agent, I want to open a conversation and see the full message history, so that I have context before responding to a client.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they GET `/api/v1/mobile/conversations/{id}/messages`, **then** the server returns a paginated list of messages ordered by `created_at ASC`.
2. Response shape per message:
   ```json
   {
     "id": "uuid",
     "sender_type": "client|ai|agent_command|system",
     "body": "string",
     "ai_generated": true,
     "delivery_status": "pending|delivered|failed",
     "created_at": "ISO8601"
   }
   ```
3. Pagination: `?page=1&per_page=50` (defaults). Supports `?before=<message_id>` cursor-based pagination for infinite scroll (return 50 messages before the given ID).
4. **Given** a conversation_id that does not belong to the authenticated agent, **when** they GET messages, **then** the server returns 404 (not 403 — no information leakage).
5. Queries use existing `messages` table with RLS.
6. *[ENG AC6]* When `before` parameter is present, ignore `page`/`per_page` and use cursor-based pagination with `per_page` as limit (default 50).
7. *[ENG AC7]* Cursor-based returns messages in reverse chronological order; offset-based returns chronological. This difference must be documented in the API contract.
8. *[ENG AC8]* Viewing messages updates `conversations.last_read_at = now()` to reset unread count.
9. *[ENG AC9]* Cursor must use `created_at` comparison (not UUID comparison). UUIDs from `gen_random_uuid()` are NOT sequential. Query: `WHERE created_at < (SELECT created_at FROM messages WHERE id = %s)`.

#### Edge Cases

- Very long conversations (1000+ messages): cursor-based pagination prevents performance degradation.
- Messages with `delivery_status = 'failed'`: include `failure_reason` field in response.

---

### MOB-CONV-003: Approve AI Draft

**Priority:** P0 — Must-have
**Effort:** L (3-5 days) *[Updated from M per engineering review — trigger worker modification required]*

#### User Story

> As a real estate agent, I want to approve an AI-drafted message from my phone, so that the message is sent to my client without me needing to be at a computer.

#### Background

When the system operates in "Supervised" autonomy mode, AI-generated messages are stored as triggers with `autonomy_level = 'ask_agent'` and `status = 'pending'`. Approving a trigger fires the message. The existing trigger_worker already handles the execution pipeline — the mobile API just needs to update the trigger status.

#### Prerequisite Sub-task: Trigger Worker Modification

The current trigger worker (`app/worker/trigger_worker.py`) only processes `status = 'pending'` triggers. It does not distinguish between auto-fire triggers and `ask_agent` triggers awaiting approval. The following modification is required before the approve endpoint is functional:

1. Modify the worker query to pick up both `'pending'` (non-ask_agent) and `'approved'` triggers.
2. For `ask_agent` triggers with `status = 'pending'`: skip (hold for approval, do not fire).
3. For `'approved'` triggers: fire the message, set to `'fired'`.
4. Use `FOR UPDATE SKIP LOCKED` pattern to handle race conditions with concurrent approve requests.

This is scoped within MOB-CONV-003 (not a separate story) because the worker change only exists to support the approval flow.

#### Acceptance Criteria

1. **Given** a pending trigger belonging to the authenticated agent, **when** they POST to `/api/v1/mobile/messages/{trigger_id}/approve`, **then** the trigger's status is updated to `'approved'` and the trigger_worker picks it up for execution on its next poll cycle. Response: `{"status": "approved", "trigger_id": "uuid"}` with status 200.
2. **Given** a trigger that is not in `'pending'` status, **when** they POST approve, **then** the server returns 409 with `{"detail": "Message is not pending approval"}`.
3. **Given** a trigger_id that does not belong to the agent, **when** they POST approve, **then** the server returns 404.
4. *[ENG AC4]* Trigger worker must be modified to distinguish `ask_agent` pending (hold for approval) from auto pending (fire immediately).
5. *[ENG AC5]* The approve endpoint must be idempotent within a reasonable window — if the trigger was already approved and is being processed, return 200 (not 409).
6. *[ENG AC6]* Add `message_preview` to the response so the agent can see what they approved: `{"status": "approved", "trigger_id": "uuid", "message_preview": "..."}`.
7. *[ENG AC7]* Expired trigger definition: `scheduled_at < now() - interval '24 hours'` AND still pending. Return 410 Gone with `{"detail": "This draft has expired", "expired_at": "..."}`.

#### Edge Cases

- Double-approve (race condition): the 409/200 idempotency response handles this gracefully.
- Trigger expires between listing and approval: return 410 Gone if `scheduled_at < now() - interval '24 hours'` and still pending. Response includes `expired_at`.

---

### MOB-CONV-004: Edit AI Draft Before Sending

**Priority:** P0 — Must-have
**Effort:** S (<1 day) *[Updated from M per engineering review — trivial CRUD]*

#### User Story

> As a real estate agent, I want to edit an AI-drafted message before approving it, so that I can adjust the tone or details before it reaches my client.

#### Acceptance Criteria

1. **Given** a pending trigger, **when** the agent POSTs to `/api/v1/mobile/messages/{trigger_id}/edit` with `{"body": "Updated message text"}`, **then** the trigger's `message_template` is updated and status remains `'pending'`. Response: `{"status": "updated", "trigger_id": "uuid"}` with status 200.
2. After editing, the agent can then approve (MOB-CONV-003) or reject (MOB-CONV-005) the trigger.
3. **Given** a trigger that is not `'pending'`, **when** they POST edit, **then** 409.
4. **Given** an empty body or body exceeding 1600 characters (SMS limit), **when** they POST edit, **then** 422 with a descriptive error.
5. *[ENG AC4]* The response should include the updated `message_template` for confirmation: `{"status": "updated", "trigger_id": "uuid", "body": "..."}`.
6. *[ENG AC5]* Body length validation should count characters, not bytes (Unicode-safe). Python's `len()` on `str` is character-count, which is correct.
7. *[ENG AC6]* Newlines are acceptable in the body (multi-line SMS).

#### Edge Cases

- Body with only whitespace: reject with 422.
- Unicode/emoji in body: accept — Twilio handles encoding.

---

### MOB-CONV-005: Reject AI Draft

**Priority:** P0 — Must-have
**Effort:** S (<1 day)

#### User Story

> As a real estate agent, I want to reject an AI-drafted message, so that it is not sent to my client when I disagree with what the AI suggested.

#### Acceptance Criteria

1. **Given** a pending trigger, **when** the agent POSTs to `/api/v1/mobile/messages/{trigger_id}/reject`, **then** the trigger's status is updated to `'cancelled'`. Response: `{"status": "rejected", "trigger_id": "uuid"}` with status 200.
2. **Given** a trigger not in `'pending'` status, **when** they POST reject, **then** 409.
3. **Given** a trigger_id not belonging to the agent, **when** they POST reject, **then** 404.
4. *[ENG AC4]* Expired trigger (same 24-hour definition as MOB-CONV-003) should return 410, consistent with the approve endpoint.

#### Edge Cases

- None beyond the standard auth and state checks.

---

## Epic 3: Contact Endpoints

### MOB-CONTACT-001: List Contacts

**Priority:** P0 — Must-have
**Effort:** M (1-3 days)

#### User Story

> As a real estate agent, I want to browse my contacts on my phone, so that I can look up a client's information while I'm out showing properties.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they GET `/api/v1/mobile/contacts`, **then** the server returns a paginated list of contacts ordered by `last_contact_at DESC NULLS LAST`.
2. Response shape per contact:
   ```json
   {
     "id": "uuid",
     "name": "string",
     "phone": "string",
     "email": "string|null",
     "role": "lead|buyer|seller|...",
     "lifecycle_stage": "new_lead|active|...",
     "last_contact_at": "ISO8601|null"
   }
   ```
3. Pagination: `?page=1&per_page=25`.
4. Search: `?search=<term>` matches against `name`, `phone`, or `email` (case-insensitive ILIKE).
5. Filter: `?role=buyer` filters by role. `?lifecycle_stage=active` filters by lifecycle stage.
6. Queries use existing `contacts` table with RLS.
7. *[ENG AC7]* Search term must be at least 2 characters — reject single-char searches with 422 `{"detail": "Search term must be at least 2 characters"}`.
8. *[ENG AC8]* Multiple filters are AND-combined (not OR). Document this in the API contract.
9. *[ENG AC9]* The response must NOT include sensitive fields like `consent_status`, `consent_granted_at`, `consent_message`, `consent_response`. Return only the specified fields.

#### Edge Cases

- Contacts with no `last_contact_at`: sort to the bottom (NULLS LAST).
- Large contact lists (500+): pagination prevents payload bloat.
- Search with special characters: sanitize input to prevent SQL injection (parameterized queries).

---

### MOB-CONTACT-002: View Contact Detail

**Priority:** P0 — Must-have
**Effort:** S (<1 day)

#### User Story

> As a real estate agent, I want to view a contact's full details, so that I can review their preferences, notes, and history before a meeting.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they GET `/api/v1/mobile/contacts/{id}`, **then** the server returns the full contact record plus their lead preferences (if any).
2. Response includes all columns from `contacts` plus a nested `preferences` object from `lead_preferences` (if the contact has a matching row).
3. Response also includes:
   - `recent_conversations`: last 5 conversations with this contact (id, last_message_at, last_message_body).
   - `upcoming_showings`: showings with status `'confirmed'` or `'hold'` where `start_time > now()`.
4. **Given** a contact_id not belonging to the agent, **when** they GET, **then** 404.
5. *[ENG AC4]* The contact response should exclude internal/sensitive fields: `consent_message`, `consent_response`, `preferences` (raw JSONB). Use `lead_preferences` for structured buyer data instead.
6. *[ENG AC5]* Each conversation in `recent_conversations` should include a `last_message_preview` (50 chars) for context.
7. *[ENG AC6]* Showings should include `listing_address` from the joined listings table.

#### Edge Cases

- Contact with no lead_preferences row: `preferences` is null in response.
- Contact with no conversations or showings: empty arrays.

---

## Epic 4: Briefing & Schedule

### MOB-BRIEF-001: Daily Briefing

**Priority:** P0 — Must-have
**Effort:** M (1-3 days)

#### User Story

> As a real estate agent, I want to see my daily briefing on my phone each morning, so that I know what needs my attention today without opening a laptop.

#### Background

The daily_scanner.py worker already generates briefing content each morning. This endpoint retrieves today's briefing data and assembles it into a mobile-friendly response. It does NOT reuse `compile_morning_briefing()` from `daily_scanner.py` directly — that function is synchronous, uses the sync DB pool, and returns a different shape. Instead, this endpoint uses new async queries tailored to the mobile response shape.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they GET `/api/v1/mobile/briefing/today`, **then** the server returns a structured briefing for today.
2. Response shape:
   ```json
   {
     "date": "2026-03-15",
     "timezone": "America/New_York",
     "generated_at": "ISO8601",
     "showings_today": [
       {"id": "uuid", "contact_name": "string", "listing_address": "string", "start_time": "ISO8601", "end_time": "ISO8601", "status": "confirmed"}
     ],
     "pending_approvals": [
       {"trigger_id": "uuid", "contact_name": "string", "message_preview": "string (100 chars)", "trigger_type": "string", "message_template": "string", "scheduled_at": "ISO8601"}
     ],
     "follow_ups_due": [
       {"trigger_id": "uuid", "contact_name": "string", "trigger_type": "string", "scheduled_at": "ISO8601"}
     ],
     "new_leads_since_yesterday": 3,
     "messages_received_today": 12,
     "active_transaction_count": 5
   }
   ```
3. "Today" is calculated in the agent's timezone (`agents.timezone` column).
4. Queries pull directly from `showings`, `triggers`, `contacts`, `messages`, and `transactions` tables. No dependency on daily_scanner output files.
5. *[ENG AC5]* Invalid/unknown timezone in agent record falls back to `America/New_York` with a warning log.
6. *[ENG AC6]* All 6 queries must use the async DB pool (`get_async_db_connection`). Use `asyncio.gather` for concurrent execution.
7. *[ENG AC7]* Response must include `generated_at` ISO timestamp for client-side cache decisions.
8. *[ENG AC8]* Each showing in `showings_today` must include `id`, `start_time`, `end_time`, `contact_name`, `listing_address`, `status`.
9. *[ENG AC9]* Each pending approval must include `trigger_id`, `trigger_type`, `message_template`, `contact_name`, `scheduled_at`.

#### Edge Cases

- Agent with no activity: all arrays empty, all counts zero. Still returns 200.
- Timezone edge case: agent in Hawaii (UTC-10) — "today" starts at 10:00 UTC. Queries must use timezone-aware date boundaries. Use `zoneinfo.ZoneInfo(agent.timezone)` to compute local day boundaries, then convert to UTC for DB comparisons.
- Agent with no timezone set: default to `America/New_York`.

---

### MOB-BRIEF-002: Today's Schedule

**Priority:** P1 — Should-have
**Effort:** S (<1 day)

#### User Story

> As a real estate agent, I want to see my schedule for today, so that I know where I need to be and when.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they GET `/api/v1/mobile/schedule/today`, **then** the server returns today's showings and any trigger-based events ordered by start time.
2. Response shape:
   ```json
   {
     "date": "2026-03-15",
     "timezone": "America/New_York",
     "events": [
       {
         "type": "showing",
         "id": "uuid",
         "title": "Showing: 123 Oak St",
         "contact_name": "string",
         "contact_id": "uuid",
         "start_time": "ISO8601",
         "end_time": "ISO8601",
         "status": "confirmed",
         "listing_address": "string",
         "listing_id": "uuid"
       }
     ]
   }
   ```
3. "Today" uses agent's timezone from `agents.timezone`.
4. Queries use existing `showings` and `listings` tables.
5. *[ENG AC3]* Cancelled showings are excluded (only include `confirmed`, `hold`, `pending` statuses).
6. *[ENG AC4]* `start_time` and `end_time` in response must be ISO 8601 with timezone offset (not naive datetimes).
7. *[ENG AC5]* Share timezone utility function with MOB-BRIEF-001 (single `get_agent_today_range()` helper in `app/api/mobile/utils.py`).

#### Edge Cases

- Agent with no showings today: empty `events` array, status 200.
- Showing that spans midnight: include if `start_time` falls on today.

---

## Epic 5: Real-Time

### MOB-RT-001: WebSocket for Live Conversation Updates

**Priority:** P1 — Should-have
**Effort:** L (3-5 days)

#### User Story

> As a real estate agent, I want to receive real-time updates when new messages arrive, so that I can respond to clients immediately without manually refreshing the app.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they connect to `WS /api/v1/mobile/ws/conversations` with their access token (sent as query param `?token=<jwt>`), **then** a WebSocket connection is established.
2. The server pushes events to the client when:
   - A new inbound message arrives for any of the agent's conversations.
   - An AI draft is generated and pending approval.
   - A message delivery status changes (sent, delivered, failed).
3. Event shape:
   ```json
   {
     "event": "new_message|draft_pending|delivery_update",
     "conversation_id": "uuid",
     "data": { "...message or status fields..." }
   }
   ```
4. Connection is authenticated: invalid or expired JWT closes the connection with code 4001.
5. Server sends a ping every 30 seconds; client must respond with pong within 10 seconds or the connection is closed.
6. **Implementation:** Use Redis pub/sub. The message pipeline publishes events to a channel `mobile:agent:{agent_id}`, and the WebSocket handler subscribes to that channel.
7. *[ENG AC7]* Async Redis pool must be initialized/closed in the FastAPI lifespan alongside DB pools. Use `redis.asyncio` (already included in the `redis[hiredis]` package).
8. *[ENG AC8]* WS endpoint must handle `WebSocketDisconnect` gracefully — clean up pub/sub subscription, log at INFO level (not ERROR).
9. *[ENG AC9]* All `publish_mobile_event()` calls in the pipeline must be wrapped in try/except — Redis failure must never block message processing.
10. *[ENG AC10]* Token expiry must be checked on each ping cycle (every 30s). If expired, close with code 4001.
11. *[ENG AC11]* Published events must be JSON-serialized with `json.dumps(default=str)` to handle UUID/datetime serialization.
12. *[ENG AC12]* Connection count per agent should be logged at DEBUG level for observability.

#### Edge Cases

- Token expires while WebSocket is open: close connection with code 4001 and `{"reason": "token_expired"}`. Client should reconnect with a refreshed token.
- Agent has multiple devices connected: all receive the same events (fan-out via Redis pub/sub).
- Redis unavailable: WebSocket connection attempt returns 503. Existing connections gracefully close.
- Brief network interruption: client reconnects and may request missed messages via the REST endpoint (no server-side message replay on WebSocket).
- Railway container restarts: WS connections will drop. Client must handle reconnection (client-side concern, document in API contract).

---

## Epic 6: Push Notifications

### MOB-PUSH-001: Device Token Registration

**Priority:** P0 — Must-have
**Effort:** S (<1 day)

#### User Story

> As a real estate agent, I want my phone to be registered for push notifications, so that I get alerted about new messages even when the app is closed.

#### Background

The `device_tokens` table already exists in the schema. The existing `firebase_service.py` already queries this table and sends notifications via FCM. This story is purely the registration endpoint.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they POST to `/api/v1/mobile/devices/register` with `{"fcm_token": "...", "device_name": "iPhone 15", "platform": "ios"}`, **then** the server upserts a row in `device_tokens` (matching on `fcm_token`). Response: `{"status": "registered"}` with status 200.
2. If the FCM token already exists for a different agent (device changed hands), update the `agent_id` to the current agent and set `is_active = true`.
3. If the FCM token already exists for the same agent, update `device_name`, `platform`, `is_active = true`, and `updated_at`.
4. **Given** an empty or missing `fcm_token`, **when** they POST register, **then** 422.
5. *[ENG AC5]* `platform` must be validated as non-empty string if provided. Accept any value (not just ios/android) for forward compatibility.
6. *[ENG AC6]* Response should include `device_id` (the UUID from device_tokens) for client-side reference: `{"status": "registered", "device_id": "uuid"}`.

#### Edge Cases

- Stale tokens: FCM will report unregistered tokens when we attempt to send. That cleanup is handled by the existing `firebase_service.py` — not in scope here.
- Multiple devices per agent: supported. Each device has its own token row.

#### Engineering Notes

- Wraps existing `firebase_service.register_device_token()` which handles the full upsert via `ON CONFLICT (fcm_token) DO UPDATE`.
- Use `run_in_executor` for the sync DB call (registration is low-frequency, latency is not critical).

---

### MOB-PUSH-002: Device Token Deregistration

**Priority:** P1 — Should-have
**Effort:** S (<1 day)

#### User Story

> As a real estate agent, I want to unregister my device when I log out, so that I stop receiving push notifications on a device I'm no longer using.

#### Acceptance Criteria

1. **Given** an authenticated agent, **when** they POST to `/api/v1/mobile/devices/unregister` with `{"fcm_token": "..."}`, **then** the server sets `is_active = false` on the matching `device_tokens` row. Response: `{"status": "unregistered"}` with status 200.
2. If the token does not exist or belongs to a different agent, return 200 (idempotent — no error, no information leakage).
3. This endpoint should be called during the logout flow (MOB-AUTH-003) by the client before revoking the auth token.
4. *[ENG AC4]* Empty `fcm_token` in request body returns 422.
5. *[ENG AC5]* Log the deregistration event at INFO level for observability.

#### Edge Cases

- Client fails to call this on logout: stale token remains active. Push delivery will fail silently via FCM, and the existing cleanup in `firebase_service.py` handles eventual deactivation.

---

### MOB-PUSH-003: Push Notification Dispatch for Mobile Events

**Priority:** P1 — Should-have
**Effort:** M (1-3 days)

#### User Story

> As a real estate agent, I want to receive push notifications when a new message arrives or an AI draft needs my approval, so that I can stay responsive to my clients even when the app is in the background.

#### Background

The `firebase_service.py` already has `send_push_notification()` which sends to all active device tokens for an agent. The trigger_worker already calls it for trigger events. This story extends push notification coverage to the message pipeline. **Note:** This is not a new endpoint — it is pipeline integration work within `app/pipeline/handlers.py`.

#### Acceptance Criteria

1. **Given** an inbound client message is processed through the pipeline, **when** the message is stored in the `messages` table, **then** a push notification is sent to the agent via `send_push_notification()` with tier `"informational"`, title `"New message from {contact_name}"`, and body containing the first 100 characters of the message.
2. **Given** an AI draft is generated in Supervised mode and stored as a pending trigger, **when** the trigger is created, **then** a push notification is sent with tier `"action_needed"`, title `"Draft ready for {contact_name}"`, and body containing the first 100 characters of the draft.
3. Push notifications include `conversation_id` in the data payload so the mobile app can deep-link to the correct conversation.
4. Push notifications respect the agent's `current_status` — if status is `"dnd"` (do not disturb), suppress informational notifications (only send `"urgent"` and `"action_needed"` tiers).
5. No push notification is sent if the agent has no active device tokens (no error, just skip).
6. *[ENG AC6]* DND suppression only applies to `informational` and `briefing` tiers. `action_needed` and `urgent` are always delivered regardless of DND status.
7. *[ENG AC7]* The `conversation_id` must be included in the FCM data payload (not just the notification body) for client-side deep linking.
8. *[ENG AC8]* Push dispatch code in handlers.py must be wrapped in `try/except Exception` with error logging — must never raise into the message pipeline.
9. *[ENG AC9]* Add `conversation_id: UUID | None = None` parameter to `send_push_notification()` signature.
10. *[ENG AC10]* When `current_status` is checked, also verify `status_until` — if `status_until` has passed, treat status as `available` (the trigger_worker reverts this, but there's a race window).

#### Edge Cases

- Agent is actively on the WebSocket: still send the push notification — the mobile client can suppress duplicate display client-side. Server-side dedup adds unnecessary complexity.
- Rapid-fire messages from same contact: no throttling in MVP. If this becomes noisy, we can add throttling later.
- Pipeline failure: push notification failure must not block message processing. Wrap in try/except and log errors.

---

## Backlog Summary

| ID | Story | Epic | Priority | Effort | Dependencies |
|----|-------|------|----------|--------|-------------|
| MOB-AUTH-001 | Agent Login (JWT Issuance) | Authentication | P0 | M | None |
| MOB-AUTH-002 | Token Refresh | Authentication | P0 | S | MOB-AUTH-001 |
| MOB-AUTH-003 | Logout (Token Revocation) | Authentication | P0 | S | MOB-AUTH-001 |
| MOB-AUTH-004 | JWT Authentication Middleware | Authentication | P0 | M | MOB-AUTH-001 |
| MOB-CONV-001 | List Conversations | Conversations | P0 | M | MOB-AUTH-004, schema change (`last_read_at`) |
| MOB-CONV-002 | View Conversation Messages | Conversations | P0 | M | MOB-AUTH-004 |
| MOB-CONV-003 | Approve AI Draft | Conversations | P0 | **L** | MOB-AUTH-004, trigger worker modification |
| MOB-CONV-004 | Edit AI Draft Before Sending | Conversations | P0 | **S** | MOB-AUTH-004 |
| MOB-CONV-005 | Reject AI Draft | Conversations | P0 | S | MOB-AUTH-004 |
| MOB-CONTACT-001 | List Contacts | Contacts | P0 | M | MOB-AUTH-004 |
| MOB-CONTACT-002 | View Contact Detail | Contacts | P0 | S | MOB-AUTH-004 |
| MOB-BRIEF-001 | Daily Briefing | Briefing & Schedule | P0 | M | MOB-AUTH-004 |
| MOB-BRIEF-002 | Today's Schedule | Briefing & Schedule | P1 | S | MOB-AUTH-004 |
| MOB-RT-001 | WebSocket for Live Updates | Real-Time | P1 | L | MOB-AUTH-004, async Redis pool |
| MOB-PUSH-001 | Device Token Registration | Push Notifications | P0 | S | MOB-AUTH-004 |
| MOB-PUSH-002 | Device Token Deregistration | Push Notifications | P1 | S | MOB-PUSH-001 |
| MOB-PUSH-003 | Push Notification Dispatch | Push Notifications | P1 | M | MOB-PUSH-001 |

### Totals

- **P0 stories:** 12
- **P1 stories:** 5
- **P2 stories:** 0
- **Estimated total effort (P0):** ~6 M + 1 L + 5 S = roughly 14-20 dev-days
- **Estimated total effort (P0+P1):** add ~1 L + 2 S + 1 M = roughly 20-28 dev-days

### Suggested Implementation Order

1. **MOB-AUTH-004** — Middleware first (everything depends on auth). Then **MOB-AUTH-001** (login), **MOB-AUTH-002** (refresh), **MOB-AUTH-003** (logout).
2. **Schema change** — Add `last_read_at` to conversations table.
3. **MOB-CONV-001 + MOB-CONV-002** — Core conversation viewing.
4. **MOB-CONV-005 + MOB-CONV-004** — Simple draft actions first (reject, edit).
5. **MOB-CONV-003** — Draft approval (includes trigger worker modification).
6. **MOB-CONTACT-001 + MOB-CONTACT-002** — Contact browsing.
7. **MOB-BRIEF-001** — Daily briefing.
8. **MOB-PUSH-001** — Device registration (unblocks push testing).
9. **MOB-BRIEF-002 + MOB-PUSH-002 + MOB-PUSH-003** — P1 items.
10. **MOB-RT-001** — WebSocket (most complex, least blocking for MVP).

---

## Changelog: v1 → v2

**Version 2.0 — Finalized after Engineering Review (2026-03-15)**

| Change | Details |
|--------|---------|
| **Status updated** | "Draft — Pending Engineering Review" → "Finalized — Ready for Stakeholder Approval" |
| **Prerequisites section added** | Documents PyJWT dependency, schema change (`last_read_at`), new file structure, and config additions required before implementation. |
| **PM Decisions section added** | Resolves 4 open questions from engineering: per-conversation unread tracking, 24-hour draft expiration, 2-char search minimum, trigger worker fix scoped within MOB-CONV-003. |
| **MOB-CONV-003 effort bumped to L** | Trigger worker modification required to handle `ask_agent` approval flow. Worker currently only processes `'pending'` status; needs to distinguish `ask_agent` holds from auto-fire triggers and process `'approved'` status. Prerequisite sub-task documented within the story. |
| **MOB-CONV-004 effort reduced to S** | Engineering assessment: trivial CRUD update to `triggers.message_template`. |
| **Engineering ACs added to all 17 stories** | Each story now includes tightened acceptance criteria from engineering review, marked with `[ENG AC-T#]` or `[ENG AC#]` prefix. These cover validation details, error handling, security, and implementation constraints. |
| **Engineering Notes added** | Key stories include implementation guidance covering reusable patterns, query approaches, and codebase references. |
| **Auth implementation order updated** | Changed from "MOB-AUTH-001 + MOB-AUTH-004 first" to "MOB-AUTH-004 (middleware) first, then MOB-AUTH-001, then MOB-AUTH-002, then MOB-AUTH-003" per engineering recommendation. |
| **MOB-AUTH-002 edge case updated** | Simplified replay attack handling: skip refresh token family tracking for v1. Consumed token returns 401. Revisit if multi-device usage warrants it. |
| **MOB-AUTH-004 Redis behavior specified** | Deny-list check fails open (allows request) if Redis is unavailable, with WARNING log. Prevents Redis outage from locking out all mobile users. |
| **MOB-CONV-001 schema dependency added** | `last_read_at TIMESTAMPTZ` column on conversations table required for unread count. Documented as explicit prerequisite. |
| **MOB-CONV-002 cursor pagination fixed** | Cursor must use `created_at` comparison, not UUID comparison (UUIDs from `gen_random_uuid()` are not sequential). |
| **MOB-BRIEF-001 response shape updated** | Added `timezone`, `generated_at`, and `message_template` to pending approvals. Specified async queries via `asyncio.gather`. |
| **MOB-BRIEF-002 response shape updated** | Added `contact_id`, `listing_id` to event shape. Specified cancelled showings are excluded. |
| **MOB-PUSH-001 response updated** | Now includes `device_id` in response for client-side reference. |
| **MOB-PUSH-003 clarified as pipeline integration** | Not a new endpoint — integration work within `handlers.py`. DND suppression scope clarified: only suppresses `informational` and `briefing` tiers. |
| **Backlog summary table updated** | MOB-CONV-003 → L, MOB-CONV-004 → S. Dependencies column updated to reflect schema change and trigger worker prerequisites. |
| **Effort totals updated** | P0: ~14-20 dev-days (was 12-16). P0+P1: ~20-28 dev-days (was 18-24). Increase driven by MOB-CONV-003 bump to L. |
