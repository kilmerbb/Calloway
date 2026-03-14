# Performance Optimization — Engineering Review

**Reviewer:** Atlas (Engineering Lead)
**Date:** 2026-03-14
**Stories reviewed:** PERF-001 through PERF-008
**Source files examined:**
- `app/services/console_queries.py` (full file, ~1462 lines)
- `app/api/console.py` (full file, ~1145 lines)
- `app/db/schema.sql` (full schema, indexes, RLS policies)
- `app/db/connection.py` (sync + async pool, connection patterns)
- `app/services/cache.py` (generic Redis cache layer)
- `app/services/redis_pool.py` (shared Redis connection pool)
- `app/services/agent_config.py` (existing Redis caching pattern for agents)

---

## Summary

All 8 stories are feasible. The diagnosed bottlenecks are real and verified in the source code. I have specific modifications and technical specs for each. Two stories need scope adjustments, and several acceptance criteria need tightened or relaxed targets.

**Total estimated effort:** 12-18 days (if done sequentially). Parallelizable to ~8-10 days with 2 engineers.

---

## PERF-001: Optimize `get_all_agents()` + Redis Caching

**Feasibility:** Can do as specified

### Verified Bottleneck

The query at line 224-248 of `console_queries.py` runs three LEFT JOIN subqueries that each perform full-table scans:
1. `SELECT agent_id, COUNT(*) FROM contacts GROUP BY agent_id` — scans entire contacts table
2. `SELECT agent_id, SUM(...), MAX(date) FROM usage_metrics GROUP BY agent_id` — scans entire usage_metrics table
3. `SELECT agent_id, COUNT(*) FROM tool_executions WHERE error_message IS NOT NULL AND created_at > now() - interval '24 hours' GROUP BY agent_id` — scans 24h of tool_executions

Called on 4 routes: `tenant_list`, `conversation_list`, `trigger_list`, `health_overview`.

### Technical Spec

**Query optimization — no rewrite needed.** The current query structure (LEFT JOIN on pre-aggregated subqueries) is actually the correct pattern. The subqueries are not correlated — they aggregate once and join. The issue is lack of caching, not query structure. PostgreSQL will execute each subquery once, not per-row. With proper indexes (PERF-006), the cold query should run in under 500ms for <50 agents.

**Redis caching — use existing `cache.py` module.** Do NOT create a new Redis connection. The codebase already has `app/services/cache.py` with `cache_get`, `cache_set`, `cache_invalidate` functions backed by `app/services/redis_pool.py`.

Implementation approach:
```python
import json
from app.services.cache import cache_get, cache_set, cache_invalidate

AGENTS_CACHE_KEY = "console:agents:all"
AGENTS_CACHE_TTL = 60  # seconds

async def get_all_agents() -> list[AgentSummary]:
    cached = cache_get(AGENTS_CACHE_KEY)
    if cached:
        logger.debug("get_all_agents: cache hit")
        return json.loads(cached)

    # ... existing query ...

    # Serialize: psycopg dict_row returns dicts, but UUIDs/dates need str conversion
    cache_set(AGENTS_CACHE_KEY, json.dumps(rows, default=str), ttl=AGENTS_CACHE_TTL)
    logger.debug("get_all_agents: cache miss, populated")
    return rows
```

**Cache invalidation** — add `cache_invalidate(AGENTS_CACHE_KEY)` to:
- `create_agent_tenant()` (line 996)
- `create_agent_from_wizard()` (line 844)
- `update_agent_tenant()` (line 1049)
- `deactivate_agent()` (line 1093)

**Lightweight `get_agent_options()` — agreed, add this.** Three of the four routes (conversations, triggers, health) only need agent `id` and `name` for dropdown filters. Create:
```python
AGENT_OPTIONS_CACHE_KEY = "console:agents:options"
AGENT_OPTIONS_CACHE_TTL = 300  # 5 minutes — changes very rarely

async def get_agent_options() -> list[dict]:
    cached = cache_get(AGENT_OPTIONS_CACHE_KEY)
    if cached:
        return json.loads(cached)
    async with get_async_db_connection() as conn:
        cur = await conn.execute("SELECT id, name FROM agents ORDER BY name")
        rows = await cur.fetchall()
    cache_set(AGENT_OPTIONS_CACHE_KEY, json.dumps(rows, default=str), ttl=AGENT_OPTIONS_CACHE_TTL)
    return rows or []
```

