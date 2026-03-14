# Calloway Architecture Audit Report

**Date:** 2026-03-14
**Auditor:** Atlas, Engineering Lead
**Scope:** Full codebase — all major components, services, workers, schema, and dependencies

---

## 1. Executive Summary

Overall system health: **Yellow** (Solid foundation with addressable issues)

Calloway is a well-structured SaaS application with clear separation of concerns, proper tenant isolation via PostgreSQL RLS, and thoughtful use of AI model tiering. The codebase demonstrates strong pragmatic engineering. However, several issues need attention before scaling beyond ~50 agents, and a handful of security findings warrant prompt remediation.

| Component | Health | Notes |
|-----------|--------|-------|
| `app/main.py` | **Green** | Clean startup, proper lifespan, correlation middleware |
| `app/config.py` | **Green** | Production secret validation, pydantic-settings, env-based |
| `app/db/connection.py` | **Green** | Proper pooling (sync + async), RLS helpers, fallbacks |
| `app/db/schema.sql` | **Green** | Comprehensive RLS, good indexes, clean normalization |
| `app/api/webhooks.py` | **Yellow** | Twilio sig validation good; sync blocking in background tasks |
| `app/api/console.py` | **Green** | CSRF protection, auth checks, proper input validation |
| `app/api/console_auth.py` | **Yellow** | Timing-safe compare, but single shared password |
| `app/pipeline/handlers.py` | **Yellow** | Well-structured command dispatch; LLM-as-parser risk |
| `app/pipeline/assembler.py` | **Green** | Smart token budgeting, summary integration |
| `app/pipeline/dispatcher.py` | **Yellow** | Consent gate good; synchronous summarization in hot path |
| `app/services/anthropic_service.py` | **Yellow** | In-memory usage tracking will lose data on restart |
| `app/services/console_queries.py` | **Yellow** | Parameterized queries; N+1 in agent list; no pagination on some views |
| `app/services/rag_service.py` | **Green** | Clean HNSW search, proper deduplication, RLS-aware |
| `app/services/embedding_service.py` | **Green** | Batching, retry with backoff, proper query/document split |
| `app/services/summarization_service.py` | **Green** | Incremental + full re-summarization, drift correction |
| `app/worker/trigger_worker.py` | **Yellow** | No distributed locking; single-process polling |
| `app/worker/daily_scanner.py` | **Yellow** | Sequential agent processing; no error isolation |
| `app/models/schemas.py` | **Green** | Clean Pydantic models, good type coverage |
| `requirements.txt` | **Yellow** | Pinned versions good; missing security-critical packages |

---

## 2. Critical Issues (P0 — Fix Immediately)

### C-1: Trigger Worker Has No Distributed Lock — Double-Firing Risk
**File:** `app/worker/trigger_worker.py`, lines 34-47
**Severity:** Critical
**Impact:** If multiple worker instances run (e.g., Railway scales horizontally), the same trigger fires multiple times. A `SELECT ... FOR UPDATE SKIP LOCKED` query or Redis-based lock is needed.

```
# Current: no locking
rows = conn.execute(
    """SELECT * FROM triggers
       WHERE status = 'pending' AND scheduled_at <= %s
       ORDER BY scheduled_at LIMIT 50""",
    [now],
).fetchall()
```

**Fix:** Use `SELECT ... FOR UPDATE SKIP LOCKED` within a transaction, and atomically mark triggers as `in_progress` before processing.

### C-2: In-Memory Token Usage Tracking Loses Data on Restart
**File:** `app/services/anthropic_service.py`, lines 30-48
**Severity:** High
**Impact:** `AnthropicClient._token_usage` is a plain dict. On process restart, crash, or deployment, all accumulated usage data is lost. The dispatcher does persist to `usage_metrics`, but the client's own tracking (used by `get_usage()`) is ephemeral and inconsistent.

**Fix:** Remove the in-memory tracking entirely (it duplicates the DB-persisted metrics in dispatcher) or flush to DB/Redis periodically.

### C-3: Synchronous Blocking Calls in Async Pipeline
**File:** `app/api/webhooks.py`, line 173 (via `process_inbound_message`)
**Severity:** High
**Impact:** `process_inbound_message` is an `async def` added as a background task, but internally it calls synchronous functions: `resolve_contact()`, `classify_intent()`, `route_and_handle()`, `dispatch()` — all of which make synchronous DB calls via `get_db_connection()`. This blocks the async event loop, degrading throughput under load.

**Fix:** Either (a) run the sync pipeline in `asyncio.to_thread()`, or (b) migrate the hot path to fully async DB calls using the async pool.

