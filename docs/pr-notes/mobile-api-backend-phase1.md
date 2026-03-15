# PR: Mobile API Backend — Full Implementation

## Summary

Implements the complete Mobile API Backend (17 stories across 4 epics) to support the Calloway mobile app for solo real estate agents. All endpoints live under `/api/v1/mobile/` and are authenticated via JWT (access + refresh token pair).

## What Changed

### New Files

| File | Purpose |
|------|---------|
| `app/api/mobile/__init__.py` | Package init + router aggregation |
| `app/api/mobile/deps.py` | JWT utilities, E.164 validation, `get_current_agent` dependency |
| `app/api/mobile/auth.py` | Login (SMS code), verify, refresh, logout endpoints |
| `app/api/mobile/conversations.py` | List conversations, view messages, approve/edit/reject AI drafts |
| `app/api/mobile/contacts.py` | List contacts with search/filters, contact detail with enrichment |
| `app/api/mobile/briefing.py` | Daily briefing (6 parallel queries), today's schedule |
| `app/api/mobile/devices.py` | FCM device token registration/deregistration |
| `app/api/mobile/ws.py` | WebSocket for real-time conversation updates via Redis pub/sub |
| `app/api/mobile/utils.py` | Shared timezone utility (`get_agent_today_range`) |
| `app/services/redis_async.py` | Async Redis connection pool for WebSocket pub/sub |
| `app/db/migrations/015_add_last_read_at.sql` | Schema migration for unread tracking |

### Modified Files

| File | Change |
|------|--------|
| `requirements.txt` | Added `pyjwt>=2.8,<3` |
| `app/config.py` | Added `MOBILE_JWT_SECRET` with production validation, dev auto-generation |
| `app/main.py` | Registered mobile router, async Redis lifecycle, OpenAPI tags |
| `app/worker/trigger_worker.py` | Fixed `ask_agent` approval flow — worker now skips `ask_agent` pending triggers and processes `approved` triggers |

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
- Escaped ILIKE wildcards in contact search
- Added JWT deny-list check to WebSocket auth
- Fixed duplicate DB query in login endpoint
- Added missing expiry check on edit_trigger
- Fixed briefing/schedule date to use agent's local timezone
- Added LIMIT caps to unbounded briefing queries
- Added Redis availability checks to refresh/logout
- Auto-generate random JWT secret in development mode

## Schema Changes
```sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMPTZ;
```

## Testing Status
- All files pass Python syntax validation
- Manual review completed by separate engineering agent
- Test files not included (separate task)
