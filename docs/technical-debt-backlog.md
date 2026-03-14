# Calloway — Technical Debt Backlog

**Document ID:** PRD-DEBT-001
**Author:** Mara (Product Manager)
**Date:** 2026-03-14
**Status:** Draft — Pending Solomon Review
**Audience:** Solomon (Chief of Staff), Atlas (Engineering Lead), Chronos (Program Manager)

---

## 1. Problem Statement

The Calloway architecture audit identified 29 outstanding items across security, performance, architecture, code quality, and testing. While the 4 critical bugs (C-1 through C-4) have been resolved, the remaining items represent compounding risk across three dimensions:

1. **Security exposure.** A shared console password with no audit trail, unverified webhook endpoints, and potential XSS vectors mean that a single credential leak or forged request could expose every agent's client data — a direct liability under state real estate commission regulations and consumer privacy law.

2. **Scaling ceiling.** N+1 queries, unbounded memory loads, and synchronous LLM calls in the hot path will degrade response times as we grow from 10 to 100 to 1,000 agents. Real estate agents depend on sub-second SMS responses to capture leads; latency kills conversion.

3. **Developer velocity drag.** No migration tooling, duplicated sync/async code paths, no dependency injection, and zero tests on the two largest service files mean every new feature carries hidden regression risk and extended delivery timelines.

Addressing this debt is not optional polish — it is prerequisite infrastructure for the next phase of growth.

---

## 2. Prioritized Epics

### Epic 1: Security Hardening
**Priority: P0**

Protect agent and client data from unauthorized access, forged requests, and injection attacks. Real estate client data includes PII (phone numbers, emails, addresses, financial pre-qualification details). A breach would be catastrophic for agent trust and regulatory compliance.

| Story ID | Title |
|----------|-------|
| S-1 | Per-user console authentication with audit trail |
| S-2 | Authorization guard on console query layer |
| S-3 | SendGrid inbound webhook signature verification |
| S-4 | Block Vapi webhook when secret not configured in production |
| S-5 | Parameterized column updates in tool functions |
| S-6 | Proper HTML sanitization for KB uploads |
| S-7 | Rate limiting on console login |

### Epic 2: Performance Optimization
**Priority: P0**

Eliminate query and processing bottlenecks that will cause visible degradation at 100+ agents. Agents receive time-sensitive inbound leads via SMS; every 100ms of added latency reduces the chance the AI responds before the lead moves on.

| Story ID | Title |
|----------|-------|
| P-1 | Eliminate N+1 queries in agent list |
| P-2 | Bounded listing search in assembler |
| P-3 | Async conversation summarization |
| P-4 | Cached conversation history |
| P-5 | Native vector parameter passing in RAG search |
| P-6 | Selective column load in daily scanner |

### Epic 3: Architecture Modernization
**Priority: P1**

Structural improvements that reduce blast radius of failures, enable zero-downtime deploys, and unlock caching/queuing patterns needed at scale.

| Story ID | Title |
|----------|-------|
| A-1 | Message queue for pipeline processing |
| A-2 | Separate worker process from web server |
| A-3 | Redis caching layer for hot data |
| A-4 | Database migration tooling (Alembic) |
| A-5 | Consolidate sync/async console query paths |

### Epic 4: Testing Foundation
**Priority: P1**

Establish test coverage for the highest-risk untested surfaces. Without these tests, every deploy is a gamble — especially for consent gates (TCPA liability) and RLS policies (tenant isolation).

| Story ID | Title |
|----------|-------|
| T-1 | Console queries test suite |
| T-2 | Dispatcher test suite |
| T-3 | Integration tests with real DB (RLS verification) |
| T-4 | Security test suite |
| T-5 | RAG search accuracy tests |
| T-6 | Load/stress test harness |

### Epic 5: Code Quality & Standards
**Priority: P2**

Reduce maintenance burden, improve onboarding speed for future engineers, and align with modern Python/FastAPI best practices.

| Story ID | Title |
|----------|-------|
| B-1 | Dependency injection for services |
| B-2 | Eliminate bare except swallowing |
| B-3 | Structured return types with type hints |
| B-5 | Configurable model names |
| B-6 | Correct monthly recurrence with relativedelta |
| B-7 | Correct annual recurrence with relativedelta |
| E-1 | Pydantic v2 migration patterns |
| E-2 | Template component organization |
| E-3 | CSS design token system |
| E-4 | Accessibility basics (ARIA, focus management) |

---

## 3. User Stories

---

### S-1: Per-User Console Authentication with Audit Trail

**As an** operations manager, **I want** individual login credentials for each console operator, **so that** I can see who performed each action and revoke access for specific people without changing a shared password.

**Priority:** P0 | **Effort:** L | **Dependencies:** A-4 (needs migration for users table)

**Acceptance Criteria:**

1. **Given** an operator navigates to `/console/login`, **when** they enter their unique email and password, **then** they are authenticated and a session is created containing their user ID and role.

2. **Given** an authenticated operator performs any write action (toggle autonomy, approve message, update agent config), **when** the action is executed, **then** an audit log entry is written containing: operator user ID, action type, target entity ID, timestamp, and IP address.

3. **Given** an operator with "viewer" role is logged in, **when** they attempt a write action (POST/PUT/DELETE), **then** the request is rejected with 403 Forbidden and no state change occurs.

4. **Given** the `ENVIRONMENT` is `production`, **when** the application starts with `CONSOLE_PASSWORD` still set to the default value, **then** the app refuses to start (this existing check must be preserved during migration).

5. **Given** an admin wants to revoke an operator's access, **when** they delete or deactivate that user record, **then** the operator's existing sessions are invalidated and they cannot access any console route.

**Edge Cases:**
- Migration path: existing single-password deployments must continue working until operators are created. Support a `LEGACY_AUTH_MODE=true` flag during transition.
- Session invalidation on password change.
- Concurrent sessions from the same user on multiple devices.

---

### S-2: Authorization Guard on Console Query Layer

**As a** security engineer, **I want** the console query functions to be callable only from authenticated console routes, **so that** an accidental or malicious unauthenticated route cannot expose cross-tenant data.

