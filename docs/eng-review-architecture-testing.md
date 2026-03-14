# Engineering Review: Architecture (A-1 to A-5) & Testing (T-1 to T-6)

**Reviewer:** Atlas (Engineering Lead)
**Date:** 2026-03-14
**Source:** `docs/technical-debt-backlog.md` (PRD-DEBT-001)

---

## Architecture Stories

---

### A-1: Message Queue for Pipeline Processing

**PM Story:** Inbound messages queued via Redis Streams before pipeline processing for durability and retry.
**PM Effort:** XL

**Engineering Specification:**

- **Files to modify:**
  - `app/api/webhooks.py` (lines 163-194, 315-331, 445-458): Replace `background_tasks.add_task(process_inbound_message, ...)` with Redis Stream `XADD` in all three webhook endpoints (Twilio inbound, Vapi post-call, email inbound).
  - `app/worker/run.py` (lines 1-53): Add a new consumer thread/loop that reads from `calloway:inbound` stream via `XREADGROUP`.
  - New file: `app/worker/message_consumer.py` — Stream consumer with consumer group, retry logic, DLQ.
  - `app/services/redis_pool.py` (lines 1-19): Current pool uses `redis.Redis` with sync client. Stream operations (`XADD`, `XREADGROUP`, `XACK`) are supported by existing `redis` 5.2.1 — no new deps needed.
  - `app/api/console.py`: Add DLQ count to dashboard (new query + template partial).
  - `app/services/console_queries.py`: Add `get_dead_letter_count()` function.

- **Implementation approach:**
  1. Webhook endpoints do `XADD calloway:inbound * type sms agent_id {id} payload {json}` and return 200 immediately (current behavior already returns 200 fast via `BackgroundTasks`, but messages are lost on restart).
  2. Consumer uses `XREADGROUP GROUP calloway-consumers worker-{hostname} COUNT 10 BLOCK 5000 STREAMS calloway:inbound >`.
  3. On success: `XACK`. On failure: increment attempt counter in message metadata. After 3 failures: `XADD calloway:dlq`.
  4. Idempotency: Dedup by `provider_message_id` (Twilio MessageSid / Vapi call_id). Check `messages` table before processing.
  5. Ordering: Use `XREADGROUP` with single consumer per stream — messages from same contact are naturally ordered. For multi-consumer, partition by `agent_id` hash.
  6. Fallback: If Redis `XADD` fails, fall back to current `BackgroundTasks` path with CRITICAL log.

- **Database changes:** None. DLQ is Redis-only. Console query for DLQ reads from Redis directly.

- **New dependencies:** None. `redis` 5.2.1 already supports Streams.

- **LOC estimate:** ~350 new, ~80 modified.

- **Risk notes:**
  - **A-2 dependency is backwards.** PM says A-1 depends on A-2. In reality, A-1 can be implemented independently — the consumer can run inside the existing worker process first, then split out with A-2. The dependency should be reversed: A-2 is easier after A-1 because the consumer is already a separate loop.
  - Message ordering across contacts is not guaranteed with multiple consumers. Single-consumer is fine at current scale (<100 agents).
  - `_process_inbound_message_sync` currently uses `asyncio.to_thread` wrapper (line 29). The consumer will call the sync function directly — simpler.
  - Redis Stream memory: Set `MAXLEN ~10000` on `XADD` to cap memory.

- **Revised effort:** XL is correct. This touches the critical path and requires careful rollout with fallback.

- **Additional acceptance criteria:**
  - Consumer must log `correlation_id` for cross-process tracing.
  - `MAXLEN` must be set on streams to prevent unbounded memory growth.
  - Metrics: Add `stream_depth` gauge to health endpoint.

---

### A-2: Separate Worker Process from Web Server

**PM Story:** Background workers run as separate container/process from web server.
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - `Dockerfile` (lines 1-38): Currently single CMD. Add a build arg or entrypoint script that branches on `PROCESS_TYPE`.
  - `docker-compose.yml` (lines 1-66): Add `worker` service using same image but different command.
  - `Procfile` (line 2): Already has `worker: python -m app.worker.run` — Railway already supports this. Just needs a second Railway service.
  - `app/worker/run.py` (lines 1-53): Currently runs trigger loop and daily scan in threads. This file is already the worker entrypoint — no structural changes needed.
  - `app/main.py` (lines 41-51): Lifespan currently only initializes DB pools. Web process should NOT start the trigger/daily scan threads. Currently it doesn't — workers are started separately via `python -m app.worker.run`. Verify no implicit worker startup in web process.
  - `app/db/connection.py` (lines 36-52, 83-99): Pool sizes need to be configurable per process type. Web process needs larger async pool, worker needs larger sync pool.