### C-4: Feedback Update SQL Has Logic Error
**File:** `app/api/webhooks.py`, lines 132-143
**Severity:** High
**Impact:** The `UPDATE messages SET feedback_score = %s WHERE conversation_id IN (...) AND ai_generated = true ORDER BY created_at DESC LIMIT 1` query is invalid in PostgreSQL — `UPDATE` does not support `ORDER BY` or `LIMIT`. This silently updates ALL matching ai_generated messages or fails depending on the driver.

**Fix:** Use a subquery: `WHERE id = (SELECT id FROM messages WHERE ... ORDER BY created_at DESC LIMIT 1)`.

---

## 3. Security Findings

### S-1: Single Shared Password for Console — No Per-User Auth (Medium)
**File:** `app/config.py`, line 56; `app/api/console_auth.py`, line 29-32
**Impact:** All operators share one password (`CONSOLE_PASSWORD`). No audit trail of who performed which action. No role-based access control.
**Recommendation:** Implement per-user accounts with hashed passwords (bcrypt/argon2) and action audit logging. Short-term: add an operator name to the session for audit trails.

### S-2: Console Queries Bypass RLS by Design — No Authorization Layer (Medium)
**File:** `app/services/console_queries.py`, line 1-5
**Impact:** Console queries intentionally skip `set_agent_context()` for cross-tenant visibility. This is correct for an operator console, but there is no authorization check within the query layer itself — it trusts the caller completely. If any unauthenticated route accidentally calls these functions, full cross-tenant data is exposed.
**Recommendation:** Add an explicit `require_operator_context()` check at the query layer, not just at the route level.

### S-3: Email Inbound Webhook Has No Signature Verification (Medium)
**File:** `app/api/webhooks.py`, lines 422-435
**Impact:** The `/webhooks/email/inbound` endpoint accepts any POST request. There is a `SENDGRID_INBOUND_SECRET` in config but it is never validated. An attacker can forge inbound emails to inject messages into the pipeline.
**Fix:** Validate the SendGrid webhook signature using `SENDGRID_INBOUND_SECRET`.

### S-4: Vapi Webhook Proceeds Without Secret When Not Configured (Low)
**File:** `app/api/webhooks.py`, lines 303-310
**Impact:** When `VAPI_WEBHOOK_SECRET` is empty, the endpoint logs a warning but processes the request anyway. This should be blocked in production.
**Fix:** Return 401 when secret is not configured in production environment.

### S-5: Dynamic SQL Column Names in Tool Update Functions (Low)
**Files:** `app/tools/contacts.py`, line 147; `app/tools/listings.py`, line 105; `app/tools/transactions.py`, line 74
**Impact:** Column names in `SET` clauses are built from dict keys via f-strings. While the current code filters against allowlists (e.g., `contacts.py` line 130 filters to allowed keys, `listings.py` line 92), the pattern is fragile — a future developer could add a key without realizing it becomes a column name.
**Recommendation:** Add an explicit allowlist check + assertion that validates column names against a hardcoded tuple, separate from the filtering logic.

### S-6: XSS Risk in HTML Sanitization (Low)
**File:** `app/api/console.py`, lines 847-848
**Impact:** KB document upload strips `<script>` tags and HTML tags with regex. Regex-based HTML sanitization is notoriously bypassable (e.g., `<img onerror=...>`, encoding tricks). Since this content goes into embeddings (not rendered as HTML), actual risk is low.
**Recommendation:** Use `bleach` or `html.escape()` for robust sanitization.

### S-7: No Rate Limiting on Console Login (Low)
**File:** `app/api/console.py`, lines 60-68
**Impact:** The login endpoint has no rate limiting, allowing brute-force attacks against the shared password.
**Recommendation:** Add IP-based rate limiting (e.g., `slowapi` or Redis-backed counter).

---

## 4. Performance Findings

### P-1: N+1 Queries in Agent List (Console)
**File:** `app/services/console_queries.py`, lines 123-141
**Impact:** `get_all_agents()` uses correlated subqueries for `contact_count`, `messages_today`, `last_active`, and `errors_24h` — four subqueries per agent row. At 100 agents, this is 400+ subqueries per dashboard load.
**Fix:** Use `LEFT JOIN` with aggregation, or pre-compute these stats in a materialized view refreshed by the trigger worker.