**Priority:** P0 | **Effort:** S | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a request reaches any function in `console_queries.py`, **when** the calling context does not have a verified console session, **then** the function raises an `AuthorizationError` and returns no data.

2. **Given** an authenticated console request calls `get_all_agents()`, **when** the session is valid, **then** the query executes normally and returns cross-tenant data as designed.

3. **Given** a new API route is added that imports and calls a console query function, **when** that route is not decorated with the console auth dependency, **then** the function-level guard blocks execution regardless.

**Edge Cases:**
- Internal background jobs that legitimately need cross-tenant access (e.g., daily scanner) should use a separate code path or an explicit `internal=True` flag, not the console query layer.
- Error messages must not leak schema or data details.

---

### S-3: SendGrid Inbound Webhook Signature Verification

**As a** platform operator, **I want** the email inbound webhook to verify SendGrid's signature on every request, **so that** attackers cannot forge inbound emails to inject messages into agent conversations.

**Priority:** P0 | **Effort:** S | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** `SENDGRID_INBOUND_SECRET` is configured, **when** an inbound POST arrives at `/webhooks/email/inbound` with a valid SendGrid signature header, **then** the request is processed normally.

2. **Given** `SENDGRID_INBOUND_SECRET` is configured, **when** a POST arrives with an invalid or missing signature, **then** the endpoint returns 401 and the request body is not processed.

3. **Given** `SENDGRID_INBOUND_SECRET` is empty and `ENVIRONMENT` is `production`, **when** the application starts, **then** a warning is logged at CRITICAL level. The endpoint should reject all requests with 503 ("email webhook not configured").

4. **Given** `SENDGRID_INBOUND_SECRET` is empty and `ENVIRONMENT` is `development`, **when** a POST arrives, **then** signature validation is skipped and a DEBUG log is emitted (mirrors existing Twilio dev behavior).

**Edge Cases:**
- SendGrid may send verification differently depending on the parse webhook version (v2 vs v3). Implementation must match the version we use.
- Replay attacks: consider adding timestamp validation if SendGrid includes one.

---

### S-4: Block Vapi Webhook When Secret Not Configured in Production

**As a** platform operator, **I want** the Vapi webhook to reject all requests when the secret is not configured in production, **so that** an unconfigured deployment cannot be exploited by forged voice transcripts.

**Priority:** P0 | **Effort:** XS | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** `VAPI_WEBHOOK_SECRET` is empty and `ENVIRONMENT` is `production`, **when** a POST arrives at `/webhooks/vapi/post-call`, **then** the endpoint returns 503 with body `{"error": "Vapi webhook not configured"}` and no processing occurs.

2. **Given** `VAPI_WEBHOOK_SECRET` is set, **when** a POST arrives with a matching `x-vapi-secret` header, **then** the request processes normally.

3. **Given** `VAPI_WEBHOOK_SECRET` is empty and `ENVIRONMENT` is `development`, **when** a POST arrives, **then** the existing skip-and-warn behavior is preserved.

**Edge Cases:**
- Ensure the 503 response does not reveal the specific missing configuration key name to external callers.

---

### S-5: Parameterized Column Updates in Tool Functions

**As a** security engineer, **I want** dynamic SQL column names in update functions to be validated against an explicit allowlist enforced at the query construction layer, **so that** even if the upstream allowlist filtering is bypassed or a new tool is added without one, SQL injection via column names is impossible.

**Priority:** P1 | **Effort:** S | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** `update_contact()` is called with field names that are all in the `valid_fields` set, **when** the SQL is constructed, **then** column names are validated against the allowlist AND the query uses a mapping of safe column names (not the raw dict key) in the f-string.

2. **Given** `update_contact()` receives a key not in `valid_fields` (e.g., `"; DROP TABLE contacts--"`), **when** filtering occurs, **then** the key is silently dropped and the remaining valid fields are updated.

3. **Given** a new tool update function is added (e.g., `update_transaction()`), **when** it follows the same pattern, **then** a shared utility function `build_safe_update_clause(fields, allowed)` is used rather than each tool reimplementing the pattern.

4. **Given** the allowlist is bypassed (defensive), **when** a column name contains non-alphanumeric/non-underscore characters, **then** the query builder raises a `ValueError` before any SQL is executed.

**Edge Cases:**
- PostgreSQL reserved words used as column names (e.g., `name`, `role`) — these should be double-quoted in the generated SQL.
- Empty `filtered` dict after validation (already handled in current code, preserve this).

---

### S-6: Proper HTML Sanitization for KB Document Uploads

**As a** platform operator, **I want** knowledge base document uploads to be sanitized with a proper HTML parsing library, **so that** XSS payloads in uploaded content cannot execute in the console when documents are displayed.

**Priority:** P1 | **Effort:** S | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a KB document is uploaded containing `<script>alert('xss')</script>`, **when** the content is sanitized, **then** the script tag and its contents are completely removed.

2. **Given** a document contains obfuscated XSS like `<img src=x onerror=alert(1)>` or `<div style="background:url(javascript:alert(1))">`, **when** sanitization runs, **then** all event handlers and javascript: URLs are stripped.

3. **Given** a document contains legitimate content with angle brackets (e.g., `price < $500,000`), **when** sanitization runs, **then** the text content is preserved.

4. **Given** the sanitization library is `bleach` or `nh3`, **when** it is used, **then** it replaces the current `re.sub` regex approach at `app/api/console.py` lines 847-848.

**Edge Cases:**
- Documents with embedded SVG containing script tags.
- Unicode-based bypass attempts (e.g., using fullwidth angle brackets).
- Very large documents (50,000 char limit already enforced — sanitizer must handle this without excessive memory use).

---

### S-7: Rate Limiting on Console Login

**As a** platform operator, **I want** the console login endpoint to enforce rate limiting, **so that** brute-force password attacks are infeasible.

**Priority:** P1 | **Effort:** S | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a client IP has made 5 failed login attempts in 15 minutes, **when** they submit another login attempt, **then** the endpoint returns 429 Too Many Requests with a `Retry-After` header.