- **Implementation approach:**
  1. Add `PROCESS_TYPE` env var (default `web`). In `Dockerfile`, use entrypoint script: `if PROCESS_TYPE=worker then python -m app.worker.run else uvicorn ...`.
  2. `docker-compose.yml`: Add `worker` service with same build context, `command: python -m app.worker.run`, and `PROCESS_TYPE=worker`.
  3. Connection pool tuning: Web gets `sync_max=5, async_max=20`. Worker gets `sync_max=15, async_max=5`. Read from env vars `DB_SYNC_POOL_MAX` and `DB_ASYNC_POOL_MAX`.
  4. Health check for worker: Add a simple HTTP health endpoint on a different port (e.g., 8001) or use a file-based liveness probe (`touch /tmp/worker-alive` each loop iteration).
  5. Graceful shutdown: Worker already runs trigger loop with `time.sleep(60)` (line 31 of trigger_worker.py). Add signal handler for SIGTERM that sets a `_shutdown` flag and breaks the loop after current trigger finishes.

- **Database changes:** None.

- **New dependencies:** None.

- **LOC estimate:** ~100 new, ~40 modified.

- **Risk notes:**
  - The Procfile already separates web and worker. Railway supports multi-process via Procfile natively. The actual work is mostly Docker + compose + pool tuning + graceful shutdown.
  - `app/services/redis_pool.py` creates a module-level singleton. Both processes will get their own pool — no shared state issue.
  - `app/services/agent_config.py` has its own Redis client (line 11-20, separate from `redis_pool.py`). Both caches work independently — no cross-process concern.

- **Revised effort:** M. The Procfile already exists with the right commands. Docker-compose needs one new service block. Pool tuning is a few env vars. Graceful shutdown is ~20 lines. PM overestimated at L.

- **Additional acceptance criteria:**
  - Worker must handle SIGTERM gracefully (finish current trigger, then exit).
  - Worker health check must be monitorable by Railway/Docker.
  - Connection pool sizes must be configurable via env vars, not hardcoded.

---

### A-3: Redis Caching Layer for Hot Data

**PM Story:** Cache agent config, active listings, and conversation history in Redis with TTLs.
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - `app/services/agent_config.py` (lines 28-80): Already caches agent lookups in Redis with 5-min TTL (lines 31-46). This is partially done.
  - `app/services/redis_pool.py` (lines 1-19): Current pool is sync-only. Need an async Redis client for use in FastAPI handlers. Add `get_async_redis_pool()`.
  - New file: `app/services/cache.py` — Generic cache layer with `get/set/invalidate` + TTL management + fallback-on-failure.
  - `app/pipeline/assembler.py` (lines 130-146): Cache conversation history at `conv:{agent_id}:{contact_id}` with 60s TTL.
  - `app/pipeline/assembler.py` (lines 149-158): `_find_referenced_listing()` currently loads ALL active listings into memory (line 152). Cache active listings at `listings:{agent_id}` with 5-min TTL.
  - `app/pipeline/dispatcher.py` (lines 168-231): After `_log_conversation`, invalidate conversation cache for that contact.
  - `app/api/console.py`: After agent config updates, invalidate agent cache keys.
  - `app/services/console_queries.py` (lines 890-931): `update_agent_tenant()` must invalidate `agent:id:{id}` and `agent:twilio:{number}`.

- **Implementation approach:**
  1. Create `app/services/cache.py` with: `cache_get(key) -> bytes|None`, `cache_set(key, value, ttl)`, `cache_invalidate(key)`, `cache_invalidate_pattern(pattern)`. All operations wrapped in try/except that returns None/logs WARNING on Redis failure.
  2. Agent config caching is already done in `agent_config.py`. Just need to add invalidation hooks in console update paths.
  3. Conversation history: In `_load_conversation_history`, check cache first. On miss, query DB and populate cache. In `_log_conversation` (dispatcher.py line 229), call `cache_invalidate(f"conv:{agent_id}:{contact_id}")`.
  4. Listings: In `_find_referenced_listing` and `_load_relevant_listings`, use `cache_get(f"listings:{agent_id}")`. On miss, query and cache. Invalidate on listing create/update in console.