### Tightened Acceptance Criteria

- AC4 target of "under 2 seconds warm cache" is easily achievable — Redis GET is <1ms. **Tighten to: under 500ms warm cache, under 3 seconds cold cache.** The cold cache target depends on PERF-006 indexes being in place.
- AC2: Serialization must handle UUID and datetime objects. Use `json.dumps(rows, default=str)`. On deserialization, the templates receive strings instead of UUID/datetime objects — verify templates use string comparison or add a deserializer.

### Risks

- **Serialization of dict_row results.** psycopg `dict_row` returns Python dicts with native UUID and datetime types. `json.dumps(default=str)` works for serialization, but deserialization returns strings. The templates and the `/tenants` route's in-memory search filter (`search.lower() in a["name"].lower()`) will work fine with strings. The JSON API response also only uses `id` and `name`. **Low risk.**
- **Cache staleness window.** 60-second TTL means a newly created agent may not appear for up to 60 seconds. Acceptable for this admin console. The explicit invalidation on create/update/deactivate handles the common case.

### Effort: S (< 1 day)

---

## PERF-002: Optimize `get_recent_conversations()` + Pagination

**Feasibility:** Can do as specified

### Verified Bottleneck

The query at lines 367-381 contains two correlated subqueries in the SELECT clause:
```sql
(SELECT COUNT(*) FROM messages WHERE conversation_id = cv.id) as msg_count,
(SELECT body FROM messages WHERE conversation_id = cv.id
 ORDER BY created_at DESC LIMIT 1) as last_message
```

These execute once per row in the result set. With LIMIT 100, that is 200 correlated subqueries. The `idx_messages_conversation_created` index on `(conversation_id, created_at)` helps, but the sheer volume is the problem.

### Technical Spec

**Replace correlated subqueries with a LATERAL JOIN:**

```sql
SELECT cv.id, cv.channel, cv.last_message_at,
       a.name as agent_name, c.name as contact_name, c.phone,
       COALESCE(msg_stats.msg_count, 0) as msg_count,
       msg_stats.last_message
FROM conversations cv
JOIN agents a ON cv.agent_id = a.id
LEFT JOIN contacts c ON cv.contact_id = c.id
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS msg_count,
           (SELECT body FROM messages m2
            WHERE m2.conversation_id = cv.id
            ORDER BY m2.created_at DESC LIMIT 1) AS last_message
    FROM messages m
    WHERE m.conversation_id = cv.id
) msg_stats ON true
{where}
ORDER BY cv.last_message_at DESC NULLS LAST
LIMIT %s OFFSET %s
```

Actually, a cleaner approach — use a window function CTE:

```sql
WITH msg_stats AS (
    SELECT conversation_id,
           COUNT(*) AS msg_count,
           MAX(created_at) AS last_msg_at
    FROM messages
    GROUP BY conversation_id
),
last_msgs AS (
    SELECT DISTINCT ON (conversation_id)
           conversation_id, body AS last_message
    FROM messages
    ORDER BY conversation_id, created_at DESC
)
SELECT cv.id, cv.channel, cv.last_message_at,
       a.name AS agent_name, c.name AS contact_name, c.phone,
       COALESCE(ms.msg_count, 0) AS msg_count,
       lm.last_message
FROM conversations cv
JOIN agents a ON cv.agent_id = a.id
LEFT JOIN contacts c ON cv.contact_id = c.id
LEFT JOIN msg_stats ms ON ms.conversation_id = cv.id
LEFT JOIN last_msgs lm ON lm.conversation_id = cv.id
{where}
ORDER BY cv.last_message_at DESC NULLS LAST
LIMIT %s OFFSET %s
```

**Wait — the CTE approach scans the entire messages table.** For a system with millions of messages, this is worse. Better approach: keep the correlated subqueries but add the `conversations(last_message_at DESC NULLS LAST)` index from PERF-006, so the outer query uses an index scan to get the top N conversations first, and only then evaluates the correlated subqueries for those N rows. With proper LIMIT and the index, PostgreSQL will only execute the subqueries for the rows it actually returns.