2. **Given** a client IP is rate-limited, **when** they submit a correct password, **then** the attempt is still blocked until the window expires (prevents timing-based enumeration).

3. **Given** rate limit state is stored in Redis, **when** Redis is unavailable, **then** login falls back to allowing the attempt (fail-open) with a WARNING log, rather than locking all operators out.

4. **Given** an operator successfully logs in, **when** the rate limit window for their IP has not expired, **then** the failed attempt counter is reset.

**Edge Cases:**
- Multiple operators behind the same corporate NAT/VPN sharing an IP.
- Rate limit bypass via IPv6 rotation — consider also limiting by session cookie fingerprint.
- Distributed brute-force from many IPs — consider a global rate limit on total failed attempts per minute.

---

### P-1: Eliminate N+1 Queries in Agent List

**As a** console operator, **I want** the agent dashboard to load in under 500ms even with 1,000 agents, **so that** I can quickly scan system health without waiting.

**Priority:** P0 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** the database has 100 agents, **when** `get_all_agents()` is called, **then** it executes at most 2 SQL statements (one for agents with JOINed aggregates, optionally one for error counts).

2. **Given** the refactored query uses LEFT JOINs or lateral joins, **when** compared to the current 4-subquery-per-row approach, **then** the total query count drops from O(4n) to O(1).

3. **Given** 1,000 agents exist, **when** the dashboard loads, **then** the `get_all_agents()` call completes in under 200ms (measured via query logging).

4. **Given** an agent has zero contacts, zero messages, and zero errors, **when** the query runs, **then** that agent still appears with counts of 0 (no NULL rendering issues).

**Edge Cases:**
- Agents with extremely large contact counts (10,000+) — ensure aggregation doesn't create a sequential scan.
- New agents with no usage_metrics rows at all.

---

### P-2: Bounded Listing Search in Assembler

**As a** real estate agent's AI assistant, **I want** listing lookup to use a database-level text search instead of loading all listings into memory, **so that** agents with hundreds of listings don't experience slow response times.

**Priority:** P0 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** an inbound message references "123 Oak Street", **when** `_find_referenced_listing()` runs, **then** it executes a SQL query with a `WHERE` clause that filters by address keywords, returning at most 5 candidates.

2. **Given** an agent has 500 active listings, **when** a listing lookup runs, **then** memory usage does not scale linearly with listing count (no `SELECT *` of all listings).

3. **Given** a message contains a partial address like "Oak St", **when** the search runs, **then** it matches listings with addresses containing "Oak" using case-insensitive `ILIKE` or `tsvector` matching.

4. **Given** a message contains no address-like content, **when** the function runs, **then** it returns `None` without executing any listing query (short-circuit).

**Edge Cases:**
- Addresses with special characters (e.g., "123 O'Brien Lane").
- Multiple listings matching the same partial address — return the best match or the first match with a warning log.
- Unicode address characters.

---

### P-3: Async Conversation Summarization

**As a** real estate agent's client, **I want** my SMS to be answered as fast as possible, **so that** I feel like the agent is responsive and available.

**Priority:** P0 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a message has been dispatched successfully, **when** `_maybe_summarize_conversation()` is triggered, **then** it runs as a background task (via `BackgroundTasks` or `asyncio.create_task`), not in the response hot path.

2. **Given** summarization is moved to background, **when** the response time is measured for a typical message, **then** p95 latency decreases by 200-400ms compared to the current synchronous approach.

3. **Given** the background summarization task fails, **when** the next message arrives, **then** the assembler gracefully falls back to recent-messages-only context (existing fallback behavior preserved).

4. **Given** two messages arrive in rapid succession for the same contact, **when** both trigger summarization, **then** a deduplication mechanism prevents two concurrent summarization calls (use a short Redis lock or in-memory flag).

**Edge Cases:**
- Background task pool exhaustion under high load.
- Summarization for a contact that is deleted between dispatch and background execution.

---

### P-4: Cached Conversation History

**As a** platform operator, **I want** frequently accessed conversation history to be served from Redis cache, **so that** repeated database hits for the same conversation are eliminated during rapid back-and-forth messaging.

**Priority:** P1 | **Effort:** M | **Dependencies:** A-3 (Redis caching layer)

**Acceptance Criteria:**

1. **Given** a message arrives for agent X, contact Y, **when** conversation history is needed, **then** the system checks Redis first using key `conv:{agent_id}:{contact_id}` before querying the database.

2. **Given** the cache contains recent history, **when** the cache entry is less than 60 seconds old, **then** the cached history is used without a DB query.

3. **Given** a new message is sent or received, **when** it is written to the database, **then** the corresponding cache entry is invalidated.

4. **Given** Redis is unavailable, **when** a cache read fails, **then** the system falls back to the database query with no user-visible error.

**Edge Cases:**
- Cache stampede when many messages arrive simultaneously for a popular agent.
- Cache entry exceeding Redis max value size for very long conversation histories.
- Stale cache causing the AI to miss the most recent message in context.

---

### P-5: Native Vector Parameter Passing in RAG Search

**As a** platform operator, **I want** embedding vectors passed as native array parameters to PostgreSQL, **so that** the database doesn't waste CPU parsing string representations of 1024-dimensional vectors on every search.

**Priority:** P1 | **Effort:** XS | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a RAG search is executed, **when** the query embedding is passed to the SQL query, **then** it is passed as a Python list (native array) rather than `str(query_embedding)`.

2. **Given** the parameter is passed natively, **when** pgvector processes it, **then** the `::vector` cast operates on a native array, not a string representation.

3. **Given** before/after benchmarks on a table with 10,000 embeddings, **when** the same search is run, **then** query execution time decreases measurably (expected 10-30% improvement on the vector comparison step).

**Edge Cases:**
- Ensure the database driver (psycopg2/asyncpg) correctly serializes Python lists as PostgreSQL array parameters. May require registering a custom adapter for the `vector` type.
- Null or empty embedding vectors — should raise a clear error before reaching the DB.

---

### P-6: Selective Column Load in Daily Scanner

**As a** platform operator, **I want** the daily scanner to load only the columns it needs for each agent, **so that** the morning scan doesn't consume excessive memory loading large JSONB configuration blobs for every agent.

