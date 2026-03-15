# Engineering Review: Mobile API — Briefing, Real-Time, Push Notifications

**Reviewer:** Atlas (Engineering Lead)
**Date:** 2026-03-15
**Stories Reviewed:** MOB-BRIEF-001, MOB-BRIEF-002, MOB-RT-001, MOB-PUSH-001, MOB-PUSH-002, MOB-PUSH-003

---

## Prerequisite: Mobile API Router & JWT Auth

These stories all reference endpoints under `/api/v1/mobile/`. Currently **no mobile API router exists** — the agent portal (`app/api/agent_portal.py`) uses cookie-based session auth at `/agent/*`. There is also no JWT infrastructure anywhere in the codebase (only Vapi webhook HMAC verification exists).

**Before any of these stories can be implemented**, the following must be in place (from the auth epic, presumably MOB-AUTH stories):

1. A new `app/api/mobile.py` router (or `app/api/mobile/` package) mounted at `/api/v1/mobile`
2. JWT issuance, validation, and refresh endpoints
3. A `get_current_agent` dependency that extracts agent_id from JWT bearer tokens
4. JWT secret configuration in `app/config.py`

This review assumes that auth infrastructure will exist when these stories are implemented. All effort estimates below **exclude** auth setup.

---

## MOB-BRIEF-001: Daily Briefing

### Feasibility: Can do as specified

### Technical Spec

**Approach:** New async endpoint in the mobile router. Does NOT reuse `compile_morning_briefing()` from `daily_scanner.py` directly — that function is synchronous, uses the sync DB pool, uses UTC instead of agent timezone, and returns a different shape (text-oriented for push notification body). Instead, write a new async query function tailored to the mobile response shape.

**Implementation:**
- New file: `app/api/mobile/briefing.py` (or section in `app/api/mobile.py`)
- Endpoint: `GET /api/v1/mobile/briefing/today`
- Dependency: `agent = Depends(get_current_agent)` provides agent_id + timezone
- Timezone handling: Use `agents.timezone` (defaults to `America/New_York` per schema). Compute `today_start` and `today_end` in agent's local timezone, then convert to UTC for DB queries. Use `zoneinfo.ZoneInfo` (stdlib, Python 3.9+).
- All queries use the async pool (`get_async_db_connection`)

**Queries (6 total, can be parallelized with `asyncio.gather`):**

1. **showings_today:** `SELECT s.*, c.name, l.address FROM showings s JOIN contacts c ... JOIN listings l ... WHERE s.agent_id = %s AND s.start_time BETWEEN %s AND %s AND s.status IN ('confirmed', 'hold') ORDER BY s.start_time` — uses existing index `idx_showings_agent_start`
2. **pending_approvals:** `SELECT t.*, c.name FROM triggers t LEFT JOIN contacts c ... WHERE t.agent_id = %s AND t.status = 'pending' AND t.autonomy_level = 'ask_agent'` — uses existing index `idx_triggers_status_agent_scheduled`
3. **follow_ups_due:** `SELECT t.* FROM triggers WHERE agent_id = %s AND scheduled_at BETWEEN %s AND %s AND status = 'pending' AND trigger_type IN ('gap_follow_up', 'proactive_follow_up')` — same index
4. **new_leads_since_yesterday:** `SELECT id, name, phone, lead_source FROM contacts WHERE agent_id = %s AND created_at >= %s ORDER BY created_at DESC` — uses `idx_contacts_agent_last_contact` (partial, but agent_id is leading)
5. **messages_received_today:** `SELECT COUNT(*) FROM messages WHERE agent_id = %s AND created_at >= %s AND sender_type = 'contact'` — uses `idx_messages_agent_created`
6. **active_transaction_count:** `SELECT COUNT(*) FROM transactions WHERE agent_id = %s AND status NOT IN ('closed', 'withdrawn', 'expired', 'fell_through')` — uses `idx_transactions_agent_status`

**Response schema (Pydantic):**
```python
class BriefingResponse(BaseModel):
    date: str  # "2026-03-15"
    timezone: str
    showings_today: list[ShowingSummary]
    pending_approvals: list[ApprovalSummary]
    follow_ups_due: list[FollowUpSummary]
    new_leads_since_yesterday: list[LeadSummary]
    messages_received_today: int
    active_transaction_count: int
```