- **Database changes:** None.

- **New dependencies:** None. `redis` 5.2.1 already installed.

- **LOC estimate:** ~200 new (cache.py + integration), ~60 modified.

- **Risk notes:**
  - Agent config caching already exists — risk of double-caching or inconsistent invalidation if not consolidated into the new cache layer.
  - Stale conversation cache could cause the AI to miss the latest message. 60s TTL is aggressive — consider 30s or invalidate-on-write only.
  - `_find_referenced_listing` loads all listings per message (line 152 of assembler.py). Caching helps, but this is really a P-2 fix (bounded listing search). The cache masks the underlying O(n) problem.

- **Revised effort:** M. Agent config caching already exists. The remaining work is conversation and listing caches + invalidation hooks. Not L.

- **Additional acceptance criteria:**
  - Consolidate existing `agent_config.py` caching into the new cache layer (or at minimum, share the same Redis client).
  - Cache keys must be namespaced: `calloway:{type}:{id}` to avoid collisions with other Redis users.
  - Add cache hit/miss counters to health endpoint.

---

### A-4: Database Migration Tooling (Alembic)

**PM Story:** Schema changes managed through Alembic migration files with versioning and rollback.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - `requirements.txt` (line 7): `alembic==1.14.1` is already present. No new dep needed.
  - New file: `alembic.ini` — Alembic configuration pointing to `app/db/connection.py` for connection string.
  - New directory: `alembic/` with `env.py`, `script.py.mako`, `versions/`.
  - `alembic/env.py`: Configure to use `get_connection_string()` from `app/db/connection.py`.
  - `app/db/schema.sql` (522 lines): Remains as reference. Baseline migration will be generated from it.
  - `Dockerfile` (line 38): Add `alembic upgrade head` to startup command (before uvicorn).
  - `docker-compose.yml`: Add migration step or init command.

- **Implementation approach:**
  1. `alembic init alembic` to scaffold.
  2. Edit `alembic/env.py` to import `get_connection_string()` and set `sqlalchemy.url` dynamically (Alembic uses SQLAlchemy under the hood, but we use psycopg3 directly — configure raw connection mode).
  3. **Baseline migration:** Create initial migration that is a no-op on existing databases. Use `alembic stamp head` on production to mark current schema as "at head" without running anything.
  4. RLS policies: Alembic autogenerate won't detect RLS policies or custom indexes. These must be manually included in migration `upgrade()` functions. Add a comment convention: `# RLS: table_name` for each policy.
  5. Advisory lock: Enable `alembic.ini` setting `[alembic] lock = True` (or use `--x lock=true` in the migration command) to prevent concurrent migrations.
  6. Pre-start script: `scripts/migrate.sh` that runs `alembic upgrade head` before the app starts. Reference in Dockerfile CMD.

- **Database changes:** Alembic creates `alembic_version` table automatically.

- **New dependencies:** None. `alembic==1.14.1` already in requirements.txt.

- **LOC estimate:** ~150 new (alembic config + env.py + baseline migration + startup script), ~10 modified.

- **Risk notes:**
  - Alembic uses SQLAlchemy metadata for autogenerate. We don't have SQLAlchemy models — autogenerate will produce empty diffs. Options: (a) write migrations manually (recommended for now), (b) create SQLAlchemy model layer later.
  - The schema includes 15 tables, 20+ indexes, 13 RLS policies. The baseline migration needs to be comprehensive but must be a no-op on existing DBs. Use `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` pattern, or simply `stamp head`.
  - pgvector extension (`CREATE EXTENSION IF NOT EXISTS vector`) must be in the baseline migration.

- **Revised effort:** M is correct. The scaffolding is straightforward, but the baseline migration capturing all RLS policies requires care.

- **Additional acceptance criteria:**
  - All RLS policies must be tracked in migrations (not just tables and indexes).
  - `alembic downgrade -1` must work for any migration (every `upgrade` needs a corresponding `downgrade`).
  - CI must run `alembic check` to verify no pending migrations against the schema.

---

### A-5: Consolidate Sync/Async Console Query Paths