**Priority:** P1 | **Effort:** XS | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** `_get_all_active_agents()` is called, **when** the SQL query executes, **then** it selects only the columns used downstream (e.g., `id, name, timezone, autonomy_level, listing_rules, active`) rather than `SELECT *`.

2. **Given** a new column is added to the `agents` table (e.g., a 100KB JSONB blob), **when** the daily scanner runs, **then** that column is NOT loaded unless explicitly needed.

3. **Given** the AgentConfig model is used to parse the results, **when** only selected columns are returned, **then** the model gracefully handles missing optional fields (or a slimmed-down model/NamedTuple is used).

**Edge Cases:**
- Future code changes that reference a column not in the SELECT list — add a comment in the query listing which downstream functions use which columns.
- The `AgentConfig(**r)` constructor may fail if required fields are missing — verify which fields are truly required.

---

### A-1: Message Queue for Pipeline Processing

**As a** platform operator, **I want** inbound messages to be queued via Redis Streams before pipeline processing, **so that** messages are not lost on server restart and failed processing can be retried automatically.

**Priority:** P1 | **Effort:** XL | **Dependencies:** A-2 (worker separation)

**Acceptance Criteria:**

1. **Given** an inbound webhook receives a message, **when** it is accepted, **then** the message is written to a Redis Stream (e.g., `calloway:inbound`) and an immediate 200 response is returned to the sender (Twilio/SendGrid).

2. **Given** a message is in the stream, **when** a consumer worker picks it up and processing fails, **then** the message is retried up to 3 times with exponential backoff before being moved to a dead-letter stream.

3. **Given** the web server restarts, **when** it comes back up, **then** unprocessed messages in the stream are still present and are consumed by the worker.

4. **Given** a message has been in the dead-letter stream for 24 hours, **when** an operator views the console, **then** they see a "failed messages" count on the dashboard with the ability to inspect and retry.

**Edge Cases:**
- Redis itself goes down — need a fallback to direct processing (current behavior) with a CRITICAL log.
- Duplicate message delivery from Twilio — consumer must be idempotent (dedup by message SID).
- Message ordering — messages from the same contact should be processed in order.

---

### A-2: Separate Worker Process from Web Server

**As a** platform operator, **I want** background workers (trigger_worker, daily_scanner) to run as a separate container/process from the web server, **so that** a worker crash doesn't take down the API and resource allocation can be tuned independently.

**Priority:** P1 | **Effort:** L | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** the deployment configuration, **when** services start, **then** the web server and worker run as separate containers (or separate Railway services) with independent health checks.

2. **Given** the worker process crashes, **when** the web server receives an API request, **then** it continues serving normally with no degradation.

3. **Given** both processes share the same codebase, **when** either starts, **then** they are differentiated by an entrypoint flag or environment variable (e.g., `PROCESS_TYPE=web` vs `PROCESS_TYPE=worker`).

4. **Given** the worker and web processes share the database, **when** connection pools are configured, **then** each process has its own pool with separate limits to prevent connection exhaustion.

**Edge Cases:**
- Shared in-memory state (if any exists) must be moved to Redis.
- Log aggregation across multiple processes — ensure correlation IDs work cross-process.
- Graceful shutdown: worker must finish current trigger execution before stopping.

---

### A-3: Redis Caching Layer for Hot Data

**As a** platform operator, **I want** agent configuration, active listings, and conversation history cached in Redis with appropriate TTLs, **so that** frequently read data is served from cache instead of hitting PostgreSQL on every request.

**Priority:** P1 | **Effort:** L | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** an agent's configuration is loaded, **when** it has been loaded in the last 5 minutes, **then** the cached version is returned without a database query.

2. **Given** an agent's configuration is updated via the console, **when** the update is saved, **then** the corresponding cache entry is immediately invalidated.

3. **Given** Redis is unavailable, **when** any cache read/write fails, **then** the system transparently falls back to direct database access with a WARNING log.

4. **Given** the caching layer is implemented, **when** benchmarked under load, **then** database queries for agent config and listing reads decrease by at least 80% during sustained conversation bursts.

**Edge Cases:**
- Cache key collisions between tenants (all keys must be namespaced by agent_id).
- Large agent configurations exceeding Redis default value size limits.
- Cache warming strategy on cold start / after Redis flush.

---

### A-4: Database Migration Tooling (Alembic)

**As an** engineer, **I want** database schema changes managed through Alembic migration files, **so that** schema changes are versioned, reversible, and can be applied consistently across environments.

**Priority:** P1 | **Effort:** M | **Dependencies:** None (but should precede any schema-changing story)

**Acceptance Criteria:**

1. **Given** the current `schema.sql`, **when** Alembic is initialized, **then** a baseline migration is created that represents the current production schema.

2. **Given** a developer needs to add a column, **when** they run `alembic revision --autogenerate`, **then** a migration file is created with `upgrade()` and `downgrade()` functions.

3. **Given** a migration is applied to staging, **when** it causes problems, **then** `alembic downgrade -1` cleanly reverts the change.

4. **Given** CI/CD runs, **when** a new migration exists, **then** it is applied automatically during deployment (via a pre-start script or init container).

**Edge Cases:**
- Existing production database with data — baseline migration must be a no-op on existing schema.
- Migrations that require data backfill (e.g., adding a NOT NULL column with default values for existing rows).
- Concurrent migration execution during rolling deploys — Alembic's advisory lock must be enabled.
- RLS policies must be included in migration tracking.

---

### A-5: Consolidate Sync/Async Console Query Paths

**As an** engineer, **I want** the console query layer to use a single async code path, **so that** the current ~700 lines of duplicated sync/async code are eliminated and bug fixes only need to be made once.

**Priority:** P1 | **Effort:** L | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** the console queries module, **when** the refactor is complete, **then** each query exists only once as an `async def` function.

2. **Given** any caller that previously used the sync version, **when** it calls the new async version, **then** it does so within an `await` context (all console routes are already async in FastAPI).

3. **Given** the refactored module, **when** line count is measured, **then** it is reduced by at least 40% compared to the current ~1,400 LOC.

