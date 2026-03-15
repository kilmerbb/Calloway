# Engineering Review: Mobile API — Conversations & Contacts (Epics 2-3)

**Reviewer:** Atlas (Engineering Lead)
**Date:** 2026-03-15
**Stories Reviewed:** MOB-CONV-001 through MOB-CONV-005, MOB-CONTACT-001, MOB-CONTACT-002

---

## Executive Summary

All seven stories are **feasible as specified**, with minor adjustments. The existing schema, query patterns, and agent portal code (`app/api/agent_portal.py`) already implement most of this logic for the HTMX-rendered portal. The mobile API endpoints are largely JSON-serialized versions of those same queries.

**Key findings:**
1. The trigger approval model described in MOB-CONV-003 does not match the current trigger worker behavior. This needs clarification and a small worker change.
2. No schema migrations are required — all needed columns and indexes already exist.
3. Auth for the mobile API should reuse the agent portal session mechanism (signed cookie or bearer token variant).
4. A new router file `app/api/mobile.py` should house all endpoints under `/api/v1/mobile/`.

---

## Architecture Decisions (Cross-Cutting)

### New File: `app/api/mobile.py`

All mobile endpoints go in a single new router file, registered in `app/main.py`. This follows the existing pattern where `agent_portal.py` groups all agent-facing routes.

```
app/api/mobile.py           — Router: /api/v1/mobile
app/services/mobile_queries.py  — Query layer (optional, can start inline)
```

### Authentication

The agent portal already has SMS-code-based auth (`app/api/agent_portal.py` lines 36-109) with session cookies via `itsdangerous`. For the mobile API:

- **Option A (recommended):** Reuse the same signed session cookie. The native app includes it in requests. Simplest path — zero new auth code.
- **Option B:** Add a `/api/v1/mobile/auth/token` endpoint that exchanges the SMS code for a bearer token (stored in Redis with TTL). More standard for mobile apps but more work.

Recommendation: Start with Option A (cookie). Migrate to bearer tokens in a future sprint if needed for token refresh or multi-device support. Either way, extract `_get_agent_id(request)` and `_require_agent(request)` into a shared utility so both `agent_portal.py` and `mobile.py` can use them.

### Response Format

All endpoints return JSON with a consistent envelope:

```json
{
  "data": [...],
  "pagination": {"total": 150, "page": 1, "per_page": 25, "pages": 6}
}
```

For single-resource endpoints, `data` is an object, not an array.

### RLS vs. Application-Level Filtering

The existing agent portal queries use `WHERE agent_id = %s` with explicit parameter binding (not RLS context). This is the correct pattern for the mobile API too — it avoids the overhead of `set_config` per request and is already proven safe. RLS remains as a defense-in-depth layer.

---

## Story-by-Story Review

---

### MOB-CONV-001: List Conversations

**Feasibility:** Can do as specified.

**Technical Spec:**

The agent portal already has this exact query at `app/api/agent_portal.py:279-289`:

```sql
SELECT cv.*, c.name as contact_name,
       (SELECT body FROM messages WHERE conversation_id = cv.id
        ORDER BY created_at DESC LIMIT 1) as last_message
FROM conversations cv
LEFT JOIN contacts c ON c.id = cv.contact_id
WHERE cv.agent_id = %s
ORDER BY cv.last_message_at DESC NULLS LAST
LIMIT 8
```

Changes needed for mobile:
1. Add `LEFT JOIN LATERAL` instead of correlated subquery for `last_message_body` (performance at scale).
2. Add `unread_count` — requires defining what "unread" means. The messages table has no `read_at` or `is_read` column. **This is a data model gap.** Options:
   - **Option A (recommended):** Add a `last_read_at TIMESTAMPTZ` column to the `conversations` table. Unread count = messages created after `last_read_at`. Simple, low storage cost, one ALTER TABLE.
   - **Option B:** Add `read_at` to messages table. More granular but expensive to count per-conversation.