### P-2: Unbounded Query in `_find_referenced_listing`
**File:** `app/pipeline/assembler.py`, lines 149-158
**Impact:** `search_listings(agent_id, filters={"status": "active"})` loads ALL active listings into memory, then iterates to find an address match. For agents with hundreds of listings, this wastes memory and DB time on every listing_qa intent.
**Fix:** Use a SQL `ILIKE` query to search server-side, or limit to a reasonable count with relevance scoring.

### P-3: Synchronous Summarization in Dispatch Hot Path
**File:** `app/pipeline/dispatcher.py`, lines 300-322
**Impact:** `_maybe_summarize_conversation` runs synchronously after every non-command message dispatch. It makes a DB query to check thresholds, and when triggered, calls Haiku (200-400ms). This adds latency to every message response for long conversations.
**Fix:** Move summarization to the trigger worker or a background task queue. The current comment says "adds minimal latency" but at scale this compounds.

### P-4: Full Conversation History Load on Every Message
**File:** `app/pipeline/assembler.py`, lines 130-146
**Impact:** Every inbound message loads up to 20 recent messages from the DB. For high-frequency conversations, this is a query on every single message.
**Recommendation:** Cache recent conversation history in Redis with a short TTL (30-60s). Invalidate on new message.

### P-5: RAG Search Passes Embedding Vector as String
**File:** `app/services/rag_service.py`, lines 295-316
**Impact:** The query embedding is passed via `str(query_embedding)` which converts a 512-float list to a string for every search. This works but forces the DB to parse the string representation. Use proper pgvector parameter binding.

### P-6: `_get_all_active_agents()` Loads Full Agent Records
**File:** `app/worker/daily_scanner.py`, lines 377-381
**Impact:** `SELECT * FROM agents` loads every column (including `google_oauth` JSONB, `style_profile` JSONB, etc.) for every agent, every daily scan. At 1000+ agents, this is a large payload.
**Fix:** Select only the columns needed for scanning, or paginate.

---

## 5. Architecture Recommendations

### A-1: Extract Message Queue for Pipeline Processing
**Current:** Twilio webhook -> FastAPI background task -> sync pipeline
**Problem:** BackgroundTasks are in-process. If the app restarts mid-processing, messages are lost. No retry, no dead-letter, no backpressure.
**Recommendation:** Introduce Redis Streams or a lightweight queue (e.g., `arq`, `celery` with Redis) as the message broker. The webhook enqueues, a separate worker dequeues and processes. This also solves C-3 (blocking async).

### A-2: Separate Worker Process from Web Server
**Current:** Workers (`trigger_worker.py`, `daily_scanner.py`) appear to be run separately but share the same codebase and DB pools.
**Recommendation:** Formalize worker deployment as a separate container/process with its own scaling. Document the startup commands in a `Procfile` or `docker-compose.yml`.

### A-3: Add Caching Layer for Hot Data
**Data that should be cached (Redis):**
- Agent config (changes rarely, read on every request): `app/services/agent_config.py`
- Active listings per agent (changes on update): `app/tools/listings.py`
- Recent conversation history: `app/pipeline/assembler.py`

**Current:** Every request hits Postgres directly. Redis is in the stack (`app/services/redis_pool.py`) but appears unused except by the pool initialization.

### A-4: Introduce Database Migration Tool
**Current:** `schema.sql` is a monolithic DDL file. Alembic is in `requirements.txt` but there are no migration files visible.
**Recommendation:** Set up Alembic migrations directory with an initial migration from the current schema. All future changes should be migrations, not manual SQL.

### A-5: Consolidate Sync/Async Code Paths
**Current:** Console queries exist in both sync (`get_system_pulse()`) and async (`async_get_system_pulse()`) versions — massive code duplication throughout `console_queries.py` (the file is 1400+ lines, roughly half is duplicated sync/async).
**Recommendation:** Standardize on async queries for the FastAPI web layer. Keep sync only for workers. Remove the sync duplicates from console_queries.

---

## 6. Best Practice Gaps

### B-1: No Dependency Injection — Singleton Anti-Pattern
**Files:** `app/services/anthropic_service.py` (line 258-265), `app/services/rag_service.py` (line 390-398), `app/services/embedding_service.py` (line 177-186)
**Issue:** All services use module-level `_service` globals with `get_*()` factory functions. This makes testing harder (must monkeypatch globals) and prevents different configurations per context.
**Recommendation:** Use FastAPI's `Depends()` injection pattern, or at minimum make the singletons configurable/resettable for testing.