**Recommended approach:** Keep the correlated subqueries (they are efficient with the existing `idx_messages_conversation_created` index — each lookup is an index scan). The real fix is:
1. Add pagination (reduce from 100 to 25 per page)
2. Add the `conversations(last_message_at DESC NULLS LAST)` index from PERF-006 so the ORDER BY does not require a full table sort
3. Optionally, denormalize `message_count` and `last_message_body` onto the `conversations` table if performance is still insufficient after indexing

**Pagination implementation:**

In `console.py` route `conversation_list` (line 432):
```python
page = int(request.query_params.get("page", "1"))
per_page = int(request.query_params.get("per_page", "25"))
offset = (page - 1) * per_page
```

Pass `limit=per_page, offset=offset` to `get_recent_conversations()`.

Add `offset` parameter to `get_recent_conversations()`:
```python
async def get_recent_conversations(
    agent_id: str | None = None,
    channel: str | None = None,
    search: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> list[ConversationRow]:
```

Add `OFFSET %s` to the query, pass `params + [limit, offset]`.

### Tightened Acceptance Criteria

- AC3: "Under 2 seconds" is achievable with pagination to 25 rows + the PERF-006 index. Keep as-is.
- Add AC6: **Default per_page is 25, not 100.** The current hardcoded `limit=100` in the route is the primary source of slowness.

### Risks

- **ILIKE search without index.** The search filter uses `c.name ILIKE %s OR c.phone ILIKE %s` which cannot use a standard B-tree index. For the current scale (<50 agents, <10K conversations), this is acceptable. If it becomes a problem, add a `pg_trgm` GIN index. **Low risk for current scale.**
- **Offset-based pagination degrades at high page numbers.** For this admin console use case, operators will rarely paginate beyond page 10. Keyset pagination would be better but is premature optimization here.

### Effort: M (1-2 days) — query changes + pagination template + filter preservation

---

## PERF-003: Fix N+1 in `get_conversations_by_contact()`

**Feasibility:** Can do with modifications

### Verified Bottleneck

The query at lines 1165-1192 has two performance issues:
1. **Correlated subquery for `last_message_preview`** (lines 1173-1179): Scans messages for every contact group using a correlated subquery that re-filters by `agent_id` and `contact_id`.
2. **`JOIN LATERAL` for per-conversation counts** (lines 1182-1184): Counts messages per conversation, then aggregates. This is not technically N+1 — it runs once per conversation row before grouping, which is reasonable.

The correlated subquery is the real issue. It joins messages to conversations and filters by agent_id and a condition on contact_id that cannot use the existing `idx_conversations_agent_contact` index efficiently because of the `OR ... IS NULL` branch.

### Technical Spec

Replace the correlated subquery with a CTE or window function:

```sql
WITH latest_msg AS (
    SELECT DISTINCT ON (cv.contact_id)
           cv.contact_id,
           m.body AS last_message_preview
    FROM messages m
    JOIN conversations cv ON m.conversation_id = cv.id
    WHERE cv.agent_id = %s
    ORDER BY cv.contact_id, m.created_at DESC
)
SELECT
    COALESCE(c.id::text, 'unknown') AS contact_id,
    COALESCE(c.name, 'Unknown Contact') AS contact_name,
    COALESCE(c.phone, '') AS phone,
    array_agg(DISTINCT cv.channel) AS channels,
    SUM(sub.msg_count)::int AS message_count,
    MAX(sub.last_msg_at) AS last_message_at,
    lm.last_message_preview
FROM conversations cv
LEFT JOIN contacts c ON cv.contact_id = c.id
JOIN LATERAL (
    SELECT COUNT(*) AS msg_count, MAX(m.created_at) AS last_msg_at
    FROM messages m WHERE m.conversation_id = cv.id
) sub ON true
LEFT JOIN latest_msg lm ON lm.contact_id = c.id
WHERE cv.agent_id = %s
  AND sub.msg_count > 0
GROUP BY c.id, c.name, c.phone, lm.last_message_preview
ORDER BY MAX(sub.last_msg_at) DESC NULLS LAST
LIMIT %s OFFSET %s
```