3. Add `has_pending_draft` — subquery or lateral join against `triggers` table where `entity_id` matches the conversation's `contact_id`, `status = 'pending'`, `autonomy_level = 'ask_agent'`.
4. Truncate `last_message_body` to 150 chars via `LEFT(body, 150)`.
5. Add `c.phone as contact_phone` to the SELECT.

**Optimized query:**

```sql
SELECT
    cv.id, cv.contact_id, cv.channel, cv.stage, cv.last_message_at,
    COALESCE(c.name, c.phone) as contact_name,
    c.phone as contact_phone,
    lm.body_preview as last_message_body,
    COALESCE(unread.cnt, 0) as unread_count,
    EXISTS(
        SELECT 1 FROM triggers t
        WHERE t.entity_id = cv.contact_id
        AND t.entity_type = 'contact'
        AND t.status = 'pending'
        AND t.autonomy_level = 'ask_agent'
        AND t.agent_id = cv.agent_id
    ) as has_pending_draft
FROM conversations cv
LEFT JOIN contacts c ON c.id = cv.contact_id
LEFT JOIN LATERAL (
    SELECT LEFT(body, 150) as body_preview
    FROM messages
    WHERE conversation_id = cv.id
    ORDER BY created_at DESC
    LIMIT 1
) lm ON true
LEFT JOIN LATERAL (
    SELECT COUNT(*) as cnt
    FROM messages
    WHERE conversation_id = cv.id
    AND created_at > COALESCE(cv.last_read_at, '1970-01-01'::timestamptz)
    AND sender_type IN ('client', 'ai')
) unread ON true
WHERE cv.agent_id = %s
ORDER BY cv.last_message_at DESC NULLS LAST
LIMIT %s OFFSET %s
```

**Required schema change:**

```sql
ALTER TABLE conversations ADD COLUMN last_read_at TIMESTAMPTZ;
```

This is a non-breaking additive change. No migration needed for existing data — NULL means "never read" which correctly counts all messages as unread.

**Effort refinement:** Agree with M (1-3 days). The `last_read_at` addition and lateral join query require careful testing.

**Risks:**
- The lateral join for `has_pending_draft` scans triggers by `entity_id`. The existing index `idx_triggers_agent_entity(agent_id, entity_type, entity_id)` covers this efficiently.
- `unread_count` lateral join on messages is covered by `idx_messages_conversation_created`.

**Tightened acceptance criteria:**
- AC6: Response must include `contact_phone` for display when `contact_name` is null (deleted contact fallback).
- AC7: `last_message_body` must be HTML-escaped to prevent XSS if rendered raw.
- AC8: When `stage` filter is provided, validate against known values (`open`, `closed`, `snoozed`) — return 422 for unknown stages.
- AC9: Add `last_read_at` column to conversations table (schema change).

---

### MOB-CONV-002: View Conversation Messages

**Feasibility:** Can do as specified.

**Technical Spec:**

The agent portal already implements this at `app/api/agent_portal.py:440-444`:

```sql
SELECT * FROM messages WHERE conversation_id = %s ORDER BY created_at
```

Changes for mobile:
1. Add offset-based pagination (`page`/`per_page`) as primary, cursor-based (`before=<message_id>`) as secondary.
2. Return only specified fields, not `SELECT *`.
3. Ownership check: query conversation first to verify `agent_id`, return 404 if mismatch (existing pattern at line 427-438).
4. Include `failure_reason` when `delivery_status` is `failed` or `undelivered`.
5. **Side effect:** Mark conversation as read by updating `last_read_at = now()` when messages are fetched. This feeds MOB-CONV-001's `unread_count`.

**Cursor-based pagination approach:**

```sql
-- Cursor-based (for infinite scroll)
SELECT id, sender_type, body, ai_generated, delivery_status,
       CASE WHEN delivery_status IN ('failed', 'undelivered')
            THEN failure_reason END as failure_reason,
       created_at
FROM messages
WHERE conversation_id = %s
  AND (%s IS NULL OR id < %s)  -- cursor: before=<message_id>
ORDER BY created_at DESC
LIMIT %s
```

Note: For cursor-based, order is DESC (newest first, load-more fetches older). For offset-based, order is ASC (chronological). The client should specify which mode via the presence/absence of the `before` parameter.