**Existing code reuse:** The agent portal dashboard (`agent_portal.py` lines 220-318) already does very similar queries — messages_today, showings_today, pending_triggers, active_transactions. Use the same query patterns adapted for timezone-aware "today" and the mobile response shape.

### Effort Refinement: Agree with M (1-3 days)

6 queries + timezone logic + response models + tests. 2 days is realistic.

### Risks/Concerns

1. **Timezone correctness is the main risk.** The daily_scanner currently uses UTC for "today" calculations (line 71: `now = datetime.now(timezone.utc)`), which is wrong for agents in non-UTC timezones. The mobile endpoint must do this correctly. Use `zoneinfo.ZoneInfo(agent.timezone)` to compute local day boundaries, then convert to UTC for DB comparisons. All timestamps in the DB are TIMESTAMPTZ (UTC), so this is safe.
2. **Invalid timezone value** in `agents.timezone` — wrap `ZoneInfo()` in try/except and fall back to `America/New_York`.
3. **Performance:** 6 queries is fine — each hits an index. Consider `asyncio.gather` to run them concurrently within a single endpoint. Worst case on a cold DB is ~50ms total.

### Tightened Acceptance Criteria

- AC5: Invalid/unknown timezone in agent record falls back to `America/New_York` with a warning log.
- AC6: All 6 queries must use the async DB pool.
- AC7: Response must include `generated_at` ISO timestamp for client-side cache decisions.
- AC8: Each showing in `showings_today` must include `id`, `start_time`, `end_time`, `contact_name`, `listing_address`, `status`.
- AC9: Each pending approval must include `trigger_id`, `trigger_type`, `message_template`, `contact_name`, `scheduled_at`.

---

## MOB-BRIEF-002: Today's Schedule

### Feasibility: Can do as specified

### Technical Spec

**Approach:** Straightforward query endpoint. Very similar to the agent portal's `/agent/schedule` endpoint (lines 458-501 in `agent_portal.py`).

**Implementation:**
- Endpoint: `GET /api/v1/mobile/schedule/today`
- Single query joining showings + listings + contacts, filtered to agent's local "today"
- Same timezone approach as MOB-BRIEF-001

**Query:**
```sql
SELECT s.id, s.start_time, s.end_time, s.status,
       c.name as contact_name, c.id as contact_id,
       l.address as listing_address, l.id as listing_id
FROM showings s
JOIN contacts c ON s.contact_id = c.id
JOIN listings l ON s.listing_id = l.id
WHERE s.agent_id = %s
  AND s.start_time >= %s AND s.start_time < %s
  AND s.status NOT IN ('cancelled')
ORDER BY s.start_time
```

Uses existing index `idx_showings_agent_start`.

**Response schema:**
```python
class ScheduleResponse(BaseModel):
    date: str  # "2026-03-15"
    timezone: str
    events: list[ScheduleEvent]

class ScheduleEvent(BaseModel):
    type: str  # "showing" (extensible for future calendar events)
    id: UUID
    title: str  # "Showing at {address}"
    contact_name: str
    contact_id: UUID
    start_time: datetime
    end_time: datetime
    status: str
    listing_address: str
    listing_id: UUID
```

**Note on the PM's `type` field:** Currently we only have showings, not generic calendar events. The `type` field should default to `"showing"` for now, making it forward-compatible for Google Calendar integration later.

### Effort Refinement: Agree with S (<1 day)

Single query, one response model. Half a day including tests.

### Risks/Concerns

1. **Timezone:** Same approach as MOB-BRIEF-001 — use agent timezone for day boundaries. Share the timezone utility with the briefing endpoint (DRY).
2. **Midnight-spanning events:** PM says "include if start_time falls on today" — this is the correct and simplest approach. An event that starts at 11pm and ends at 1am tomorrow should appear on today's schedule. Document this in the response model.

### Tightened Acceptance Criteria

- AC3: Cancelled showings are excluded (only include `confirmed`, `hold`, `pending` statuses).
- AC4: `start_time` and `end_time` in response must be ISO 8601 with timezone offset (not naive).
- AC5: Share timezone utility function with MOB-BRIEF-001 (single `get_agent_today_range()` helper).

---

## MOB-RT-001: WebSocket for Live Conversation Updates

### Feasibility: Can do with modifications

### Technical Spec