This runs the latest-message lookup once as a CTE (using `DISTINCT ON` which is index-friendly with `idx_messages_conversation_created`), then joins the result.

**Parameter change:** The `agent_id` is now passed once for the CTE and once for the WHERE clause (2 params instead of the current 2), but the correlated subquery no longer receives it. Net: same number of params, but the expensive work is done once.

### Tightened Acceptance Criteria

- AC2: "Under 1 second for 200 contacts" — achievable with the CTE approach + PERF-006 indexes. Keep as-is.
- Add AC5: The `unknown` contact_id case (NULL contact_id) must still work. The `DISTINCT ON` CTE handles NULL contact_id via `LEFT JOIN`, but test explicitly.

### Risks

- **NULL contact_id handling.** The `DISTINCT ON (cv.contact_id)` in the CTE will produce one row per distinct contact_id including NULL. The LEFT JOIN back to the main query needs to handle the NULL case — join on `lm.contact_id IS NOT DISTINCT FROM c.id` instead of `lm.contact_id = c.id`. **Medium risk — must be tested.**

### Effort: M (1-2 days)

---

## PERF-004: Fix O(n^2) Tool Execution Correlation in `get_conversation_thread()`

**Feasibility:** Can do as specified

### Verified Bottleneck

Lines 1272-1292 of `console_queries.py` show the exact O(n^2) loop described. The outer loop iterates tool executions, and the inner loop iterates all messages to find the closest timestamp match within 5 seconds. With 200 messages and 100 tool executions, that is 20,000 comparisons.

Additionally, the tool execution query (lines 1250-1267) fetches ALL tool executions for the contact with no LIMIT or time bounds, even though the messages are paginated.

### Technical Spec

**Fix 1: Bound tool executions to the message time window.**

After fetching messages, extract the time range and use it to filter tool executions:

```python
cur = await conn.execute(msg_sql, params_msgs)
messages = await cur.fetchall()

if messages:
    # Messages are ordered DESC, so last element is earliest
    earliest = messages[-1]["created_at"]
    latest = messages[0]["created_at"]
    # Add 5-second buffer for correlation window
    from datetime import timedelta
    time_start = earliest - timedelta(seconds=5)
    time_end = latest + timedelta(seconds=5)

    # Add time bounds to tool execution query
    tool_sql += " AND te.created_at BETWEEN %s AND %s"
    params_tools.extend([time_start, time_end])
```

**Fix 2: Replace O(n^2) Python loop with O(n log n) approach.**

```python
from bisect import bisect_left

if tool_execs and messages_list:
    # Build index of AI/system messages sorted by (conversation_id, timestamp)
    ai_msgs = [
        msg for msg in messages_list
        if msg["sender_type"] in ("ai", "system")
    ]
    ai_msgs.sort(key=lambda m: (str(m["conversation_id"]), m["created_at"]))

    # Group by conversation_id for fast lookup
    from collections import defaultdict
    msgs_by_conv = defaultdict(list)
    for msg in ai_msgs:
        msgs_by_conv[str(msg["conversation_id"])].append(msg)

    for te in tool_execs:
        conv_msgs = msgs_by_conv.get(str(te["conversation_id"]), [])
        if not conv_msgs:
            continue
        te_time = te["created_at"]
        # Binary search for closest message
        times = [m["created_at"] for m in conv_msgs]
        idx = bisect_left(times, te_time)
        best_msg = None
        best_delta = None
        for candidate_idx in [idx - 1, idx]:
            if 0 <= candidate_idx < len(conv_msgs):
                delta = abs((conv_msgs[candidate_idx]["created_at"] - te_time).total_seconds())
                if delta <= 5 and (best_delta is None or delta < best_delta):
                    best_delta = delta
                    best_msg = conv_msgs[candidate_idx]
        if best_msg is not None:
            best_msg["tool_executions"].append(te)
```

**Fix 3 (alternative): Move correlation to SQL.** This is cleaner but harder to maintain:

```sql
SELECT te.*, m.id AS correlated_message_id
FROM tool_executions te
JOIN conversations cv ON te.conversation_id = cv.id
LEFT JOIN LATERAL (
    SELECT m.id FROM messages m
    WHERE m.conversation_id = te.conversation_id
      AND m.sender_type IN ('ai', 'system')
      AND ABS(EXTRACT(EPOCH FROM (m.created_at - te.created_at))) <= 5
    ORDER BY ABS(EXTRACT(EPOCH FROM (m.created_at - te.created_at)))
    LIMIT 1
) m ON true
WHERE cv.contact_id = %s AND cv.agent_id = %s
  AND te.created_at BETWEEN %s AND %s
ORDER BY te.created_at
```

**Recommendation:** Do Fix 1 + Fix 2 (Python-side). The SQL lateral join approach (Fix 3) is elegant but creates a dependency on `idx_tool_executions_conversation_created` from PERF-006, and the LATERAL join with an expression-based filter (`ABS(EXTRACT(...))`) cannot use indexes well. The Python bisect approach is simpler, well-tested, and O(n log n).

### Tightened Acceptance Criteria

- AC3: "Under 1 second for 500 messages" — achievable with bounded tool execution query + O(n log n) correlation. Keep as-is.
- Add AC5: Tool execution query MUST include time bounds matching the paginated message window. This is the highest-impact fix.

### Risks

- **Time bounds off-by-one.** If messages are paginated with OFFSET 100 and LIMIT 50, the time window covers messages 100-150. Tool executions just outside this window (correlated to message 99 or 151) will be missed. This is acceptable — the tool execution is still visible when the user navigates to that page. **Low risk.**

### Effort: S (< 1 day) — mostly mechanical refactoring

---

## PERF-005: Parallelize `get_agent_detail()` Queries with `asyncio.gather()`

**Feasibility:** Can do with modifications

### Verified Bottleneck

Lines 258-335 of `console_queries.py` show 7 sequential queries within a single `async with get_async_db_connection() as conn:` block:
1. Agent record (must run first — gate check)
2. Contacts list
3. Listings list
4. Recent messages (JOIN conversations + contacts)
5. Pending triggers
6. Cost/month aggregation
7. Error count

Queries 2-7 are independent and can run concurrently after query 1 succeeds.

### Technical Spec

**Key constraint:** `asyncio.gather()` requires each query to have its own connection. The current code uses one connection for all 7 queries. The `AsyncConnectionPool` (psycopg_pool) supports concurrent checkout — each `get_async_db_connection()` call gets a separate connection from the pool.

**Pool sizing check:** The async pool defaults to `max_size=20` for web processes (line 47 of `connection.py`). Running 6 concurrent queries per request means a single agent detail request consumes 6 connections. With 3 concurrent console users, that is 18 connections — within the 20-connection pool limit but tight. **Recommendation: do not increase pool size. Instead, limit parallelism to 3 groups of 2 queries, not 6 individual queries.**

Actually, re-evaluating: the console is an internal operator tool with 1-3 concurrent users, not a public-facing endpoint. 6 connections per request is fine for the pool size of 20.

**Implementation:**

```python
@console_authorized
async def get_agent_detail(agent_id: str) -> AgentDetail | None:
    # Step 1: Fetch agent (gate check) — must complete first
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM agents WHERE id = %s", [agent_id]
            )
            agent = await cur.fetchone()
            if not agent:
                return None
    except psycopg.Error as e:
        logger.error(f"Agent detail query failed: {e}")
        return None

    # Step 2: Parallel queries
    async def _fetch_contacts():
        try:
            async with get_async_db_connection() as conn:
                cur = await conn.execute(
                    """SELECT id, name, phone, role, lifecycle_stage, consent_status,
                              last_contact_at, silent_mode
                       FROM contacts WHERE agent_id = %s
                       ORDER BY last_contact_at DESC NULLS LAST
                       LIMIT 25""",  # PERF-008 pagination
                    [agent_id],
                )
                return await cur.fetchall() or []
        except psycopg.Error:
            return []

    # ... similar for listings, messages, triggers, costs, errors ...

    contacts, listings, recent_msgs, triggers, cost_month, errors = (
        await asyncio.gather(
            _fetch_contacts(), _fetch_listings(), _fetch_messages(),
            _fetch_triggers(), _fetch_costs(), _fetch_errors(),
            return_exceptions=True,
        )
    )

    # Handle any exceptions from gather
    def _safe(val, default):
        return default if isinstance(val, Exception) else val

    return {
        "agent": agent,
        "contacts": _safe(contacts, []),
        "listings": _safe(listings, []),
        # ... etc
    }
```