**PM Story:** Eliminate ~700 lines of duplicated sync/async code in console_queries.py.
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - `app/services/console_queries.py` (1917 lines): The file has ~30 sync functions (lines 20-982) and ~25 async mirrors (lines 990-1917). Every async function is a copy-paste of the sync version with `await` added. The async versions are used by console routes; sync versions by workers and tests.
  - `app/api/console.py`: All console routes currently call `async_*` variants. After consolidation, they call the single async function directly.
  - `app/worker/run.py` (line 19): Daily scanner imports `_get_all_active_agents` which is sync. Worker callers need wrapping.
  - `app/services/console_queries.py` lines 933-982: `send_test_sms()` and `run_manual_scan()` are sync-only (no async mirror). These stay sync or get async versions.
  - `tests/test_console.py`: Tests mock both sync and async variants. After consolidation, simplify mocks.

- **Implementation approach:**
  1. Keep only the async versions. Rename `async_get_system_pulse` to `get_system_pulse`, etc.
  2. For the ~5 sync-only functions (`create_agent_tenant`, `update_agent_tenant`, `create_agent_from_wizard`, `send_test_sms`, `run_manual_scan`, `deactivate_agent`), convert to async.
  3. For worker callers that need sync: Create a thin sync wrapper `def sync_get_all_agents(): return asyncio.run(get_all_agents())` — but only for the 1-2 functions the worker actually uses. Better: make the worker async (it already runs in its own process).
  4. Update all import sites. Console routes already use `async_*` — just rename.
  5. Drop all sync functions that have async mirrors (lines 20-982 minus the ~6 sync-only functions).

- **Database changes:** None.

- **New dependencies:** None.

- **LOC estimate:** ~900 lines deleted, ~100 lines modified (renames, import updates), ~20 new (sync wrappers for worker).

- **Risk notes:**
  - The worker (`app/worker/run.py`, `daily_scanner.py`, `trigger_worker.py`) runs synchronously with `time.sleep()` loops. It imports sync DB functions. If we convert console_queries to async-only, the worker can't call them directly. Options: (a) make worker async (significant refactor — scope creep), (b) provide sync wrappers using `asyncio.run()` for the 2-3 functions the worker needs, (c) keep a small sync path for worker-specific queries only.
  - Option (b) is cleanest: worker only uses `_get_all_active_agents()` (daily_scanner.py line 15) which is defined in `daily_scanner.py` itself, not in console_queries. Verify no other worker imports from console_queries.
  - `log_error()` (line 444) is called from various places including potentially sync contexts. Needs a sync wrapper.
  - Test impact: `test_console.py` mocks `async_*` variants extensively (20+ patches). All mock targets change.

- **Revised effort:** L is correct. The deletion is straightforward but the import audit and test updates are tedious.

- **Additional acceptance criteria:**
  - Zero sync functions remain that have an async equivalent (except explicit sync wrappers for worker use).
  - `grep -c "def get_\|def async_get_" console_queries.py` shows roughly half the current count.
  - All console routes must use the async pool (no sync `get_db_connection()` calls from FastAPI handlers via console_queries).

---

## Testing Stories

---

### T-1: Console Queries Test Suite

**PM Story:** Comprehensive tests for console_queries.py (~30 public functions, 1400+ LOC).
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - `tests/test_console.py` (528 lines): Already has 20+ tests covering console routes and a few query functions (lines 177-218 test imports and basic mock patterns). Extend this or create a new dedicated file.
  - New file: `tests/test_console_queries.py` — Dedicated unit tests for the query layer, separate from route-level tests.

- **Implementation approach:**
  1. Audit public functions. Current sync public functions (from grep): `get_system_pulse`, `get_recent_activity`, `get_agents_needing_attention`, `get_all_agents`, `get_agent_detail`, `get_recent_conversations`, `get_conversation_detail`, `get_trigger_queue`, `retry_trigger`, `cancel_trigger`, `fire_trigger_now`, `get_recent_errors`, `log_error`, `get_cost_summary`, `get_cost_by_agent`, `get_model_tier_breakdown`, `get_health_overview`, `get_health_status_color`, `create_agent_from_wizard`, `create_agent_tenant`, `update_agent_tenant`, `deactivate_agent`, `send_test_sms`, `run_manual_scan`. That's 24 sync functions.
  2. For each function, test: (a) happy path with mocked DB returning expected rows, (b) empty/None results, (c) DB exception returns safe default (each function has try/except returning empty list/dict).
  3. For functions with parameters that change SQL (`get_recent_conversations` with `agent_id`, `channel`, `search`), test each filter branch.
  4. For write functions (`retry_trigger`, `cancel_trigger`, `fire_trigger_now`, `log_error`, `create_agent_tenant`, `update_agent_tenant`, `deactivate_agent`), verify correct SQL is executed via mock assertions.
  5. Test `create_agent_tenant` validation: missing required fields, duplicate Twilio number (already partially tested in test_console.py lines 455-476).