**Approach:** FastAPI supports WebSocket endpoints natively via Starlette. However, the current codebase has **zero WebSocket usage** — no existing WS endpoints, no Redis pub/sub consumers, no async Redis client.

**Key infrastructure gap:** The Redis pool (`app/services/redis_pool.py`) uses the synchronous `redis` client. WebSocket + pub/sub requires an **async Redis client** (`redis.asyncio` or `aioredis`). This needs to be added.

**Implementation plan:**

1. **New dependency:** `redis[hiredis]` already includes `redis.asyncio` — no new pip dependency needed (verify in requirements.txt).

2. **New file:** `app/services/redis_async.py` — async Redis connection pool using `redis.asyncio.Redis`. Initialized in `lifespan()` alongside DB pools.

3. **New file:** `app/api/mobile/ws.py` — WebSocket endpoint.

4. **WebSocket auth flow:**
   - Client connects to `ws://host/api/v1/mobile/ws/conversations?token=<JWT>`
   - Server validates JWT from query param before accepting the connection
   - If invalid/expired → `websocket.close(code=4001, reason="auth_failed")`
   - Alternative: client sends JWT in first message. **Recommendation: use query param** — it's simpler and matches the PM spec. Query param is acceptable for WS because the token is short-lived and the connection is upgraded immediately.

5. **Redis pub/sub pattern:**
   ```python
   async def ws_conversations(websocket: WebSocket, token: str = Query(...)):
       agent_id = validate_jwt(token)  # raises on failure
       await websocket.accept()

       channel = f"mobile:agent:{agent_id}"
       pubsub = async_redis.pubsub()
       await pubsub.subscribe(channel)

       try:
           # Ping task + message listener run concurrently
           async with asyncio.TaskGroup() as tg:
               tg.create_task(_ping_loop(websocket))
               tg.create_task(_listen_loop(websocket, pubsub))
       finally:
           await pubsub.unsubscribe(channel)
           await pubsub.close()
   ```

6. **Publishing side:** Add a `publish_mobile_event()` helper that the message pipeline calls after storing an inbound message or creating a draft. This publishes to `mobile:agent:{agent_id}` via Redis. The publish call should be in `app/pipeline/handlers.py` (after message storage) and wherever drafts are created.

7. **Event shapes:**
   ```json
   {"event": "new_message", "conversation_id": "uuid", "data": {"contact_name": "...", "body": "...", "sender_type": "contact", "created_at": "..."}}
   {"event": "draft_pending", "conversation_id": "uuid", "data": {"contact_name": "...", "draft_body": "...", "trigger_id": "..."}}
   {"event": "delivery_update", "conversation_id": "uuid", "data": {"message_id": "uuid", "status": "delivered"}}
   ```

8. **Ping/pong:** Server sends ping every 30s. If client doesn't respond within 10s, close the connection. FastAPI/Starlette supports `websocket.send_json({"type": "ping"})` and client responds with `{"type": "pong"}`.

**Existing code to modify:**
- `app/main.py`: Add async Redis pool init/shutdown to lifespan
- `app/pipeline/handlers.py`: Add `publish_mobile_event()` calls after message storage
- `app/config.py`: Already has `REDIS_URL` — no changes needed

### Effort Refinement: Agree with L (3-5 days)

This is the largest story. Breakdown:
- Day 1: Async Redis pool, WS endpoint with auth, ping/pong
- Day 2: Redis pub/sub listener, publish helper, integration with message pipeline
- Day 3: Event shapes for all three event types, delivery_update integration
- Day 4: Testing (WS testing requires pytest fixtures with `httpx.AsyncClient` or `starlette.testclient.TestClient` WS support)
- Day 5: Edge cases, multi-device fan-out verification, error handling

4-5 days is realistic.

### Risks/Concerns

1. **Async Redis is the biggest new infrastructure addition.** The sync Redis pool works fine for current use (stream publishing, login codes). Adding an async pool introduces a second Redis connection manager. Keep it simple — single async Redis instance, initialized in lifespan.

2. **Connection lifecycle on Railway:** Railway containers can be restarted at any time. WS connections will drop. The client must handle reconnection. **This is a client-side concern**, but document it in the API contract.

3. **Memory pressure with many connections:** Each connected agent holds one WS connection + one Redis pub/sub subscription. For a solo-agent SaaS with <100 agents initially, this is a non-issue. At 1000+ agents, consider connection limits.