**Lightweight `get_agent_basic()` for the edit route:**

The `tenant_edit_form` route (line 319) calls `get_agent_detail()` but only uses `detail["agent"]`. Create:

```python
@console_authorized
async def get_agent_basic(agent_id: str) -> dict | None:
    try:
        async with get_async_db_connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM agents WHERE id = %s", [agent_id]
            )
            return await cur.fetchone()
    except psycopg.Error:
        return None
```

### Tightened Acceptance Criteria

- AC2: "Under 1.5 seconds" — achievable. The bottleneck is the slowest of 6 queries running in parallel, not their sum. With PERF-006 indexes, each individual query should complete in under 300ms. **Keep as-is.**
- Add AC5: `return_exceptions=True` must be used in `asyncio.gather()` to prevent one query failure from canceling all others.
- Add AC6: Create `get_agent_basic()` for the edit form route to avoid unnecessary queries.

### Risks

- **Connection pool exhaustion under concurrent load.** Each agent detail request uses 7 connections (1 + 6 parallel). Pool max is 20. If 3 operators hit agent detail pages simultaneously, that is 21 connections — **pool exhaustion, requests will block on connection checkout timeout (10 seconds).** Mitigation: group the 6 queries into 3 pairs (contacts+listings, messages+triggers, costs+errors), each pair sharing a connection. This reduces peak to 4 connections per request. **Medium risk — must mitigate.**
- **psycopg autocommit mode.** The current code uses `get_async_db_connection()` which returns connections in transaction mode (default). Read-only queries inside a transaction are fine. No risk.

### Effort: M (1-2 days) — refactoring + testing error handling + edit route optimization

---

## PERF-006: Add Missing Database Indexes

**Feasibility:** Can do as specified

### Verified Index Gaps

Current indexes from `schema.sql`:

| Table | Existing Indexes |
|-------|-----------------|
| conversations | `idx_conversations_agent_contact(agent_id, contact_id)` — no index on `last_message_at` |
| messages | `idx_messages_conversation_created(conversation_id, created_at)` — sort direction not specified (defaults to ASC) |
| tool_executions | `idx_tool_executions_agent_created(agent_id, created_at)` — no index on `conversation_id` |
| usage_metrics | `idx_usage_metrics_agent_date(agent_id, date)` — no standalone `date` index |
| triggers | `idx_triggers_status_scheduled(status, scheduled_at)` — does not include `agent_id` |

### Technical Spec

**Migration file:** `app/db/migrations/003_console_performance_indexes.sql`

```sql
-- Console Performance Indexes
-- All indexes support cross-tenant console queries (bypass RLS)

-- Conversations: ORDER BY last_message_at DESC (get_recent_conversations)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_last_message_at
    ON conversations(last_message_at DESC NULLS LAST);

-- Conversations: filtered by agent + ordered by last_message_at
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_agent_last_message
    ON conversations(agent_id, last_message_at DESC NULLS LAST);

-- Tool executions: lookup by conversation (get_conversation_thread, get_conversation_detail)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tool_executions_conversation_created
    ON tool_executions(conversation_id, created_at);

-- Usage metrics: cost queries filtered by date range without agent filter
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_metrics_date
    ON usage_metrics(date);

-- Triggers: queue filtered by status + agent (get_trigger_queue)
-- Existing idx_triggers_status_scheduled covers (status, scheduled_at)
-- Adding agent_id as a third column for filtered queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_triggers_status_agent_scheduled
    ON triggers(status, agent_id, scheduled_at);

-- Messages: support DESC order for "last message" lookups
-- Existing idx_messages_conversation_created is (conversation_id, created_at) ASC
-- Add DESC variant for "latest message" queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_conversation_created_desc
    ON messages(conversation_id, created_at DESC);
```

### Tightened Acceptance Criteria