**Effort refinement:** Agree with M. Cursor-based + offset-based dual pagination needs testing.

**Risks:**
- The `idx_messages_conversation_created` index covers the primary query path.
- For cursor-based pagination using `id < %s`, we need the messages to have monotonically increasing UUIDs (they use `gen_random_uuid()`, which is NOT sequential). **This is a problem.** Cursor should use `created_at < (SELECT created_at FROM messages WHERE id = %s)` instead of `id < %s`.

**Tightened acceptance criteria:**
- AC6: When `before` parameter is present, ignore `page`/`per_page` and use cursor-based pagination with `per_page` as limit (default 50).
- AC7: Cursor-based returns messages in reverse chronological order; offset-based returns chronological. Document this difference.
- AC8: Viewing messages updates `conversations.last_read_at = now()` to reset unread count.
- AC9: Cursor must use `created_at` comparison, not UUID comparison (UUIDs are not sequential).

---

### MOB-CONV-003: Approve AI Draft

**Feasibility:** Can do with modifications.

**Technical Spec:**

The agent portal already has approve at `app/api/agent_portal.py:627-654`:

```sql
UPDATE triggers SET status = 'approved'
WHERE id = %s AND agent_id = %s AND status = 'pending'
RETURNING id
```

**Critical issue: The trigger worker does not process 'approved' triggers.**

The trigger worker (`app/worker/trigger_worker.py:59-73`) only picks up `status = 'pending'`. When the agent portal sets a trigger to `'approved'`, it's in a terminal state — the worker never acts on it. This means the current approve flow is broken (or at minimum, the approved trigger's message is never sent).

**The PM story says:** "trigger_worker picks it up" after approval. This is not how the code currently works.

**Fix required (pick one):**