- **Database changes:** None.

- **New dependencies:** None.

- **LOC estimate:** ~600 new.

- **Risk notes:**
  - The existing `test_console.py` already tests some query functions (lines 190-218). Need to avoid duplication — either move those tests to the new file or leave them and only add new coverage.
  - All functions use `get_db_connection()` context manager. The mock pattern is established (lines 200-218 of test_console.py). Reuse it.
  - Some functions return complex nested dicts (`get_agent_detail` returns agent + contacts + listings + messages + triggers + costs). Tests need to mock multiple `execute().fetchone()`/`fetchall()` calls in sequence — mock setup is verbose.

- **Revised effort:** L is correct. 24 functions with 2-3 tests each = 50-70 tests. Verbose mock setup adds LOC.

- **Additional acceptance criteria:**
  - Each function's error-handling path (the except block returning defaults) must have at least one test.
  - Test file must be runnable independently: `pytest tests/test_console_queries.py -v` completes in <30s.

---

### T-2: Dispatcher Test Suite

**PM Story:** Tests for dispatcher consent gate, conversation logging, and usage tracking.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - New file: `tests/test_dispatcher.py` — Dedicated test suite for `app/pipeline/dispatcher.py`.

- **Implementation approach:**
  1. Test `dispatch()` main function (line 22-108):
     - Consent gate: mock contact with `consent_status='revoked'`, verify `_log_conversation` is called but `send_client_message`/`send_sms` is NOT called.
     - Consent gate: mock contact with `consent_status='granted'`, verify message IS sent.
     - Consent gate: `contact=None` (new contact), verify no consent check.
     - `is_agent_command=True` bypasses consent gate (line 33).
  2. Test `_log_conversation` (line 168-231):
     - Existing conversation: verify `UPDATE conversations SET last_message_at` is called.
     - New conversation: verify `INSERT INTO conversations` is called.
     - Response text present: verify two INSERT INTO messages (inbound + outbound).
     - No response text: verify only one INSERT INTO messages (inbound only).
     - Contact `last_contact_at` update.
  3. Test `_update_usage_metrics` (line 234-266):
     - Model cost calculation for haiku, sonnet, template.
     - UPSERT pattern (INSERT ... ON CONFLICT DO UPDATE).
  4. Test `_maybe_summarize_conversation` (line 300-322):
     - Called for client messages (`contact` present, not `is_agent_command`).
     - NOT called for agent commands.
     - Failure is non-fatal (exception caught, warning logged).
  5. Test `_maybe_append_feedback_prompt` (line 272-297):
     - Appends feedback prompt every 10th interaction.
     - Does not append on non-10th interactions.
  6. Test channel routing: SMS, email, agent command — verify correct send function called (lines 57-83).

- **Database changes:** None.

- **New dependencies:** None.

- **LOC estimate:** ~500 new.

- **Risk notes:**
  - `dispatch()` has many side effects (send SMS, send email, send push notification, create trigger, log conversation, update metrics, summarize). Each needs careful mocking.
  - `_maybe_summarize_conversation` runs synchronously in the hot path (line 300-322, comments at 300-306 say "This runs synchronously after dispatch"). This is the bug that P-3 fixes. Tests should document this behavior.
  - `MODEL_COST_MAP` (line 15-19) has hardcoded rates. Tests should verify cost calculation math.

- **Revised effort:** M is correct. Many code paths but straightforward mock-based testing.

- **Additional acceptance criteria:**
  - Edge case: `decision.response_text` is empty string vs None — both should skip sending.
  - Edge case: `contact.consent_status` is NULL (not 'granted' or 'revoked') — verify behavior matches `check_consent_before_send()`.
  - Test that `provider_message_id` from Twilio send is stored in messages table.

---

### T-3: Integration Tests with Real DB (RLS Verification)