4. **Given** the async versions use the async connection pool, **when** concurrent console requests arrive, **then** they no longer block the event loop (current sync queries block via `get_db_connection()`).

**Edge Cases:**
- Any non-async callers (background workers, scripts) that import console queries need to be identified and migrated or wrapped with `asyncio.run()`.
- Connection pool behavior differences between sync psycopg2 and async asyncpg.
- Transaction semantics: ensure any multi-statement operations maintain atomicity.

---

### T-1: Console Queries Test Suite

**As an** engineer, **I want** comprehensive tests for `console_queries.py`, **so that** the largest service file (1,400+ LOC) has regression protection before we refactor it.

**Priority:** P1 | **Effort:** L | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** `console_queries.py` has ~30 public functions, **when** the test suite is complete, **then** at least 80% of public functions have at least one test.

2. **Given** `get_all_agents()` is tested, **when** the test runs, **then** it validates correct SQL construction, handles empty results, and verifies error logging on failure.

3. **Given** `get_conversations()` is tested, **when** filter parameters are passed, **then** the test verifies correct SQL WHERE clause construction for each filter type.

4. **Given** all tests pass, **when** the test suite runs in CI, **then** it completes in under 30 seconds using mocked database connections.

**Edge Cases:**
- Functions that return different types based on conditions (dict vs None).
- Functions with optional parameters that change query structure.
- Error handling paths (database connection failures).

---

### T-2: Dispatcher Test Suite

**As an** engineer, **I want** tests covering the dispatcher's consent gate, conversation logging, and usage tracking, **so that** TCPA compliance logic and usage metering are verified.

**Priority:** P1 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a contact has `consent_status = 'revoked'`, **when** the dispatcher processes an outbound message, **then** the message is blocked and the blocking reason is logged.

2. **Given** a message is dispatched successfully, **when** the conversation log is checked, **then** the message, response, and metadata are recorded.

3. **Given** an agent has hit their daily message limit, **when** the dispatcher processes an outbound message, **then** usage tracking correctly increments and the limit is enforced.

4. **Given** the consent gate is tested with edge cases (consent_status = NULL, expired consent, consent granted then revoked in same day), **when** each scenario is dispatched, **then** the correct blocking/allowing behavior is verified.

**Edge Cases:**
- Messages sent via different channels (SMS vs email) — consent may differ.
- Race condition: consent revoked between dispatch decision and actual send.

---

### T-3: Integration Tests with Real DB (RLS Verification)

**As a** security engineer, **I want** integration tests that verify PostgreSQL RLS policies with real database connections, **so that** tenant isolation is proven correct, not assumed.

**Priority:** P1 | **Effort:** L | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** two agents (A and B) with contacts in the database, **when** Agent A's context is set via `set_agent_context()`, **then** queries return only Agent A's contacts.

2. **Given** Agent A's context is set, **when** a query attempts to read Agent B's messages, **then** zero rows are returned (not an error — RLS filters silently).

3. **Given** Agent A's context is set, **when** an INSERT is attempted for Agent B's contact, **then** the RLS policy blocks the insert.

4. **Given** the test suite, **when** it runs, **then** it uses a dedicated test database with the same RLS policies as production (applied from `schema.sql`).

**Edge Cases:**
- Service-role connections that bypass RLS (console queries) — verify these only exist in intended code paths.
- RLS interaction with JOINs across tables with different policies.
- New tables added without RLS policies — test should flag tables missing policies.

---

### T-4: Security Test Suite

**As a** security engineer, **I want** automated tests for authentication bypass, CSRF, and webhook signature validation, **so that** security regressions are caught in CI.

**Priority:** P1 | **Effort:** M | **Dependencies:** S-3, S-4 (webhook signature stories)

**Acceptance Criteria:**

1. **Given** a request to any `/console/*` route without a session cookie, **when** the request is made, **then** it is redirected to `/console/login` (not a 500 or data leak).

2. **Given** a POST to a console write endpoint without a valid CSRF token, **when** the request is made, **then** it returns 403.

3. **Given** a POST to `/webhooks/email/inbound` without a valid SendGrid signature, **when** `SENDGRID_INBOUND_SECRET` is configured, **then** it returns 401.

4. **Given** a POST to `/webhooks/vapi/post-call` without `x-vapi-secret`, **when** `VAPI_WEBHOOK_SECRET` is configured, **then** it returns 401.

**Edge Cases:**
- Expired session cookies — should redirect to login, not error.
- CSRF token reuse after logout.
- Webhook endpoints receiving GET requests instead of POST.

---

### T-5: RAG Search Accuracy Tests

**As an** engineer, **I want** a test suite that measures RAG search result quality against known-good queries, **so that** changes to the embedding pipeline or search logic don't silently degrade answer quality.

**Priority:** P2 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a curated set of 20+ test documents are ingested, **when** a query like "What are the HOA fees for 123 Oak St?" is searched, **then** the top-1 result contains the relevant document chunk.

2. **Given** the test suite runs, **when** accuracy is measured as "relevant result in top-3", **then** it exceeds 80% across the test corpus.

3. **Given** a change is made to chunk size, overlap, or embedding model, **when** the test suite re-runs, **then** accuracy delta is reported so regressions are visible.

**Edge Cases:**
- Queries with typos or colloquial language.
- Documents with very similar content (e.g., two listings on the same street).
- Empty corpus — should return empty results, not error.

---

### T-6: Load/Stress Test Harness

**As a** platform operator, **I want** a load test harness that simulates concurrent agent and client message traffic, **so that** we can identify breaking points before they affect real agents.

**Priority:** P2 | **Effort:** L | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** the test harness is configured for 100 concurrent agents, **when** the load test runs, **then** it sends simulated inbound messages at a configurable rate (1-100 msg/sec).

2. **Given** the test is running, **when** it completes, **then** it produces a report with p50/p95/p99 response times, error rates, and database connection pool utilization.

3. **Given** the load test framework (e.g., Locust or k6), **when** an engineer runs `make load-test`, **then** the test runs against a staging environment.

**Edge Cases:**
- Test must not accidentally send real SMS via Twilio — mock or dry-run mode required.
- Connection pool exhaustion — test should identify the breaking point.
- Memory leaks during sustained load (monitor RSS over time).