### B-2: Bare `except Exception` Swallowing Errors
**Prevalence:** Dozens of instances across the codebase, especially in:
- `app/api/webhooks.py` lines 63-64 (silent `pass` on notification failure)
- `app/pipeline/dispatcher.py` multiple locations
- `app/worker/trigger_worker.py` lines 29-30
**Issue:** Many `except Exception` blocks log the error but continue silently. While this is appropriate for non-critical paths (notifications, metrics), some of these hide real bugs.
**Recommendation:** Categorize exception handlers: (a) truly non-critical (notifications) can stay, (b) data integrity paths (conversation logging, trigger creation) should raise or retry.

### B-3: Missing Type Hints on Return Values
**Files:** Most functions in `console_queries.py`, `daily_scanner.py`
**Issue:** Functions return `dict`, `list[dict]`, or `None` without structured types. The Pydantic models exist in `schemas.py` but aren't used at the service layer boundary.
**Recommendation:** Define response models for service layer returns, or at minimum use TypedDict for dict returns.

### B-4: No API Documentation / OpenAPI Configuration
**File:** `app/main.py`
**Issue:** FastAPI auto-generates OpenAPI docs, but webhook endpoints use `Request` directly (no typed request/response models). The console endpoints return HTMLResponse. Only the health endpoint would have useful API docs.
**Recommendation:** Add Pydantic request/response models to webhook endpoints for proper API documentation.

### B-5: Hardcoded Model Names
**File:** `app/services/anthropic_service.py`, lines 16-17
**Issue:** Model IDs are hardcoded constants. When Anthropic releases new model versions, this requires a code change and deployment.
**Recommendation:** Make model IDs configurable via environment variables with these as defaults.

### B-6: Monthly Recurrence Uses `timedelta(days=30)`
**File:** `app/worker/trigger_worker.py`, line 184
**Issue:** Monthly recurrence adds exactly 30 days rather than advancing to the same day next month. Over time, triggers drift (e.g., a March 31 trigger becomes April 30, then May 30, etc.).
**Fix:** Use `dateutil.relativedelta(months=1)` (python-dateutil is already in requirements).

### B-7: Annual Recurrence Uses `timedelta(days=365)`
**File:** `app/worker/trigger_worker.py`, line 183
**Issue:** Ignores leap years. Same fix as B-6.

---

## 7. Testing Gaps

The test suite has 34 files covering webhooks, handlers, classifiers, normalizer, contacts, listings, triggers, voice, email, billing, RAG, summarization, and structured logging. This is good coverage for a project of this size.

### Gaps identified:

| Gap | What's Missing | Risk |
|-----|---------------|------|
| No load/stress tests | Pipeline behavior under concurrent messages is untested | High — async blocking issues (C-3) would surface here |
| No console_queries tests | The largest service file (1400+ LOC) has no dedicated tests | Medium — SQL bugs hide |
| No dispatcher tests | `dispatcher.py` consent gate, conversation logging, usage tracking are untested directly | Medium |
| No integration tests with real DB | All tests appear to mock the DB layer | Medium — RLS policy correctness untested |
| No security tests | No tests for auth bypass, CSRF, webhook signature validation | Medium |
| No RAG search accuracy tests | Embedding + retrieval quality is unmeasured | Low |

---

## 8. Scalability Analysis

### At 100 Agents (Current Target)
**Status:** Should work fine
- DB connection pool (max 20 sync + 20 async = 40 connections) is adequate
- Trigger worker processes 50 per cycle at 60s interval = 3000/hour capacity
- Daily scanner processes sequentially but 100 agents should complete in minutes

### At 1,000 Agents
**Breaking points:**
1. **Trigger worker becomes bottleneck** — 50 triggers per cycle may not keep up. LIMIT 50 in `process_due_triggers()` means at most 3000 triggers/hour. If each agent has 5 pending triggers, 5000 total exceeds capacity.
2. **Daily scanner takes too long** — Sequential processing of 1000 agents with multiple DB queries each could take 30+ minutes. Agents in later timezones miss their briefing window.
3. **Console dashboard becomes slow** — `get_all_agents()` with 4 correlated subqueries x 1000 rows = 4000+ subqueries.
4. **Connection pool exhaustion** — 20 connections shared across 1000 agents' concurrent messages will bottleneck under peak load (e.g., morning briefing time when all agents are active).

**Fixes needed:**
- Increase pool sizes or add PgBouncer
- Parallelize daily scanner with asyncio.gather or worker pool
- Add pagination to all list endpoints
- Increase trigger worker batch size or run multiple workers (requires C-1 fix first)