4. **No message replay (PM spec says this explicitly).** If a client disconnects and reconnects, they miss events that occurred while offline. This is acceptable for MVP — the briefing/schedule endpoints serve as the "catch-up" mechanism. Document this clearly.

5. **Token expiry mid-connection:** PM spec says close with 4001. Implementation approach: check token expiry on each ping cycle (every 30s). If expired, close. This avoids the complexity of a separate expiry-monitoring task.

6. **Pipeline integration risk:** `handlers.py` is described as 40K LOC. Adding publish calls needs to be surgical — identify the exact points where (a) inbound messages are stored, (b) AI drafts are created, (c) delivery status updates arrive. Each gets a `try/except` wrapped publish call that must never block the pipeline.

### Tightened Acceptance Criteria

- AC7: Async Redis pool must be initialized/closed in the FastAPI lifespan alongside DB pools.
- AC8: WS endpoint must handle `WebSocketDisconnect` gracefully — clean up pub/sub subscription, log at INFO level (not ERROR).
- AC9: All `publish_mobile_event()` calls in the pipeline must be wrapped in try/except — Redis failure must never block message processing.
- AC10: Token expiry must be checked on each ping cycle (every 30s). If expired, close with code 4001.
- AC11: Published events must be JSON-serialized with `json.dumps(default=str)` to handle UUID/datetime serialization.
- AC12: Connection count per agent should be logged at DEBUG level for observability.

---

## MOB-PUSH-001: Device Token Registration

### Feasibility: Can do as specified

### Technical Spec

**Approach:** Thin endpoint wrapping the existing `register_device_token()` function in `firebase_service.py` (lines 88-115). The function already handles the upsert logic exactly as specified — same agent re-register, different agent takeover, conflict resolution on `fcm_token` unique index.

**Implementation:**
- Endpoint: `POST /api/v1/mobile/devices/register`
- Request body: `{"fcm_token": "...", "device_name": "iPhone 15", "platform": "ios"}`
- Calls `firebase_service.register_device_token(agent_id, fcm_token, device_name, platform)`
- Returns `{"status": "registered"}` 200

**Existing code reuse:** `firebase_service.register_device_token()` does everything. The DB upsert uses `ON CONFLICT (fcm_token) DO UPDATE` which handles all three cases (new, same agent update, different agent takeover).

**One concern:** The existing function uses the **sync** DB pool (`get_db_connection()`). For the mobile API (async FastAPI handlers), we should either:
- (a) Call it via `run_in_executor` (simplest, acceptable for a low-frequency call), or
- (b) Write an async version.

**Recommendation:** Use `run_in_executor` for MVP. Registration happens once per app launch — latency is not critical.

**Validation:**
- `fcm_token` must be non-empty string → 422 if empty/missing
- `platform` should be one of `ios`, `android`, `web` → validate but don't reject unknown values (future-proof)
- `device_name` is optional

### Effort Refinement: Agree with S (<1 day)

Wrapper endpoint + validation + test. Half a day.

### Risks/Concerns

1. **RLS bypass:** `firebase_service.register_device_token()` does not set RLS context — it uses raw `agent_id` in the WHERE clause. This is correct because the upsert needs to potentially reassign tokens across agents (AC2: "Token exists for different agent → update agent_id"). RLS would block cross-agent updates. No change needed.

2. **Token length:** FCM tokens can be up to ~4KB. The `TEXT` column handles this fine. No length validation needed.

### Tightened Acceptance Criteria

- AC5: `platform` must be validated as non-empty string if provided. Accept any value (not just ios/android) for forward compatibility.
- AC6: Response should include `device_id` (the UUID from device_tokens) for client-side reference.

---

## MOB-PUSH-002: Device Token Deregistration

### Feasibility: Can do as specified

### Technical Spec

**Approach:** Thin endpoint wrapping `firebase_service.unregister_device_token()` (lines 118-125). The function already sets `is_active = false`.

**Implementation:**
- Endpoint: `POST /api/v1/mobile/devices/unregister`
- Request body: `{"fcm_token": "..."}`
- Calls `firebase_service.unregister_device_token(fcm_token)`
- Returns `{"status": "unregistered"}` 200