---

### B-1: Dependency Injection for Services

**As an** engineer, **I want** services to be injected via FastAPI's dependency system instead of module-level singletons, **so that** tests can easily swap in mocks and service lifecycle is managed by the framework.

**Priority:** P2 | **Effort:** XL | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** the main services (Anthropic, Twilio, RAG, Redis), **when** they are refactored, **then** each is available as a FastAPI `Depends()` parameter in route handlers.

2. **Given** a test needs to mock the Anthropic service, **when** it uses `app.dependency_overrides[get_anthropic_service]`, **then** the mock is injected without modifying production code.

3. **Given** the migration is done incrementally, **when** a service is migrated, **then** the old `get_*()` factory function continues to work as a compatibility shim that delegates to the DI container.

**Edge Cases:**
- Background workers and pipeline code that run outside of request context need a different DI mechanism (e.g., explicit container or parameter passing).
- Circular dependencies between services.
- Startup ordering: some services depend on others being initialized first.

---

### B-2: Eliminate Bare Except Swallowing

**As an** engineer, **I want** bare `except Exception` blocks to be replaced with specific exception handling that preserves error visibility, **so that** real bugs are not silently swallowed.

**Priority:** P2 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a codebase audit identifies all `except Exception` blocks, **when** each is reviewed, **then** it is categorized as: (a) should reraise, (b) should catch specific exceptions, (c) is intentional and gets a `# noqa` comment with justification.

2. **Given** the audit is complete, **when** category (a) and (b) blocks are refactored, **then** at least 80% of bare excepts are either removed or narrowed to specific exception types.

3. **Given** a linting rule is added, **when** new code introduces a bare `except Exception:` that swallows without logging, **then** the linter flags it.

**Edge Cases:**
- Error handling in webhook endpoints where returning 500 would cause Twilio/SendGrid to retry indefinitely — these genuinely need broad catches.
- Background workers where an unhandled exception kills the worker loop.
- Exception chaining: ensure `raise ... from e` is used where appropriate.

---

### B-3: Structured Return Types with Type Hints

**As an** engineer, **I want** all public functions to have return type annotations using Pydantic models or TypedDicts, **so that** IDE autocompletion works and type checkers can catch bugs.

**Priority:** P2 | **Effort:** L | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** the top 20 most-called functions (by import count), **when** they are annotated, **then** each has an explicit return type that is a Pydantic model, TypedDict, or a primitive (not `dict` or `Any`).

2. **Given** `mypy` is configured in `pyproject.toml`, **when** it runs in CI, **then** it reports zero errors on annotated files (incremental adoption is OK).

3. **Given** a function returns `dict | None`, **when** it is refactored, **then** it returns `AgentSummary | None` (or equivalent typed model).

**Edge Cases:**
- Functions that return different shapes depending on input (polymorphic returns) — use Union types or overloads.
- Backward compatibility: existing callers that access dict keys should work with model attribute access.

---

### B-5: Configurable Model Names

**As a** platform operator, **I want** Claude model IDs to be configurable via environment variables, **so that** upgrading to a new model version (e.g., Haiku 3.5 to Haiku 4) requires only a config change, not a code deploy.

**Priority:** P2 | **Effort:** S | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** `CLAUDE_HAIKU_MODEL` and `CLAUDE_SONNET_MODEL` are set in environment, **when** the Anthropic service initializes, **then** it uses those model IDs instead of hardcoded values.

2. **Given** the environment variables are not set, **when** the service initializes, **then** it uses sensible defaults (current hardcoded values).

3. **Given** an invalid model ID is configured, **when** the first API call fails, **then** the error message clearly indicates the model ID is invalid and shows the configured value.

**Edge Cases:**
- Model-specific parameters (max tokens, temperature) may differ between versions — document any version-specific constraints.
- Feature flags that use Haiku for simple tasks and Sonnet for complex — ensure the tier selection logic still works with custom model names.

---

### B-6: Correct Monthly Recurrence with relativedelta

**As a** real estate agent, **I want** monthly follow-up triggers to fire on the same day each month, **so that** my anniversary check-ins and monthly market updates arrive predictably.

**Priority:** P1 | **Effort:** XS | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a trigger is set for the 15th of January with monthly recurrence, **when** the next fire date is calculated, **then** it is February 15th (not February 14th, which `timedelta(days=30)` would produce).

2. **Given** a trigger fires on January 31st with monthly recurrence, **when** the next date is calculated for February, **then** it falls on February 28th (or 29th in leap year), not March 2nd.

3. **Given** `dateutil.relativedelta` is used, **when** the import is added, **then** `python-dateutil` is already in `requirements.txt` (verify, add if missing).

**Edge Cases:**
- Triggers set for the 29th, 30th, or 31st of a month — relativedelta handles this correctly (falls back to last day of shorter months).
- Timezone interactions: the "same day" must be evaluated in the agent's local timezone.

---

### B-7: Correct Annual Recurrence with relativedelta

**As a** real estate agent, **I want** annual triggers (e.g., home purchase anniversaries) to fire on the correct date every year, **so that** my clients receive anniversary messages on the actual date.

**Priority:** P1 | **Effort:** XS | **Dependencies:** B-6 (same fix pattern)

**Acceptance Criteria:**

1. **Given** a trigger is set for March 1st with annual recurrence, **when** the next fire date is calculated, **then** it is March 1st of the following year.

2. **Given** a trigger is set for February 29th (leap year), **when** the next year is not a leap year, **then** the trigger fires on February 28th.

3. **Given** `timedelta(days=365)` is replaced with `relativedelta(years=1)`, **when** the change is applied, **then** existing triggers recalculate their next fire date correctly.

**Edge Cases:**
- Triggers that have already drifted due to the `timedelta(days=365)` bug — consider a one-time data migration to correct stored next-fire dates.

---

### E-1: Pydantic v2 Migration Patterns

**As an** engineer, **I want** all Pydantic models to use v2 patterns, **so that** we benefit from the 5-50x validation speed improvement and avoid deprecation warnings.

