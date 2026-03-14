# Console Performance Optimization — User Stories

**Epic:** Operator Console Performance
**Priority:** P0
**Created:** 2026-03-14
**Status:** Draft

---

## Context

The Calloway operator console (`/console`) suffers from multi-second page loads across its primary pages. Root cause analysis identified 10 bottlenecks spanning slow SQL queries, missing indexes, absent caching, lack of pagination, and sequential I/O where concurrency is possible. These stories group the fixes by impact and logical affinity.

**Pages affected and estimated current load times:**

| Page | Route | Estimated Load | Primary Bottleneck |
|------|-------|---------------|-------------------|
| Customers | `/console/tenants` | 5-10s | `get_all_agents()` — 3 LEFT JOIN subqueries |
| Messages | `/console/conversations` | 8-15s | `get_all_agents()` + `get_recent_conversations()` |
| Automations | `/console/triggers` | 5-10s | `get_all_agents()` + unbounded trigger query |
| System Health | `/console/health` | 5-10s | `get_all_agents()` + health overview |
| Customer Detail | `/console/tenants/{id}` | 2-4s | `get_agent_detail()` — 6 sequential queries |
| Customer Messages Tab | `/console/tenants/{id}/tab/messages` | 3-5s | `get_conversations_by_contact()` — N+1 subquery |
| Message Thread | `/console/tenants/{id}/tab/messages/{cid}` | 2-3s | `get_conversation_thread()` — O(n^2) correlation |
| Billing | `/console/billing` | 2-4s | Cost queries scan full `usage_metrics` |

---

## PERF-001: Optimize the Agent List Query and Add Redis Caching

**Priority:** P0 — Critical
**Estimated impact:** Fixes the single slowest query, used on 4 pages (Customers, Messages, Automations, Health)

### User Story

> As a console operator, I want the Customers page and agent filter dropdowns to load in under 2 seconds, so that I can navigate the console without waiting for every page to re-query the full agent list.

### Background

`get_all_agents()` in `console_queries.py` runs a query with 3 LEFT JOIN subqueries (contacts count, usage_metrics aggregation, tool_executions error count). This query is executed on 4 different routes but is never cached, despite Redis being available. The agent list changes infrequently (new agents are onboarded rarely), making it an ideal cache candidate.

### Acceptance Criteria

1. **Query optimization:** The `get_all_agents()` SQL is rewritten to eliminate or reduce the cost of the 3 LEFT JOIN subqueries. Acceptable approaches include: converting correlated subqueries to indexed JOINs, pre-aggregating counts, or splitting into a base query + parallel stat queries merged in Python.
2. **Redis caching:** `get_all_agents()` results are cached in Redis with a TTL of 60 seconds. Cache is invalidated on agent create, update, or deactivate operations (`create_agent_tenant`, `create_agent_from_wizard`, `update_agent_tenant`, `deactivate_agent`).
3. **Cache key isolation:** Cache key is namespaced (e.g., `console:agents:all`) and uses JSON serialization compatible with the existing response models.
4. **Performance target:** The Customers page (`/console/tenants`) loads in under 2 seconds with warm cache, under 4 seconds with cold cache.
5. **No functional regression:** Agent list still displays contact count, messages today, last active date, and 24h error count. Search and sort still work.
6. **Logging:** Cache hits and misses are logged at DEBUG level.

### Technical Notes

- Redis connection is already imported in `console_queries.py` (`import redis`) but unused.
- The 4 routes calling `get_all_agents()`: `tenant_list`, `conversation_list`, `trigger_list`, `health_overview`.
- Consider whether the agent dropdown on Messages/Automations/Health pages actually needs the full stat columns (contact_count, messages_today, errors_24h), or just `id` and `name`. If so, a lightweight `get_agent_options()` that returns only `id`/`name` (trivially fast, longer TTL) would further reduce load on 3 of the 4 pages.

---

## PERF-002: Optimize Recent Conversations Query and Add Pagination

**Priority:** P0 — Critical
**Estimated impact:** Fixes the Messages page, currently 8-15s (compounds with PERF-001)

### User Story

> As a console operator, I want the Messages page to load quickly and show conversations in manageable pages, so that I can find and review recent conversations without the browser stalling.