**PM Story:** Integration tests verifying PostgreSQL RLS policies with real database connections.
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - New file: `tests/test_rls_integration.py` — Integration tests requiring a running PostgreSQL instance.
  - `tests/conftest.py` (9 lines): Add fixtures for test database setup/teardown, agent context switching.
  - `docker-compose.yml` (or new `docker-compose.test.yml`): Test database service.
  - `app/db/schema.sql`: Used as-is to set up test database.

- **Implementation approach:**
  1. Test fixture: Create a test database by running `schema.sql`. Insert two agents (A, B) with contacts, messages, listings, triggers.
  2. RLS tests:
     - Set context to Agent A (`set_agent_context(conn, agent_a_id)`), query contacts — only A's contacts returned.
     - Set context to Agent A, query Agent B's messages — zero rows (not error).
     - Set context to Agent A, attempt INSERT with `agent_id=B` — blocked by RLS.
     - Service-role connection (no `set_agent_context`) — returns all rows (console query behavior).
  3. RLS coverage: Test all 13 tables with RLS policies: contacts, lead_preferences, listings, conversations, messages, showings, triggers, transactions, drip_campaigns, drip_enrollments, emails, tool_executions, embeddings, usage_metrics, consent_log, conversation_summaries, device_tokens.
  4. Cross-table JOIN test: Query messages with JOIN to conversations — RLS on both tables filters correctly.
  5. Schema completeness test: Query `pg_catalog.pg_policies` and compare against expected list — flag any table missing a policy.

- **Database changes:** None (test-only).

- **New dependencies:** None. `psycopg` already in requirements.

- **LOC estimate:** ~400 new.

- **Risk notes:**
  - These tests require a running PostgreSQL with pgvector. CI must have a Postgres service. Docker-compose already provides one.
  - Test isolation: Each test should use a transaction that is rolled back, or use unique agent IDs. Transaction rollback is cleaner.
  - The `set_agent_context` function (connection.py line 151) uses `set_config('app.current_agent_id', ..., true)` — the `true` means it's transaction-local. This is good for test isolation.
  - `lead_preferences` RLS uses a subquery joining to `contacts` (schema.sql lines 400-407). This is slower and more complex — needs specific testing.
  - Tables without `agent_id` column: `lead_preferences` (uses contact_id FK), `alembic_version` (no RLS needed). Verify the schema completeness check accounts for these.

- **Revised effort:** L is correct. Many tables to cover, test DB setup is involved, and CI integration needs work.

- **Additional acceptance criteria:**
  - Test must programmatically verify all tables with `agent_id` column have RLS enabled — no manual list.
  - Tests must run in CI with `docker-compose up postgres` (or equivalent GitHub Actions service).
  - Mark with `@pytest.mark.integration` so unit test runs can skip them.

---

### T-4: Security Test Suite

**PM Story:** Automated tests for auth bypass, CSRF, and webhook signature validation.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - New file: `tests/test_security.py` — Security-focused test suite.
  - Existing `tests/test_console.py` (lines 20-78): Already tests auth redirects for 7 console pages and login flow. New tests supplement, don't duplicate.
  - Existing `tests/test_webhooks.py`: Check what's already covered.

- **Implementation approach:**
  1. Console auth bypass:
     - All `/console/*` routes without session → 303 redirect to login (partially covered in test_console.py line 63-78, but only 7 routes — need to cover all routes including POST endpoints).
     - Forged/expired session cookie → redirect to login.
     - Session cookie from a different signing secret → rejected.
  2. CSRF:
     - POST to `/console/tenants/new` without CSRF token → 403. (Need to verify CSRF is actually implemented first — check console.py).
     - POST with invalid CSRF token → 403.
  3. Webhook signature tests:
     - Twilio: Already validated (webhooks.py line 14-20). Test with invalid signature → 403 (line 174).
     - Vapi: Test without `x-vapi-secret` header when `VAPI_WEBHOOK_SECRET` is set → 401 (line 322-323).
     - Vapi: Test with valid secret → 200.
     - SendGrid: Depends on S-3 being implemented. Test stub with `SENDGRID_INBOUND_SECRET` configured → 401 on invalid signature. (Currently no signature validation exists for email — line 446-458 has no check.)
  4. HTTP method tests:
     - GET to webhook POST endpoints → 405.
     - DELETE to console read endpoints → 405.

- **Database changes:** None.

- **New dependencies:** None.

- **LOC estimate:** ~300 new.