**Security concern:** The current `unregister_device_token()` does NOT verify that the token belongs to the requesting agent. It just sets `is_active = false` on any matching token. PM spec says "Token doesn't exist or belongs to different agent → 200 (idempotent)" which makes this acceptable — an agent can only deactivate tokens, not read or modify them. The worst case is an agent deactivating someone else's token, which is unlikely (they'd need the exact FCM token string) and low-impact (the other agent just re-registers on next app launch).

**Recommendation:** For MVP, accept the idempotent behavior as-is. For a future hardening pass, add `WHERE agent_id = %s` to the update query.

**Same sync/async consideration as MOB-PUSH-001:** Use `run_in_executor` for the sync DB call.

### Effort Refinement: Agree with S (<1 day)

Trivial wrapper. A few hours including tests.

### Risks/Concerns

1. **Ordering with token revocation (AC3):** PM says "Called during logout flow before token revocation." This is a client-side ordering concern. The endpoint itself is stateless and idempotent. Document in API contract that the client should call this before clearing local auth state.

### Tightened Acceptance Criteria

- AC4: Empty `fcm_token` in request body returns 422.
- AC5: Log the deregistration event at INFO level for observability.

---

## MOB-PUSH-003: Push Notification Dispatch for Mobile Events

### Feasibility: Can do as specified

### Technical Spec

**Approach:** This is not a new endpoint — it's **pipeline integration**. Add push notification dispatch calls at specific points in the message processing flow.

**Implementation points:**

1. **Inbound message → push notification:**
   - Location: `app/pipeline/handlers.py`, after inbound message is stored in the `messages` table
   - Call: `send_push_notification(agent_id, tier="informational", title=f"New message from {contact_name}", body=body[:100], data={"conversation_id": str(conversation_id)})`
   - Must check `agent.current_status` — if `"dnd"`, skip informational pushes
   - Wrap in try/except: push failure must NOT block message processing

2. **AI draft pending → push notification:**
   - Location: `app/pipeline/handlers.py`, after AI draft is created and stored with `delivery_status = 'draft_pending'` (or equivalent)
   - Call: `send_push_notification(agent_id, tier="action_needed", title=f"Draft ready for {contact_name}", body=draft_body[:100], data={"conversation_id": str(conversation_id)})`
   - `action_needed` tier is NOT suppressed by DND (agents still need to approve drafts)

3. **Data payload for deep linking:**
   - The existing `send_push_notification()` already supports a `data` dict parameter and already builds deep_link_url from contact_id
   - Add `conversation_id` to the data payload. Modify the function or pass it via the `data` parameter.

**Existing code reuse:**
- `firebase_service.send_push_notification()` handles everything — token lookup, FCM delivery, error handling, async/sync detection. Already has tier-based priority configuration.
- `TIER_CONFIG` already defines `informational` and `action_needed` tiers with appropriate priority/sound settings.

**DND status check:** Query `agents.current_status` before sending. The agent object is likely already loaded in the pipeline context. If `current_status == 'dnd'` and tier is `informational`, skip. If `current_status == 'dnd'` and tier is `action_needed` or `urgent`, still send.

**Modification to `send_push_notification()`:** Add `conversation_id` parameter (optional UUID) alongside existing `contact_id` and `listing_id`. Include it in the data payload as `conversation_id` and update `deep_link_url` to use conversation-based routing: `/conversations/{conversation_id}`.

### Effort Refinement: Agree with M (1-3 days)

The work is primarily in identifying the correct insertion points in handlers.py (40K LOC) and adding the calls with proper error handling. 1-2 days is realistic.

Breakdown:
- Day 1: Identify insertion points in handlers.py, add DND check helper, add push calls for inbound message + draft pending
- Day 2: Add conversation_id to push data payload, write tests, verify error isolation

### Risks/Concerns

1. **handlers.py is 40K LOC.** Finding the right insertion points requires careful code review. The inbound message storage point and draft creation point must be identified precisely. Recommend the implementer reads the full message flow before making changes.

2. **Performance:** `send_push_notification()` already handles async contexts by offloading FCM calls to a thread pool executor (lines 294-304 in firebase_service.py). This means push notification sending is non-blocking in the async pipeline. No performance concern.

3. **DND suppression scope:** PM says "suppress informational if dnd." Clarify: should `action_needed` also be suppressed during DND? **Recommendation:** Only suppress `informational` and `briefing` tiers during DND. Always deliver `action_needed` and `urgent`. This matches real-world expectations — an agent in DND still needs to know about pending drafts.

