# PR: Mobile API Backend — Full Implementation

## Summary

Implements the complete Mobile API Backend (17 stories across 4 epics) to support the Calloway mobile app for solo real estate agents. All endpoints live under `/api/v1/mobile/` and are authenticated via JWT (access + refresh token pair).

## What Changed

### New Files

| File | Purpose |
|------|---------|
| `app/api/mobile/__init__.py` | Package init + router aggregation |
| `app/api/mobile/schemas.py` | Shared Pydantic schemas (`PaginationMeta`) |
| `app/api/mobile/deps.py` | JWT utilities, E.164 validation, `get_current_agent` dependency |
| `app/api/mobile/auth.py` | Login (SMS code), verify, refresh, logout endpoints |
| `app/api/mobile/conversations.py` | List conversations, view messages, approve/edit/reject AI drafts |
| `app/api/mobile/contacts.py` | List contacts with search/filters, contact detail with enrichment |
| `app/api/mobile/briefing.py` | Daily briefing (6 parallel queries), today's schedule |
| `app/api/mobile/devices.py` | FCM device token registration/deregistration with ownership scoping |
| `app/api/mobile/ws.py` | WebSocket for real-time conversation updates via Redis pub/sub |
| `app/api/mobile/utils.py` | Shared timezone utility (`get_agent_today_range`) |
| `app/services/redis_async.py` | Async Redis connection pool for WebSocket pub/sub |
| `app/db/migrations/015_add_last_read_at.sql` | Schema migration for unread tracking |
| `tests/test_mobile_deps.py` | Tests for JWT utilities, E.164 validation, auth dependency |
| `tests/test_mobile_auth.py` | Tests for login, verify, refresh, logout endpoints |
| `tests/test_mobile_conversations.py` | Tests for conversation list, messages, trigger approve/edit/reject |
| `tests/test_mobile_contacts.py` | Tests for contact list, search, filters, detail |
| `tests/test_mobile_briefing.py` | Tests for briefing and schedule endpoints |
| `tests/test_mobile_devices.py` | Tests for device register/unregister with ownership check |
| `tests/test_mobile_dispatcher_ws.py` | Tests for WebSocket event publishing from dispatcher |

### Modified Files

| File | Change |
|------|--------|
| `requirements.txt` | Added `pyjwt>=2.8,<3` |
| `app/config.py` | Added `MOBILE_JWT_SECRET` with production validation, dev auto-generation |
| `app/main.py` | Registered mobile router, async Redis lifecycle, OpenAPI tags |
| `app/worker/trigger_worker.py` | Fixed `ask_agent` approval flow — worker now skips `ask_agent` pending triggers and processes `approved` triggers |
| `app/pipeline/dispatcher.py` | Added WebSocket event publishing (`new_message`, `notification`, `pending_approval`) via `_publish_ws_event` helper |
| `app/services/firebase_service.py` | `unregister_device_token` now accepts optional `agent_id` for ownership-scoped deactivation |

## Epics Implemented

### Epic 1: Authentication (MOB-AUTH-001 through 004)
- SMS-based login with 6-digit code, anti-enumeration, rate limiting (5 attempts/15 min)
- JWT access tokens (HS256, 30-min) + opaque refresh tokens (30-day, Redis-backed)
- Token rotation on refresh, JTI deny-list for logout
- Fail-open Redis deny-list check per engineering spec

### Epic 2: Conversations (MOB-CONV-001 through 005)
- List conversations with unread counts, pending draft indicators, pagination
- View messages with dual pagination (cursor-based + offset-based), marks as read
- Approve/edit/reject AI drafts with 24h expiry, trigger worker integration

### Epic 3: Contacts (MOB-CONTACT-001, 002)
- List contacts with ILIKE search (min 2 chars, wildcard-escaped), AND-combined filters
- Contact detail with lead preferences, recent conversations, upcoming showings

### Epic 4: Briefing, Schedule, Push, WebSocket
- Daily briefing: 6 async parallel queries with timezone-aware day boundaries
- Today's schedule: non-cancelled showings with listing/contact enrichment
- Device token register/unregister wrapping existing Firebase service
- WebSocket at `/ws/conversations` with JWT auth, Redis pub/sub, 30s ping, token expiry re-check

## Code Review Findings Addressed

### Critical / Security
- Escaped ILIKE wildcards in contact search (C-2)
- Added JWT deny-list check to WebSocket auth (C-4)
- Added rate limiting on refresh endpoint — 10 attempts/15min per token (C-6)

### Important
- Fixed duplicate DB query in login endpoint
- Added missing expiry check on edit_trigger (C-7)
- Fixed briefing/schedule date to use agent's local timezone (I-3)
- Added LIMIT caps to unbounded briefing queries (I-1, I-2)
- Added Redis availability checks to refresh/logout (I-4)
- Auto-generate random JWT secret in development mode (I-7)
- Device token unregister now scoped to authenticated agent (I-6)
- SMS call in login wrapped in `run_in_executor` to avoid blocking event loop (I-8)

### Code Quality (Nitpicks)
- Extracted shared `PaginationMeta` to `app/api/mobile/schemas.py` (N-1)
- Fixed variable shadowing (`l` → `lead`) in briefing.py (N-2)
- Consistent `::uuid` casts in conversations.py queries (N-3)
- Module-level docstrings added to all mobile API files

### Pipeline Integration
- WebSocket events published from dispatcher on new messages, notifications, and pending approval triggers
- `_publish_ws_event` helper handles both async and sync calling contexts with fire-and-forget semantics

## Schema Changes
```sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMPTZ;
```

## Testing Status
- All files pass Python syntax validation
- Manual review completed by separate engineering agent
- 7 test files covering all mobile API modules (~2500 lines, 80+ test cases)
- Tests cover: auth flows, JWT lifecycle, rate limiting, conversation CRUD, trigger approval workflows, contact search/filters, briefing parallel queries, device ownership, and dispatcher WebSocket event publishing