- **Risk notes:**
  - CSRF protection may not be implemented yet. Check `app/api/console.py` for CSRF middleware or token validation. If not implemented, T-4 tests will fail — this creates a dependency on a new story (or T-4 must include CSRF implementation).
  - S-3 (SendGrid webhook signature verification) is listed as a dependency. If S-3 isn't done, SendGrid signature tests should be written as `@pytest.mark.skip(reason="Requires S-3")` and shipped anyway.
  - The existing Twilio signature validation skips in development mode (webhooks.py line 17-18). Security tests must set `ENVIRONMENT=production` or mock the settings.

- **Revised effort:** M is correct, assuming CSRF already exists. If CSRF needs to be added, this becomes L.

- **Additional acceptance criteria:**
  - Tests must run with `ENVIRONMENT=production` mocked to catch dev-mode bypasses.
  - Rate limiting on login (S-7) should be tested here if S-7 is done.
  - Verify no console route returns 500 on auth failure (must be 303 or 403, never a stack trace).

---

### T-5: RAG Search Accuracy Tests

**PM Story:** Test suite measuring RAG search result quality against known-good queries.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - New file: `tests/test_rag_accuracy.py` — Accuracy benchmark suite.
  - Existing `tests/test_rag.py` (368 lines): Already has unit tests for chunking, embedding, RAG service, and pipeline integration. New tests are complementary — they test quality, not correctness.
  - New file: `tests/fixtures/rag_test_corpus.json` — Curated test documents + expected query-result pairs.

- **Implementation approach:**
  1. Test corpus: 20+ documents representing real data types: listings (address, price, features, HOA), contacts (preferences, notes), conversations (Q&A threads). Store as JSON fixtures.
  2. Embed the corpus once per test session (session-scoped fixture). Use the real embedding service with Voyage API (or mock with deterministic embeddings for CI).
  3. Query-result pairs: For each query, define expected top-1 and top-3 results. Example: `"What are the HOA fees for 123 Oak St?"` → top-1 should be the listing chunk containing 123 Oak St.
  4. Accuracy metric: `relevant_in_top_3 / total_queries >= 0.80`.
  5. Regression reporting: Output a markdown table with query, expected result, actual top-3, and pass/fail.
  6. Run modes: (a) With real Voyage API (slow, ~$0.01, needs API key — CI only), (b) With mock embeddings (fast, deterministic — local dev).

- **Database changes:** None (uses in-memory or test DB).

- **New dependencies:** None.

- **LOC estimate:** ~350 new (test code + corpus fixture).

- **Risk notes:**
  - Real embedding tests require `VOYAGE_API_KEY`. CI needs this as a secret. If not available, tests must gracefully skip.
  - Embedding model changes (e.g., voyage-3-lite → voyage-3) will change accuracy scores. Tests should report deltas, not hard-fail on slight drops.
  - The current RAG search passes `str(query_embedding)` (rag_service.py line 279, 298, 311) — this is the string representation issue that P-5 addresses. Accuracy tests may expose this inefficiency but won't fix it.
  - Test corpus must be representative but not so large that embedding costs are significant ($0.01-0.05 per run is acceptable).

- **Revised effort:** M is correct. Corpus creation is the main effort. Test code is straightforward.

- **Additional acceptance criteria:**
  - Test suite must work in two modes: real embeddings (CI) and mock embeddings (local).
  - Accuracy report must be printed to stdout, not just pass/fail assertions.
  - Add `@pytest.mark.slow` marker for test runs with real embeddings.

---

### T-6: Load/Stress Test Harness

**PM Story:** Load test simulating concurrent agent/client message traffic to find breaking points.
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - New file: `tests/load/locustfile.py` — Locust load test definitions.
  - New file: `tests/load/README.md` — Instructions for running load tests. (Only if explicitly requested.)
  - `Makefile` or `scripts/load-test.sh`: `make load-test` command.
  - `requirements-dev.txt` (2 lines): Add `locust`.