**Priority:** P2 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** the codebase uses `pydantic_settings`, **when** all models are audited, **then** any v1 patterns (e.g., `class Config:`, `validator` decorator, `schema_extra`) are migrated to v2 equivalents (`model_config`, `field_validator`, `json_schema_extra`).

2. **Given** Pydantic v2 is fully adopted, **when** the test suite runs, **then** zero `PydanticDeprecatedSince20` warnings are emitted.

3. **Given** `model_config` is already used in `Settings` (app/config.py), **when** all other models are migrated, **then** the pattern is consistent across the codebase.

**Edge Cases:**
- Custom validators that rely on v1 behavior (e.g., `pre=True` validators with different semantics in v2).
- Serialization changes: v2 `.model_dump()` vs v1 `.dict()`.

---

### E-2: Template Component Organization

**As an** engineer, **I want** Jinja2 templates organized by component (e.g., `templates/components/agent-card.html`), **so that** template reuse is natural and the template directory doesn't become a flat list of files.

**Priority:** P2 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** the current template directory, **when** templates are reorganized, **then** they follow a structure: `templates/layouts/`, `templates/pages/`, `templates/components/`, `templates/partials/`.

2. **Given** HTMX partial responses, **when** a component is updated via an HTMX swap, **then** the partial template is in `templates/partials/` and is independently renderable.

3. **Given** Jinja2 `include` and `extends` are used, **when** templates reference each other, **then** paths use the new directory structure.

**Edge Cases:**
- Existing bookmarked URLs or cached template references in browsers.
- Template loading performance with deeper directory nesting (Jinja2 caches compiled templates, so minimal impact).

---

### E-3: CSS Design Token System

**As a** designer/engineer, **I want** CSS custom properties (design tokens) for colors, spacing, typography, and shadows, **so that** visual consistency is maintained and theming is possible.

**Priority:** P2 | **Effort:** M | **Dependencies:** None

**Acceptance Criteria:**

1. **Given** a `tokens.css` file is created, **when** it defines variables like `--color-primary`, `--spacing-md`, `--font-size-body`, **then** all existing CSS references to raw color/spacing values are replaced with token references.

2. **Given** a component uses `color: #2563eb`, **when** it is migrated, **then** it uses `color: var(--color-primary)`.

3. **Given** the token system is in place, **when** a future dark mode or white-label theme is needed, **then** only the token values need to change — no component CSS modifications.

**Edge Cases:**
- CSS specificity conflicts when migrating existing styles.
- Fallback values for older browsers (though console is internal tool, so modern browser assumption is OK).

---

### E-4: Accessibility Basics (ARIA, Focus Management)

**As a** console operator using keyboard navigation or a screen reader, **I want** the console to follow WCAG 2.1 AA basics, **so that** the tool is usable by operators with disabilities.

**Priority:** P2 | **Effort:** L | **Dependencies:** E-2, E-3 (template and CSS work)

**Acceptance Criteria:**

1. **Given** every interactive element (buttons, links, form inputs), **when** inspected, **then** it has an accessible name (visible label, `aria-label`, or `aria-labelledby`).

2. **Given** a modal dialog opens (e.g., confirmation dialog), **when** it opens, **then** focus is trapped inside the modal and returns to the trigger element on close.

3. **Given** the dashboard is navigated via keyboard only, **when** Tab is pressed sequentially, **then** focus follows a logical order through the page.

4. **Given** HTMX dynamically updates a region, **when** new content loads, **then** an `aria-live` region announces the change to screen readers.

**Edge Cases:**
- HTMX swaps that replace focused elements — focus must be restored to a sensible location.
- Color contrast ratios — token system (E-3) must use colors meeting 4.5:1 contrast ratio.

---

## 4. Backlog Summary Table

| ID | Story Title | Epic | Priority | Effort | Dependencies | Status |
|----|------------|------|----------|--------|-------------|--------|
| S-1 | Per-user console auth with audit trail | Security | P0 | L | A-4 | Pending |
| S-2 | Authorization guard on console queries | Security | P0 | S | None | Pending |
| S-3 | SendGrid webhook signature verification | Security | P0 | S | None | Pending |
| S-4 | Block Vapi webhook without secret in prod | Security | P0 | XS | None | Pending |
| S-5 | Parameterized column updates in tools | Security | P1 | S | None | Pending |
| S-6 | Proper HTML sanitization for KB uploads | Security | P1 | S | None | Pending |
| S-7 | Rate limiting on console login | Security | P1 | S | None | Pending |
| P-1 | Eliminate N+1 queries in agent list | Performance | P0 | M | None | Pending |
| P-2 | Bounded listing search in assembler | Performance | P0 | M | None | Pending |
| P-3 | Async conversation summarization | Performance | P0 | M | None | Pending |
| P-4 | Cached conversation history | Performance | P1 | M | A-3 | Pending |
| P-5 | Native vector params in RAG search | Performance | P1 | XS | None | Pending |
| P-6 | Selective column load in daily scanner | Performance | P1 | XS | None | Pending |
| A-1 | Message queue for pipeline processing | Architecture | P1 | XL | A-2 | Pending |
| A-2 | Separate worker from web server | Architecture | P1 | L | None | Pending |
| A-3 | Redis caching layer for hot data | Architecture | P1 | L | None | Pending |
| A-4 | Database migration tooling (Alembic) | Architecture | P1 | M | None | Pending |
| A-5 | Consolidate sync/async query paths | Architecture | P1 | L | None | Pending |
| T-1 | Console queries test suite | Testing | P1 | L | None | Pending |
| T-2 | Dispatcher test suite | Testing | P1 | M | None | Pending |
| T-3 | Integration tests with real DB / RLS | Testing | P1 | L | None | Pending |
| T-4 | Security test suite | Testing | P1 | M | S-3, S-4 | Pending |
| T-5 | RAG search accuracy tests | Testing | P2 | M | None | Pending |
| T-6 | Load/stress test harness | Testing | P2 | L | None | Pending |
| B-1 | Dependency injection for services | Code Quality | P2 | XL | None | Pending |
| B-2 | Eliminate bare except swallowing | Code Quality | P2 | M | None | Pending |
| B-3 | Structured return types | Code Quality | P2 | L | None | Pending |
| B-5 | Configurable model names | Code Quality | P2 | S | None | Pending |
| B-6 | Correct monthly recurrence | Code Quality | P1 | XS | None | Pending |
| B-7 | Correct annual recurrence | Code Quality | P1 | XS | B-6 | Pending |
| E-1 | Pydantic v2 migration | Standards | P2 | M | None | Pending |
| E-2 | Template component organization | Standards | P2 | M | None | Pending |
| E-3 | CSS design token system | Standards | P2 | M | None | Pending |
| E-4 | Accessibility basics | Standards | P2 | L | E-2, E-3 | Pending |