- AC2: **Add `idx_conversations_agent_last_message`** — this is critical for the filtered `get_recent_conversations()` query. The story lists `conversations(agent_id, last_message_at DESC NULLS LAST)` which I agree with.
- AC5: EXPLAIN ANALYZE validation — **modify to: provide the specific queries to test and expected index usage (Index Scan vs Seq Scan), but do not require before/after benchmarks as part of this story.** Benchmarking requires production-like data volumes which the dev environment may not have.
- Add AC6: Verify the DESC index on messages is actually used by the query planner. PostgreSQL can scan a B-tree in reverse, so the existing ASC index on `(conversation_id, created_at)` may already support `ORDER BY created_at DESC` efficiently. If EXPLAIN shows a backward index scan, the DESC index is redundant and should be skipped.

### Risks

- **`CREATE INDEX CONCURRENTLY` cannot run inside a transaction.** The migration runner must execute each statement outside a transaction block. psycopg supports `conn.autocommit = True` for this. If using a migration tool (Alembic, custom runner), verify it supports non-transactional DDL. **Medium risk — deployment concern.**
- **Index bloat.** Adding 6 indexes increases write overhead. For an admin console serving <5 concurrent users, the read benefit far outweighs the write cost. **Low risk.**
- **Duplicate index on triggers.** The new `(status, agent_id, scheduled_at)` overlaps with existing `(status, scheduled_at)`. The existing index remains useful for queries without agent filter. Both are fine to coexist. **No risk.**

### Effort: S (< 1 day) — SQL only, no application code changes

---

## PERF-007: Add Pagination/Bounds to Trigger Queue + Cost Query Caching

**Feasibility:** Can do as specified

### Verified Bottleneck

**Trigger queue:** Lines 468-476 — `get_trigger_queue()` has no LIMIT clause. Confirmed. With filters, it returns all triggers matching the status/agent, ordered by `scheduled_at`. For a system with thousands of triggers, this is unbounded.

**Cost queries:** Lines 607-735 — `get_cost_summary()`, `get_cost_by_agent()`, `get_model_tier_breakdown()` each scan `usage_metrics` for 30 days and aggregate. No caching. These are moderate-cost queries but redundant when operators reload the billing page.

### Technical Spec

**Trigger pagination:**

```python
async def get_trigger_queue(
    status: str | None = None,
    agent_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TriggerRow]:
    # ... existing filter logic ...
    # Add LIMIT/OFFSET
    query += f" LIMIT %s OFFSET %s"
    params.extend([min(limit, 500), offset])  # Safety cap at 500
```

Update `console.py` route to pass pagination params from query string.

**Cost query caching — use existing `cache.py`:**

```python
from app.services.cache import cache_get, cache_set

COST_CACHE_TTL = 300  # 5 minutes

async def get_cost_summary(days: int = 30) -> CostSummary:
    cache_key = f"console:costs:summary:{days}"
    cached = cache_get(cache_key)
    if cached:
        return json.loads(cached)

    # ... existing query ...

    cache_set(cache_key, json.dumps(result, default=str), ttl=COST_CACHE_TTL)
    return result
```

Same pattern for `get_cost_by_agent()` and `get_model_tier_breakdown()`.

### Tightened Acceptance Criteria

- AC1: Default limit 50 is good. **Add: the route must also pass `per_page` and `page` query params, not raw limit/offset.**
- AC3: 5-minute TTL for cost queries is appropriate. **Add: no cache invalidation is needed for cost queries — they are time-based aggregations that naturally refresh.**
- AC4: "Under 2 seconds" for both pages — achievable. Keep as-is.

### Risks

- **Cost query caching with daily breakdown.** The `daily` array in `get_cost_summary()` contains 30 date+value pairs — trivially small for Redis. **No risk.**
- **Stale cost data.** 5-minute TTL means cost figures may be up to 5 minutes old. For an admin dashboard, this is acceptable. **No risk.**

### Effort: M (1-2 days) — pagination template for triggers + caching for 3 cost functions

---

## PERF-008: Add Pagination to Agent Detail Sub-lists

**Feasibility:** Can do as specified

### Verified Bottleneck

Lines 269-283 of `console_queries.py` — `get_agent_detail()` fetches ALL contacts and ALL listings for an agent with no LIMIT. For agents with hundreds of contacts, this produces a large result set and heavy HTML rendering.

### Technical Spec

**Modify `get_agent_detail()` to accept pagination params for contacts and listings:**