### At 10,000 Agents
**Breaking points (in addition to above):**
1. **Single-process architecture won't scale** — Need horizontal scaling with proper task distribution
2. **RLS performance degrades** — `current_setting()` check on every row in large tables. Need to evaluate whether application-level filtering would be faster for hot paths.
3. **Embedding table becomes massive** — HNSW index rebuild time grows. Need to partition by `agent_id`.
4. **Anthropic API rate limits** — 10,000 agents generating concurrent LLM calls will hit rate limits. Need request queuing with backpressure.
5. **Twilio throughput** — Need multiple Twilio numbers/accounts with load balancing.

**Architectural changes needed:**
- Microservice decomposition (message pipeline, worker, console as separate services)
- Database sharding by agent_id or read replicas
- Redis-based task queue (Redis Streams or Celery)
- Embedding table partitioning
- LLM request queue with priority and rate limiting

---

## 9. Recommended Improvements — Prioritized

### P0 — Critical (Fix This Week)
| ID | Issue | Effort |
|----|-------|--------|
| C-1 | Add distributed locking to trigger worker | S |
| C-4 | Fix feedback UPDATE SQL (ORDER BY/LIMIT in UPDATE) | XS |
| S-3 | Validate SendGrid webhook signature | S |
| C-3 | Wrap sync pipeline in `asyncio.to_thread()` | S |

### P1 — Important (Fix This Month)
| ID | Issue | Effort |
|----|-------|--------|
| C-2 | Remove in-memory token tracking (rely on DB metrics) | XS |
| S-1 | Add per-user console authentication | M |
| S-7 | Add rate limiting to console login | S |
| P-1 | Fix N+1 queries in agent list | S |
| P-3 | Move summarization to background worker | M |
| B-6/B-7 | Fix monthly/annual recurrence with relativedelta | XS |
| A-1 | Introduce message queue for pipeline processing | L |
| A-4 | Set up Alembic migrations | M |

### P2 — Nice to Have (Backlog)
| ID | Issue | Effort |
|----|-------|--------|
| S-4 | Block Vapi webhook in production when secret not set | XS |
| S-5 | Add assertion-based allowlist to dynamic SQL builders | S |
| S-6 | Use proper HTML sanitization library | XS |
| P-2 | Optimize listing search with SQL ILIKE | S |
| P-4 | Add Redis caching for conversation history | M |
| P-5 | Use proper pgvector parameter binding | S |
| P-6 | Optimize daily scanner agent loading | XS |
| A-3 | Add Redis caching layer for agent config + listings | M |
| A-5 | Consolidate sync/async console queries | L |
| B-1 | Migrate to FastAPI Depends() injection | L |
| B-3 | Add TypedDict/Pydantic models to service returns | M |
| B-5 | Make model IDs configurable via env vars | XS |

---

## 10. Dependencies Audit

**File:** `requirements.txt`

| Package | Version | Status | Notes |
|---------|---------|--------|-------|
| fastapi | 0.115.6 | OK | Recent stable |
| uvicorn | 0.34.0 | OK | |
| pydantic | 2.10.6 | OK | |
| psycopg | 3.2.4 | OK | Modern async-capable driver |
| anthropic | 0.42.0 | OK | |
| twilio | 9.4.0 | OK | |
| redis | 5.2.1 | OK | |
| jinja2 | 3.1.5 | OK | |

**Missing recommended packages:**
- `bleach` or `nh3` — HTML sanitization (for S-6)
- `slowapi` — Rate limiting (for S-7)
- `sentry-sdk` — Error tracking (currently relying on structured logging only)
- `pytest-cov` — Test coverage reporting (no coverage config visible)

---

## 11. What's Done Well

Credit where due — these patterns are solid:

1. **RLS-based tenant isolation** — Every table has `agent_isolation` policies. This is defense-in-depth and correct.
2. **TCPA compliance** — Consent checking at multiple pipeline stages (gate, dispatcher) with immutable `consent_log` table.
3. **Model tiering** — Haiku for cheap/fast classification, Sonnet for reasoning. Cost tracking per agent/day.
4. **Conversation summarization** — Incremental + periodic full re-summarization to combat drift. Smart token budgeting in the assembler.
5. **Structured JSON logging** — Correlation IDs, structured fields, proper log levels.
6. **CSRF protection** — Double-submit cookie pattern on all mutating console endpoints.
7. **Production secret validation** — `validate_production_secrets()` refuses to start with default credentials.
8. **Prompt caching** — System prompts use `cache_control: ephemeral` for Anthropic prompt caching.
9. **Background task pattern** — Webhooks return 200 immediately, process in background.
10. **Schema design** — Clean normalization, appropriate indexes, `ON CONFLICT` upserts for idempotency.

---

*End of audit. Questions or clarifications: ping @eng.*