### Background

`get_recent_conversations()` returns up to 100 conversations with 2 correlated subqueries per row: one `COUNT(*)` and one `SELECT body ... LIMIT 1` against the messages table. With 100 conversations, this means ~200 correlated subqueries executed inside the main query. The route also calls `get_all_agents()` (addressed in PERF-001).

### Acceptance Criteria

1. **Eliminate correlated subqueries:** The `msg_count` and `last_message` subqueries are replaced with JOINs, window functions, or a lateral join pattern that the planner can optimize (e.g., a single `LATERAL` join that fetches both count and last body).
2. **Server-side pagination:** The `/console/conversations` route supports `page` and `per_page` query parameters (default: page 1, 25 per page). The template renders pagination controls (previous/next).
3. **Performance target:** The Messages page loads in under 2 seconds for any page of results.
4. **Filters preserved across pages:** Agent, channel, and search filters are preserved in pagination links.
5. **No functional regression:** Each conversation row still shows agent name, contact name, phone, channel, message count, last message preview, and last activity timestamp.

### Technical Notes

- The existing query uses f-string SQL construction with dynamic WHERE clauses. Maintain that pattern but ensure parameterized queries (no SQL injection risk).
- Consider adding `last_message_body` and `message_count` as denormalized columns on the `conversations` table if the JOIN approach is still too slow. This would be a schema migration story if needed.

---

## PERF-003: Fix N+1 Query in Conversations-by-Contact (Customer Messages Tab)

**Priority:** P0 — Critical
**Estimated impact:** Fixes Customer Detail Messages tab, currently 3-5s

### User Story

> As a console operator viewing a customer's detail page, I want the Messages tab to load within 1 second, so that I can quickly review a customer's conversation history organized by contact.

### Background

`get_conversations_by_contact()` uses a correlated subquery for `last_message_preview` that scans the full messages table for each contact group. It also uses a `JOIN LATERAL` to count messages per conversation, which is re-executed per row. The combination creates N+1-like behavior.

### Acceptance Criteria

1. **Correlated subquery eliminated:** The `last_message_preview` correlated subquery is replaced with a window function or a single lateral join that retrieves both the count and the last message body in one pass.
2. **Performance target:** The Messages tab (`/console/tenants/{id}/tab/messages`) loads in under 1 second for agents with up to 200 contacts.
3. **Pagination preserved:** Existing `limit`/`offset` pagination continues to work.
4. **No functional regression:** Each contact row still shows contact name, phone, channels, message count, last message preview, and last activity timestamp.

### Technical Notes

- The current query passes `agent_id` twice as a parameter (once for the correlated subquery, once for the WHERE clause). The fix should eliminate this duplication.
- Consider using `DISTINCT ON` or a CTE with `ROW_NUMBER()` to get the latest message per contact group efficiently.

---

## PERF-004: Fix O(n^2) Tool Execution Correlation in Conversation Thread

**Priority:** P1 — Major
**Estimated impact:** Fixes message thread view, currently 2-3s

### User Story

> As a console operator drilling into a contact's conversation thread, I want messages and their associated tool executions to load within 1 second, so that I can debug AI behavior without delay.

### Background

`get_conversation_thread()` fetches all messages and all tool executions for a contact, then correlates them in Python using an O(n^2) nested loop (every tool execution is compared against every message to find the closest timestamp within 5 seconds). For active contacts with hundreds of messages and tool executions, this becomes slow.

### Acceptance Criteria

1. **Correlation moved to SQL or optimized in Python:** Either:
   - (a) The correlation is done in SQL via a JOIN with a timestamp window condition, or
   - (b) The Python loop is replaced with an O(n log n) approach (e.g., sort both lists by timestamp, then use a sliding window or binary search).
2. **Tool executions bounded:** The tool executions query is filtered to only return executions within the time range of the fetched messages (respecting pagination offset), rather than fetching all tool executions for the contact's entire history.
3. **Performance target:** Thread view loads in under 1 second for conversations with up to 500 messages.
4. **No functional regression:** Tool executions still appear correlated to the correct message in the UI. The 5-second proximity window logic is preserved.

### Technical Notes