- **Option A (recommended):** Change the worker query to also pick up `'approved'` triggers:
  ```sql
  WHERE status IN ('pending', 'approved') AND scheduled_at <= %s
  ```
  And for `ask_agent` triggers with `status = 'pending'`, the worker should skip them (don't fire, just notify). Only fire `ask_agent` triggers when `status = 'approved'`. This aligns with the PM's intent.

- **Option B:** Keep the worker as-is. Change approve to: set `status = 'pending'` + `scheduled_at = now()` so the worker picks it up on next cycle. Hacky but zero worker changes.

**Recommendation:** Option A. Modify the trigger worker to handle the `ask_agent` approval flow correctly:
1. Worker picks up `pending` triggers where `autonomy_level != 'ask_agent'` OR `approved` triggers (any autonomy level).
2. For `ask_agent` + `pending`: send push notification, set to `'awaiting_approval'` (not `'fired'`).
3. For `approved`: fire the message, set to `'fired'`.

This is a **prerequisite** for MOB-CONV-003 and should be scoped as a separate sub-task.

**Effort refinement:** Upgrade to L (3-5 days). The trigger worker modification is meaningful and requires careful testing to avoid breaking existing auto-fire triggers.

**Risks:**
- Modifying trigger worker is high-risk (production background process). Needs thorough test coverage.
- Race condition: agent approves while worker is mid-cycle. The `FOR UPDATE SKIP LOCKED` pattern handles this — the approve endpoint should also use row locking or an atomic CAS update.

**Tightened acceptance criteria:**
- AC4: Trigger worker must be modified to distinguish `ask_agent` pending (hold for approval) from auto pending (fire immediately).
- AC5: The approve endpoint must be idempotent within a reasonable window — if the trigger was already approved and is being processed, return 200 (not 409).
- AC6: Add `message_template` to the response so the agent can see what they're approving: `{"status": "approved", "trigger_id": "uuid", "message_preview": "..."}`.
- AC7: Expired trigger definition: `scheduled_at < now() - interval '24 hours'` AND still pending. The 410 Gone response should include `expired_at`.

---

### MOB-CONV-004: Edit AI Draft Before Sending

**Feasibility:** Can do as specified.

**Technical Spec:**

Straightforward update to `triggers.message_template`:

```sql
UPDATE triggers
SET message_template = %s
WHERE id = %s AND agent_id = %s AND status = 'pending'
RETURNING id, message_template
```

Validation:
- Strip whitespace, check non-empty after strip.
- Check `len(body) <= 1600` (SMS segment limit consideration).
- Reject if only whitespace: `body.strip() == ""`.

No existing code does this — it's a new endpoint.

**Effort refinement:** Agree with S (<1 day). Trivial CRUD.

**Risks:** None significant.

**Tightened acceptance criteria:**
- AC4: The response should include the updated `message_template` for confirmation: `{"status": "updated", "trigger_id": "uuid", "body": "..."}`.
- AC5: Body length validation should count characters, not bytes (Unicode-safe). Python's `len()` on `str` is character-count, which is correct.
- AC6: Newlines are acceptable in the body (multi-line SMS).

---

### MOB-CONV-005: Reject AI Draft

**Feasibility:** Can do as specified.

**Technical Spec:**

The agent portal already has reject at `app/api/agent_portal.py:657-683`:

```sql
UPDATE triggers SET status = 'cancelled'
WHERE id = %s AND agent_id = %s AND status = 'pending'
RETURNING id
```

The mobile endpoint is a direct JSON translation. Note the response says `"status": "rejected"` but the DB value is `'cancelled'`. This is fine — the API can map terminology for the client.

**Effort refinement:** Agree with S (<1 day). Near-identical to the existing portal endpoint.

**Risks:** None.

**Tightened acceptance criteria:**
- AC4: Consistent with MOB-CONV-003 on edge cases — expired trigger should return 410, same definition.

---

### MOB-CONTACT-001: List Contacts

**Feasibility:** Can do as specified.

**Technical Spec:**

The agent portal already has this at `app/api/agent_portal.py:323-373`:

```sql
SELECT * FROM contacts WHERE agent_id = %s
  [AND role = %s]
  [AND lead_source = %s]
  [AND (name ILIKE %s OR phone ILIKE %s OR email ILIKE %s)]
ORDER BY last_contact_at DESC NULLS LAST
```

Changes for mobile:
1. Select only needed fields (not `SELECT *`).
2. Add pagination (LIMIT/OFFSET with count query).
3. Add `lifecycle_stage` filter (agent portal only has `role` and `lead_source`).
4. ILIKE search is already implemented — reuse the pattern.

**Search performance note:** ILIKE with leading `%` wildcard (`%term%`) cannot use B-tree indexes. For 500 contacts this is fine (<10ms). For 5000+ contacts, consider `pg_trgm` GIN index. Not needed now — premature optimization.

**Effort refinement:** Agree with M. Pagination count query + multiple filters need testing.

**Risks:**
- The existing index `idx_contacts_agent_last_contact(agent_id, last_contact_at)` covers the sort order.
- No index on `name` or `email` for ILIKE search, but acceptable at expected scale.

**Tightened acceptance criteria:**
- AC7: Search term must be at least 2 characters — reject single-char searches to avoid overly broad results.
- AC8: Multiple filters are AND-combined (not OR). Document this.
- AC9: The response should NOT include sensitive fields like `consent_status`, `consent_granted_at`, etc. Return only the specified fields.

---

### MOB-CONTACT-002: View Contact Detail

**Feasibility:** Can do as specified.

**Technical Spec:**

This is a composite endpoint — one query for the contact, plus joins/subqueries for related data:

```sql
-- 1. Contact + preferences
SELECT c.*, lp.*
FROM contacts c
LEFT JOIN lead_preferences lp ON lp.contact_id = c.id
WHERE c.id = %s AND c.agent_id = %s

-- 2. Recent conversations (last 5)
SELECT id, channel, stage, last_message_at
FROM conversations
WHERE contact_id = %s AND agent_id = %s
ORDER BY last_message_at DESC NULLS LAST
LIMIT 5

-- 3. Upcoming showings
SELECT s.id, s.start_time, s.end_time, s.status, l.address as listing_address
FROM showings s
JOIN listings l ON l.id = s.listing_id
WHERE s.contact_id = %s AND s.agent_id = %s
AND s.status IN ('confirmed', 'hold')
AND s.start_time > now()
ORDER BY s.start_time
LIMIT 10
```

These can run as three sequential queries within one connection (no need for parallelism at this scale), or be combined into a single query with JSON aggregation. Sequential is simpler and easier to debug.

The agent portal doesn't have a contact detail view with this level of enrichment, so this is new logic.

**Effort refinement:** Agree with S (<1 day). Three straightforward queries, JSON assembly.

**Risks:**
- `lead_preferences` uses RLS via a subquery on `contacts.agent_id`. Since we're already filtering `contacts.agent_id = %s`, the LEFT JOIN will work correctly without setting RLS context.
- The showings query uses `idx_showings_agent_start(agent_id, start_time)` — efficient.

**Tightened acceptance criteria:**
- AC4: The contact response should exclude internal/sensitive fields: `consent_message`, `consent_response`, `preferences` (raw JSONB). Use `lead_preferences` for structured buyer data instead.
- AC5: Each conversation in `recent_conversations` should include a `last_message_preview` (50 chars) for context.
- AC6: Showings should include `listing_address` from the joined listings table.

---

## Summary of Required Changes

### Schema Changes (1)
| Change | Table | Migration |
|--------|-------|-----------|
| Add `last_read_at TIMESTAMPTZ` | conversations | `ALTER TABLE conversations ADD COLUMN last_read_at TIMESTAMPTZ;` |

### New Files (1-2)
| File | Purpose |
|------|---------|
| `app/api/mobile.py` | All mobile API endpoints, router prefix `/api/v1/mobile` |
| `app/services/mobile_queries.py` | (Optional) Query layer if queries grow complex |

### Modified Files (2)
| File | Change |
|------|--------|
| `app/main.py` | Register mobile router |
| `app/worker/trigger_worker.py` | Handle `ask_agent` approval flow (prerequisite for MOB-CONV-003) |

### Effort Summary

| Story | PM Estimate | Eng Estimate | Delta | Reason |
|-------|-------------|--------------|-------|--------|
| MOB-CONV-001 | M (1-3d) | M (2d) | — | Lateral joins + unread_count needs schema change |
| MOB-CONV-002 | M (1-3d) | M (2d) | — | Dual pagination modes need testing |
| MOB-CONV-003 | M (1-3d) | L (3-5d) | +1 size | Trigger worker modification is high-risk |
| MOB-CONV-004 | M (1-3d) | S (<1d) | -1 size | Trivial CRUD update |
| MOB-CONV-005 | S (<1d) | S (<1d) | — | Direct port from portal |
| MOB-CONTACT-001 | M (1-3d) | M (1-2d) | — | Reuses portal patterns |
| MOB-CONTACT-002 | S (<1d) | S (<1d) | — | Three simple queries |

**Total estimated effort:** 8-12 days for all 7 stories.

### Implementation Order (Recommended)

1. **Schema change** — Add `last_read_at` to conversations (blocks MOB-CONV-001)
2. **Trigger worker fix** — Modify `ask_agent` handling (blocks MOB-CONV-003)
3. **Scaffold** — Create `app/api/mobile.py`, register router, extract shared auth utils
4. **MOB-CONTACT-001** + **MOB-CONTACT-002** — Simplest, builds confidence
5. **MOB-CONV-001** — List conversations (depends on schema change)
6. **MOB-CONV-002** — View messages (depends on MOB-CONV-001 for read tracking)
7. **MOB-CONV-005** → **MOB-CONV-004** → **MOB-CONV-003** — Draft actions (003 depends on worker fix)

### Open Questions for PM

1. **Unread tracking:** Is `last_read_at` per-conversation sufficient, or do we need per-message read receipts? Per-conversation is simpler and recommended.
2. **Draft expiration window:** What's the TTL for a pending `ask_agent` trigger before it's considered expired (410 Gone)? Recommend 24 hours.
3. **Search minimum length:** Is a 2-character minimum for contact search acceptable?
4. **Trigger worker scope:** Should the trigger worker fix be a separate story/ticket? It's a prerequisite for MOB-CONV-003 but affects production background processing.