---

## 5. Open Questions

**OQ-1: Console user management scope (S-1)**
How many console operators do we expect? Is it just 2-3 internal team members, or will each agent also get console access? This affects whether we need a full RBAC system or just a simple users table with admin/viewer roles.

**OQ-2: SendGrid webhook version (S-3)**
Which SendGrid inbound parse version are we using (v2 or v3)? Signature verification differs between them. Need to confirm before implementation.

**OQ-3: Message queue technology choice (A-1)**
Redis Streams is simplest given Redis is already in the stack. However, if we anticipate needing more sophisticated routing (e.g., per-agent queues, priority lanes), should we evaluate arq or celery? This affects effort estimate (XL vs XXL).

**OQ-4: Worker separation deployment target (A-2)**
Are we staying on Railway? If so, we can use Railway's service separation. If we're considering moving to Kubernetes or ECS, the containerization approach differs. Need deployment target confirmed.

**OQ-5: Test database strategy (T-3)**
Should integration tests use a local PostgreSQL via Docker (testcontainers-python), a dedicated Supabase test project, or the existing dev database with transaction rollback? Each has different CI setup costs.

**OQ-6: Load test target environment (T-6)**
Do we have a dedicated staging environment for load tests? Running load tests against production or shared dev would be dangerous.

**OQ-7: Recurrence drift correction (B-6, B-7)**
For triggers that have already drifted due to the `timedelta` bugs, should we run a one-time data migration to correct stored `next_fire_at` values, or just let them self-correct on next fire?

**OQ-8: DI migration scope (B-1)**
Should we migrate all services at once (big bang) or one service at a time with the compatibility shim? Big bang is cleaner but riskier.

---

## 6. Sequencing Recommendation

### Phase 1: Foundation & Quick Wins (Weeks 1-2)
**Goal:** Close security gaps and eliminate the worst performance bottlenecks.

Execute in parallel:
- **S-2** (authorization guard) — XS effort, high security impact
- **S-3** (SendGrid signature) — S effort, closes open attack vector
- **S-4** (Vapi production block) — XS effort, one-line fix
- **P-5** (native vector params) — XS effort, free perf win
- **P-6** (selective columns in scanner) — XS effort, free perf win
- **B-6** (monthly recurrence) — XS effort, active bug causing drift
- **B-7** (annual recurrence) — XS effort, same as above

Then:
- **P-1** (N+1 queries) — M effort, visible dashboard perf improvement
- **P-2** (bounded listing search) — M effort, prevents OOM with large listing counts
- **P-3** (async summarization) — M effort, 200-400ms latency reduction per message

### Phase 2: Security Completion & Migration Tooling (Weeks 3-4)
- **A-4** (Alembic setup) — Prerequisite for S-1's schema changes
- **S-7** (rate limiting) — S effort
- **S-6** (HTML sanitization) — S effort
- **S-5** (parameterized columns) — S effort
- **S-1** (per-user auth) — L effort, requires A-4 for users table migration
- **B-5** (configurable models) — S effort, quick win

### Phase 3: Architecture & Testing (Weeks 5-8)
Execute in parallel tracks:

**Track A — Architecture:**
- **A-5** (consolidate sync/async) — L effort, reduces codebase by 700+ LOC
- **A-3** (Redis caching) — L effort, prerequisite for P-4
- **P-4** (cached conversation history) — M effort, depends on A-3
- **A-2** (worker separation) — L effort, prerequisite for A-1

**Track B — Testing:**
- **T-1** (console queries tests) — Before A-5 refactor begins
- **T-2** (dispatcher tests) — Independent
- **T-3** (integration tests / RLS) — Independent
- **T-4** (security tests) — After S-3, S-4 are done

### Phase 4: Architecture Completion (Weeks 9-10)
- **A-1** (message queue) — XL effort, depends on A-2

### Phase 5: Code Quality & Standards (Weeks 11-16)
Lower urgency, can be interleaved with feature work:
- **B-2** (bare except cleanup) — Can be done incrementally, file-by-file
- **B-3** (return type hints) — Can be done incrementally
- **E-1** (Pydantic v2 migration)
- **E-2** (template organization)
- **E-3** (CSS design tokens)
- **B-1** (dependency injection) — XL effort, do last as it touches everything
- **E-4** (accessibility) — After E-2 and E-3
- **T-5** (RAG accuracy tests)
- **T-6** (load test harness)

### Critical Path
```
A-4 (Alembic) → S-1 (per-user auth)
A-2 (worker separation) → A-1 (message queue)
A-3 (Redis caching) → P-4 (cached history)
T-1 (console query tests) → A-5 (consolidate sync/async)
E-2 + E-3 → E-4 (accessibility)
B-6 → B-7 (recurrence fixes)
S-3 + S-4 → T-4 (security tests)
```

### Effort Summary
| Size | Count | Estimated Days Each | Total Days |
|------|-------|-------------------|------------|
| XS | 5 | 0.5 | 2.5 |
| S | 6 | 1-2 | 9 |
| M | 10 | 3-5 | 40 |
| L | 8 | 5-8 | 52 |
| XL | 2 | 10-15 | 25 |
| **Total** | **31** | | **~128 days** |

At one full-time engineer, this is approximately 6 months of work. With two engineers running parallel tracks (one on security/performance, one on architecture/testing), this compresses to approximately 3-4 months.

---

*End of backlog. Awaiting Solomon review and open question resolution before engineering handoff.*