- The current code fetches ALL tool executions for the contact regardless of the message pagination window. This means even page 1 (50 messages) triggers a full scan of potentially thousands of tool executions.
- `tool_executions` has an index on `(agent_id, created_at)` but not on `(conversation_id, created_at)`. See PERF-006 for the index story.

---

## PERF-005: Parallelize Agent Detail Queries

**Priority:** P1 — Major
**Estimated impact:** Fixes Customer Detail page, currently 2-4s

### User Story

> As a console operator, I want a customer's detail page to load in under 1.5 seconds, so that I can quickly review a customer's full profile, contacts, listings, messages, triggers, and costs.

### Background

`get_agent_detail()` runs 6 sequential database queries within a single connection: agent record, contacts, listings, recent messages, pending triggers, and cost/error aggregations. These queries are independent of each other (after confirming the agent exists) and could run concurrently.

### Acceptance Criteria

1. **Concurrent execution:** After fetching and confirming the agent record exists, the remaining 5 queries are executed concurrently using `asyncio.gather()` (or equivalent).
2. **Performance target:** Customer detail page (`/console/tenants/{id}`) loads in under 1.5 seconds.
3. **Error handling preserved:** If any individual query fails, the others still complete. Failed sections show empty state rather than crashing the page.
4. **No functional regression:** All 6 data sections still populate correctly: agent profile, contacts list, listings list, recent messages, pending triggers, and month-to-date cost/error summary.

### Technical Notes

- The current implementation uses a single `async with get_async_db_connection() as conn:` block. Parallelizing may require opening multiple connections or using `asyncio.gather()` with separate connection contexts for each query.
- This is also called from the edit form route (`tenant_edit_form`), which only needs the agent record. Consider a lightweight `get_agent_basic()` for the edit route.

---

## PERF-006: Add Missing Database Indexes for Console Access Patterns

**Priority:** P1 — Major
**Estimated impact:** Accelerates multiple queries across all stories; low-risk, high-leverage

### User Story

> As a console operator, I want all console pages to benefit from proper database indexing, so that query performance remains fast as data volume grows.

### Background

The console queries access data across tenant boundaries (bypassing RLS), using access patterns that differ from the per-agent RLS-scoped queries. Several console-specific access patterns lack supporting indexes.

### Acceptance Criteria

1. **Indexes added via migration script:** A SQL migration file is created at `app/db/migrations/` (or equivalent project convention) containing all new indexes. Indexes are created with `IF NOT EXISTS` or `CREATE INDEX CONCURRENTLY` to be safe for production.
2. **The following indexes are added (at minimum):**
   - `conversations(last_message_at DESC NULLS LAST)` — used by `get_recent_conversations()` ORDER BY
   - `conversations(agent_id, last_message_at DESC NULLS LAST)` — used by conversations filtered by agent
   - `tool_executions(conversation_id, created_at)` — used by `get_conversation_thread()` and `get_conversation_detail()`
   - `messages(conversation_id, created_at DESC)` — used by last-message subqueries (partially exists but verify sort order)
   - `usage_metrics(date)` — used by cost queries filtered by date range
   - `triggers(status, scheduled_at, agent_id)` — used by `get_trigger_queue()` with status + agent filters
3. **No existing indexes are dropped.** This is additive only.
4. **Index creation is tested** against the current schema to verify no conflicts or duplicate index errors.
5. **Impact validated:** EXPLAIN ANALYZE output (or equivalent) is captured for the slowest queries before and after indexing, confirming improvement.

### Technical Notes