- **Implementation approach:**
  1. Use Locust (Python-native, fits our stack). Define user classes:
     - `InboundSMSUser`: POST to `/webhooks/twilio/inbound` with realistic Twilio payload.
     - `ConsoleUser`: GET `/console/dashboard`, `/console/tenants`, `/console/conversations` with auth cookie.
     - `VapiUser`: POST to `/webhooks/vapi/post-call` with call transcript payload.
  2. Safety: Mock outbound Twilio/SendGrid calls. Options:
     - Set `TWILIO_AUTH_TOKEN=""` so Twilio SDK calls fail (existing code catches and logs).
     - Better: Use environment variable `DRY_RUN_MODE=true` that skips actual SMS sends. This needs a code change in `twilio_service.py`.
     - Simplest: Point at staging with a Twilio test credential (test cred SID starts with `AC_test`).
  3. Metrics: Locust provides p50/p95/p99 response times, error rates, RPS out of the box.
  4. DB connection pool monitoring: Add a `/health/detailed` endpoint that reports `_pool.get_stats()` (psycopg_pool supports this).
  5. Target: Simulate 100 concurrent agents, 1-100 msg/sec configurable via Locust UI or CLI `--users 100 --spawn-rate 10`.

- **Database changes:** None.

- **New dependencies:** `locust` (add to `requirements-dev.txt`).

- **LOC estimate:** ~250 new.

- **Risk notes:**
  - Twilio signature validation will reject load test requests unless we either (a) disable validation in test, (b) generate valid signatures, or (c) use a test mode bypass. Option (c) with `ENVIRONMENT=development` is simplest (webhooks.py line 17 already skips validation in dev).
  - Database seeding: Load tests need pre-existing agents, contacts, and conversations. Need a seed script or use existing test harness data.
  - Railway staging may have rate limits or cost implications. Load tests should target local docker-compose only.
  - Memory leak detection: Locust can run for extended periods. Pair with `psutil` RSS monitoring or Railway's built-in metrics.

- **Revised effort:** L is correct. Locust setup is quick, but realistic payloads, safety mechanisms, and seeding add work.

- **Additional acceptance criteria:**
  - `make load-test` must work against `docker-compose up` with zero manual setup beyond `docker-compose up`.
  - Load test must NOT send real SMS/emails under any configuration.
  - Results must include DB connection pool utilization (not just HTTP metrics).
  - Seed script must be idempotent (safe to run multiple times).

---

## Engineering Notes

### Stories Where I Disagree with Priority/Effort

1. **A-2 effort is overestimated.** PM says L, I say M. The Procfile already exists with `web` and `worker` commands. Railway supports this natively. The actual new work is Docker-compose worker service, pool tuning env vars, and graceful shutdown signal handling.

2. **A-3 effort is overestimated.** PM says L, I say M. Agent config caching already exists in `agent_config.py`. The remaining work is conversation + listing caches and invalidation hooks.

3. **A-1 dependency is reversed.** PM says A-1 depends on A-2. In reality, A-1 (message queue) can be implemented first with the consumer running inside the existing worker process. A-2 (process separation) is then just deployment config. Reverse the dependency.

### Stories to Combine or Split

- **A-3 and P-4** (Redis caching layer + Cached conversation history) overlap significantly. P-4 is a subset of A-3. Implement A-3 first, and P-4's conversation caching comes along with it. Mark P-4 as "absorbed into A-3."

- **T-4 has a hidden dependency on CSRF.** The console may not have CSRF protection implemented. If not, either: (a) add a new story S-8 for CSRF implementation, or (b) expand T-4 to include CSRF implementation (which changes it from M to L effort).

### Implementation Order Recommendation

```
Phase 1 (Foundation, no dependencies):
  A-4  Database migration tooling (Alembic)     — M, enables all schema changes
  T-1  Console queries test suite                — L, safety net before A-5 refactor
  T-2  Dispatcher test suite                     — M, safety net for pipeline changes

Phase 2 (Parallel tracks):
  Track A: A-5  Consolidate sync/async queries   — L, needs T-1 done first
  Track B: A-2  Separate worker process           — M, standalone
  Track B: A-3  Redis caching layer (absorbs P-4) — M, standalone

Phase 3 (Depends on Phase 2):
  A-1  Message queue                             — XL, needs A-2 worker separation ideally
  T-3  Integration tests (RLS)                   — L, needs test DB infrastructure

Phase 4 (Independent, lower priority):
  T-4  Security test suite                       — M, depends on S-3/S-4
  T-5  RAG accuracy tests                        — M, standalone
  T-6  Load test harness                         — L, standalone
```

**Rationale:** A-4 (Alembic) and test suites (T-1, T-2) are zero-risk enablers that should go first. A-5 is a large refactor that needs T-1's safety net. A-1 is the riskiest story (touches the critical message path) and should go last with full test coverage in place.

**Total estimated LOC:** ~4,100 new/modified across all 11 stories.