4. **Duplicate notifications:** PM spec says "Active WebSocket → still send push (client handles dedup)." This is the right call for MVP. Client-side dedup is simpler than server-side WS connection tracking.

### Tightened Acceptance Criteria

- AC6: DND suppression only applies to `informational` and `briefing` tiers. `action_needed` and `urgent` are always delivered.
- AC7: The `conversation_id` must be included in the FCM data payload (not just the notification body) for client-side deep linking.
- AC8: Push dispatch code in handlers.py must be wrapped in `try/except Exception` with error logging — must never raise into the message pipeline.
- AC9: Add `conversation_id: UUID | None = None` parameter to `send_push_notification()` signature.
- AC10: When `current_status` is checked, also verify `status_until` — if `status_until` has passed, treat status as `available` (the trigger_worker reverts this, but there's a race window).

---

## Cross-Story Technical Notes

### File Organization

Recommend organizing the mobile API as a package:

```
app/api/mobile/
    __init__.py          # Router aggregation
    auth.py              # JWT auth (from auth epic)
    briefing.py          # MOB-BRIEF-001, MOB-BRIEF-002
    devices.py           # MOB-PUSH-001, MOB-PUSH-002
    ws.py                # MOB-RT-001
```

Mount in `app/main.py` as:
```python
from app.api.mobile import router as mobile_router
app.include_router(mobile_router)
```

### Shared Utilities

Create `app/api/mobile/utils.py` for:
- `get_agent_today_range(timezone_str: str) -> tuple[datetime, datetime]` — used by both briefing and schedule endpoints
- Timezone validation/fallback logic

### Response Model Consistency

All mobile API responses should follow a consistent envelope. For these stories, the PM has specified flat responses (not wrapped in `{"data": ...}`). Keep it flat for simplicity — no envelope pattern needed for MVP.

### Testing Strategy

- **Briefing/Schedule:** Standard async endpoint tests with `httpx.AsyncClient`. Mock DB with known data, verify response shape and timezone calculations.
- **WebSocket:** Use `starlette.testclient.TestClient` which supports `with client.websocket_connect(url) as ws:` pattern. Test auth failure (4001), ping/pong, event delivery via direct Redis publish.
- **Push registration:** Test upsert logic via the existing `register_device_token()` function. Endpoint tests verify validation (empty token → 422).
- **Push dispatch:** Test in isolation — mock `send_push_notification()`, verify it's called with correct arguments at the right pipeline points. Test DND suppression.

### Dependency on Auth Epic

All six stories depend on JWT auth being implemented first. The implementation order should be:

1. **Auth infrastructure** (JWT, mobile router setup)
2. **MOB-PUSH-001 + MOB-PUSH-002** (device registration — no other dependencies, simple)
3. **MOB-BRIEF-002** (schedule — single query, simplest read endpoint)
4. **MOB-BRIEF-001** (briefing — 6 queries, more complex)
5. **MOB-PUSH-003** (push dispatch — requires pipeline integration, benefits from having device tokens registered)
6. **MOB-RT-001** (WebSocket — largest, most complex, benefits from everything else being in place)

---

## Summary Table

| Story | Feasibility | PM Effort | Eng Effort | Key Risk |
|-------|------------|-----------|------------|----------|
| MOB-BRIEF-001 | As specified | M (1-3d) | **M (2d)** | Timezone correctness |
| MOB-BRIEF-002 | As specified | S (<1d) | **S (0.5d)** | None significant |
| MOB-RT-001 | With modifications | L (3-5d) | **L (4-5d)** | Async Redis, pipeline integration, no existing WS infra |
| MOB-PUSH-001 | As specified | S (<1d) | **S (0.5d)** | None — wraps existing function |
| MOB-PUSH-002 | As specified | S (<1d) | **S (0.5d)** | None — wraps existing function |
| MOB-PUSH-003 | As specified | M (1-3d) | **M (1-2d)** | 40K LOC handlers.py insertion points |

**Total estimated effort: 8.5-10 days** (excluding auth infrastructure)

**Modifications required for MOB-RT-001:**
1. Add async Redis pool infrastructure (new file + lifespan init)
2. JWT validation via query param (not just bearer header) for WS auth
3. Pipeline integration for event publishing requires careful handlers.py surgery