- Existing indexes in `schema.sql` cover per-agent access patterns well. The gaps are in cross-tenant and console-specific patterns.
- `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block — the migration runner may need to handle this.
- `idx_messages_conversation_created` exists as `(conversation_id, created_at)` but confirm sort direction matches query needs.

---

## PERF-007: Add Pagination and Bounds to Trigger Queue and Cost Queries

**Priority:** P2 — Moderate
**Estimated impact:** Prevents degradation as data grows; fixes Automations and Billing pages

### User Story

> As a console operator, I want the Automations page and Billing page to load quickly and show bounded result sets, so that page performance does not degrade as the system processes more triggers and accumulates more usage data.

### Background

Two moderate-impact issues:
1. `get_trigger_queue()` returns unbounded results — no LIMIT clause. As trigger volume grows, this will slow unboundedly.
2. Cost/billing queries (`get_cost_summary`, `get_cost_by_agent`, `get_model_tier_breakdown`) aggregate the full `usage_metrics` table for the requested period. While the 30-day window is reasonable, there is no caching and the queries re-run on every page load.

### Acceptance Criteria

1. **Trigger pagination:** `get_trigger_queue()` accepts `limit` and `offset` parameters (default: 50, 0). The Automations page renders pagination controls. Filters (status, agent) are preserved across pages.
2. **Trigger result cap:** Even without explicit pagination, the query includes a `LIMIT 500` safety cap to prevent unbounded result sets.
3. **Cost query caching:** Cost summary, per-agent cost, and model tier breakdown results are cached in Redis with a 5-minute TTL. Cache key includes the `days` parameter.
4. **Performance targets:**
   - Automations page loads in under 2 seconds.
   - Billing page loads in under 2 seconds.
5. **No functional regression:** Trigger filtering by status and agent still works. Cost breakdowns still show accurate 30-day totals, per-agent splits, and model tier data.

### Technical Notes

- The `get_trigger_queue()` query currently has no LIMIT: `ORDER BY t.scheduled_at` with no bound.
- Cost queries already have a `days` parameter that bounds the date range, so the main win is caching, not query rewriting.
- Consider whether the daily breakdown array in `get_cost_summary` needs to be cached separately (it can be large for 30 days x many agents).

---

## PERF-008: Add Pagination to Agent Detail Sub-lists (Contacts, Listings)

**Priority:** P2 — Moderate
**Estimated impact:** Prevents degradation for high-volume agents

### User Story

> As a console operator viewing a high-volume customer with hundreds of contacts or listings, I want the detail page to load a manageable number of records with the option to load more, so that the page remains responsive regardless of how many contacts or listings the customer has.

### Background

`get_agent_detail()` fetches all contacts and all listings for an agent with no pagination. For agents with 500+ contacts, this produces a large HTML payload and slow rendering. The recent messages query is already limited to 50.

### Acceptance Criteria

1. **Contacts pagination:** The contacts section of the customer detail page shows the first 25 contacts by default, with a "Load more" button (HTMX partial) to fetch the next page.
2. **Listings pagination:** The listings section shows the first 25 listings by default, with the same "Load more" pattern.
3. **Performance target:** Customer detail page loads in under 1.5 seconds for agents with any number of contacts/listings.
4. **Sort order preserved:** Contacts sorted by `last_contact_at DESC NULLS LAST`. Listings sorted by `created_at DESC`.
5. **No functional regression:** All contact and listing fields still display. Existing links to contact detail and listing detail pages still work.

### Technical Notes

- This pairs well with PERF-005 (parallelized queries). The initial page load fetches only 25 contacts + 25 listings in parallel, with HTMX-driven lazy loading for more.
- The HTMX partials pattern is already established in the codebase (see `tenant_messages_tab`, `dashboard_activity_feed`).

---

## Implementation Priority Order

| Order | Story | Impact | Effort | Rationale |
|-------|-------|--------|--------|-----------|
| 1 | PERF-006 | High | Low | Indexes are low-risk, improve all queries, and should be deployed first so other stories benefit |
| 2 | PERF-001 | Critical | Medium | Fixes the single most impactful bottleneck (4 pages) |
| 3 | PERF-002 | Critical | Medium | Fixes the worst single page (Messages) |
| 4 | PERF-003 | Critical | Medium | Fixes Customer Messages tab |
| 5 | PERF-005 | Major | Low | Simple asyncio.gather() refactor with big payoff |
| 6 | PERF-004 | Major | Medium | Fixes thread view performance |
| 7 | PERF-007 | Moderate | Medium | Pagination + caching for triggers and billing |
| 8 | PERF-008 | Moderate | Low | Pagination for contacts/listings sub-lists |

### Overall Target

After all 8 stories are implemented, every console page should load in under 2 seconds under normal operating conditions (< 50 agents, < 10,000 conversations total). No page should degrade below 3 seconds regardless of data volume.