Better approach: do not modify `get_agent_detail()`. Instead, create separate HTMX endpoints following the existing pattern from `tenant_messages_tab` (line 792):

```python
# In console.py:

@router.get("/tenants/{agent_id}/tab/contacts", response_class=HTMLResponse)
async def tenant_contacts_tab(request: Request, agent_id: str):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    page = int(request.query_params.get("page", "1"))
    per_page = 25
    offset = (page - 1) * per_page

    from app.services.console_queries import get_agent_contacts_paginated
    contacts = await get_agent_contacts_paginated(agent_id, limit=per_page, offset=offset)

    return _render(request, "partials/tenant_contacts_list.html",
        agent_id=agent_id, contacts=contacts,
        page=page, per_page=per_page,
        has_more=len(contacts) == per_page,
    )
```

```python
# In console_queries.py:

@console_authorized
async def get_agent_contacts_paginated(
    agent_id: str, limit: int = 25, offset: int = 0,
) -> list[dict]:
    async with get_async_db_connection() as conn:
        cur = await conn.execute(
            """SELECT id, name, phone, role, lifecycle_stage, consent_status,
                      last_contact_at, silent_mode
               FROM contacts WHERE agent_id = %s
               ORDER BY last_contact_at DESC NULLS LAST
               LIMIT %s OFFSET %s""",
            [agent_id, limit, offset],
        )
        return await cur.fetchall() or []
```

Same pattern for listings. The initial `get_agent_detail()` call can include the first page (LIMIT 25) inline, then the "Load more" button hits the HTMX partial.

**This pairs with PERF-005.** The initial `get_agent_detail()` already adds `LIMIT 25` to contacts and listings in the parallelized version.

### Tightened Acceptance Criteria

- AC1-2: 25 items per page with "Load more" via HTMX. **Add: the "Load more" button should use `hx-get` with `hx-swap="beforeend"` to append new rows without replacing existing ones.**
- AC3: "Under 1.5 seconds" — this is the same target as PERF-005. **Tie these stories together: PERF-008 must be implemented alongside PERF-005 for the target to be meaningful.**

### Risks

- **Template changes required.** The `tenant_detail.html` template currently renders contacts and listings inline. This needs refactoring to use HTMX partials. The pattern exists in the codebase (`tenant_messages_tab.html`), so the risk is low but the template work is non-trivial. **Low risk.**

### Effort: S-M (1-2 days) — new endpoints + HTMX partials + template refactoring

---

## Cross-Cutting Concerns

### Implementation Order (Revised)

I agree with the proposed order with one modification:

| Order | Story | Effort | Notes |
|-------|-------|--------|-------|
| 1 | PERF-006 | S | Deploy indexes first — all other stories benefit |
| 2 | PERF-001 | S | Highest impact (4 pages), low effort with existing cache module |
| 3 | PERF-002 | M | Fix the worst page (Messages) |
| 4 | PERF-003 | M | Fix Customer Messages tab |
| 5 | PERF-005 + PERF-008 | M | **Combine these** — parallel queries + pagination are tightly coupled in `get_agent_detail()` |
| 6 | PERF-004 | S | Mechanical refactor of the correlation loop |
| 7 | PERF-007 | M | Pagination + caching for triggers/billing |

### Connection Pool Sizing

With PERF-005 parallelizing queries, the async pool may need adjustment. Current default is `max_size=20`. With the recommended mitigation (group queries into pairs), peak usage per agent detail request is 4 connections. At 3 concurrent operators, peak is 12 connections. **Pool size of 20 is sufficient. No change needed.**

### Redis Dependency

Stories PERF-001 and PERF-007 add Redis as a soft dependency for the console. The existing `cache.py` module is already fail-safe (swallows Redis errors, falls through to DB). This means the console will still work if Redis is down, just without caching. **No new Redis dependency risk.**

### Testing Strategy

All stories should include:
1. Unit tests for the modified query functions (mock DB, verify SQL parameters)
2. Integration test with the test database verifying correct results
3. Manual EXPLAIN ANALYZE for PERF-006 on staging with representative data volume
4. Load test: 3 concurrent operators navigating all console pages for 5 minutes, verify no connection pool exhaustion or error spikes
