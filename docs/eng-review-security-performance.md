# Engineering Review — Security (S-1–S-7) & Performance (P-1–P-6)

**Reviewer:** Atlas (Engineering Lead)
**Date:** 2026-03-14
**Status:** Review Complete

---

### S-1: Per-User Console Authentication with Audit Trail

**PM Story:** Replace shared `CONSOLE_PASSWORD` with per-user email/password auth, add audit logging for all write actions.
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - `app/api/console_auth.py` (lines 1–92) — gut and replace. Currently a single-password scheme with `verify_password()` doing `hmac.compare_digest(password, settings.CONSOLE_PASSWORD)` (line 32). Needs full user model, bcrypt hashing, session-with-user-id.
  - `app/api/console.py` — `login_submit()` (line 60–68) needs email+password form fields. `_require_auth()` (line 37–41) must return user object, not bool. Every `@router.post` handler that mutates state needs audit logging (~15 endpoints).
  - `app/config.py` (line 56–57) — preserve `CONSOLE_PASSWORD` for legacy mode. Add `LEGACY_AUTH_MODE` env var.
  - `app/db/schema.sql` — new `console_users` table (id, email, password_hash, role, active, created_at, updated_at). New `audit_log` table (id, user_id, action, target_entity_id, target_entity_type, ip_address, details_jsonb, created_at).
  - `app/templates/console/login.html` — add email field.
- **Implementation approach:**
  1. Add Alembic migration for `console_users` and `audit_log` tables (depends on A-4 being done, or ship raw SQL migration).
  2. Rewrite `console_auth.py`: bcrypt password hashing via `passlib[bcrypt]`, session token now contains `{user_id, role, ts}`, `check_session()` returns user dict or None.
  3. Add `_require_auth_user()` that returns `(user, redirect)` tuple — every route uses this instead of `_require_auth()`.
  4. Add `log_audit(user_id, action, target_id, ip, details)` utility that writes to `audit_log`.
  5. Wire audit logging into all POST handlers in `console.py`.
  6. Add role-based guard: if `user.role == "viewer"`, reject POST/PUT/DELETE with 403.
  7. Support `LEGACY_AUTH_MODE=true` flag: if set and no `console_users` rows exist, fall back to single-password auth (current behavior). Log deprecation warning on every login.
- **Database changes:** Two new tables (`console_users`, `audit_log`). Migration required.
- **New dependencies:** `passlib[bcrypt]` (or `bcrypt` directly).
- **LOC estimate:** ~350 changed/added.
- **Risk notes:**
  - A-4 (Alembic) is listed as a dependency, but Alembic is already in `requirements.txt` (line 7). The real blocker is whether Alembic is actually configured with an `alembic.ini` and `env.py`. Need to check. If not, the first migration can be a raw `.sql` file run manually.
  - Session invalidation on user deactivation requires either short session TTL or a revocation list (Redis set of revoked session IDs). Recommend short TTL (1h) + refresh-on-activity pattern.
  - The transition period with `LEGACY_AUTH_MODE` is the riskiest part — two auth paths means double the testing surface.
- **Revised effort:** L — agree with PM. This is a solid week of work including migration, auth rewrite, audit wiring, and testing.
- **Additional acceptance criteria:**
  - Passwords must be stored as bcrypt hashes, never plaintext.
  - Audit log must be append-only (no UPDATE/DELETE permissions for the app user on that table).
  - Session token must include user_id so audit logging can identify the operator.

---

### S-2: Authorization Guard on Console Query Layer

**PM Story:** Console query functions should reject calls from unauthenticated contexts.
**PM Effort:** S

**Engineering Specification:**

- **Files to modify:**
  - `app/services/console_queries.py` (1917 lines) — every public function (e.g., `get_all_agents()` line 123, `get_system_pulse()` line 20, `get_agent_detail()` line 144, and their `async_*` counterparts starting at line 1095). There are ~30 public functions.
  - `app/api/console.py` — all call sites need to pass the auth context token.
- **Implementation approach:**
  1. Add a thread-local/context-var `_console_auth_context` at the top of `console_queries.py`.
  2. Create a `set_console_auth(verified: bool)` function and a decorator `@require_console_auth` that checks it.
  3. In `console.py`, after `_require_auth()` succeeds, set the context var before calling any query function.
  4. Apply `@require_console_auth` to every public function in `console_queries.py`.
  5. For internal callers (daily_scanner, background workers), provide a `with internal_console_context():` context manager that sets an `internal=True` flag.
  - **Alternative (simpler):** Use a FastAPI `Depends()` pattern — pass a sentinel object (`ConsoleSession`) as the first arg to every query function. Callers without the session simply cannot call the function with the right type. This is more Pythonic but requires changing every call signature.
  - **Recommendation:** Context-var approach is less invasive for 30 functions.
- **Database changes:** None.
- **New dependencies:** None. Uses stdlib `contextvars`.
- **LOC estimate:** ~80 (decorator + context var setup + applying to ~30 functions).
- **Risk notes:**
  - The sync/async duplication means applying the guard to both versions. ~60 public functions total.
  - Must verify daily_scanner doesn't use any console query functions (it uses its own `_get_all_active_agents()` at line 377 of `daily_scanner.py` — it does NOT use console_queries, so no conflict).
- **Revised effort:** S — agree. Mechanical but low-risk.
- **Additional acceptance criteria:**
  - Guard must raise a specific `AuthorizationError` (not a generic Exception) so callers can distinguish auth failures from query failures.
  - Error messages must not include table names, column names, or query text.

---

### S-3: SendGrid Inbound Webhook Signature Verification

**PM Story:** Verify SendGrid signatures on the email inbound webhook to prevent forged emails.
**PM Effort:** S

**Engineering Specification:**

- **Files to modify:**
  - `app/api/webhooks.py` — `email_inbound()` at line 445–458. Currently accepts all POSTs with zero signature validation.
  - `app/config.py` — `SENDGRID_INBOUND_SECRET` already exists (line 43). No changes needed.
- **Implementation approach:**
  1. SendGrid Inbound Parse uses the [Event Webhook verification](https://docs.sendgrid.com/for-developers/tracking-events/getting-started-event-webhook-security-features) with an ECDSA signature. The `sendgrid` package (already in requirements, v6.11.0) includes `EventWebhookHeader` and `EventWebhook` classes for verification.
  2. However, Inbound Parse webhooks (which this is — it's a form-data POST of the email) do NOT use the same ECDSA signature as event webhooks. SendGrid Inbound Parse has a "basic auth" or "OAuth" option but no built-in HMAC signature verification like Twilio.
  3. **Realistic approach:** Use HTTP Basic Auth on the webhook URL configured in SendGrid (e.g., `https://user:secret@api.calloway.ai/webhooks/email/inbound`). Verify the `Authorization` header against `SENDGRID_INBOUND_SECRET`.
  4. Add a `validate_sendgrid_inbound()` function similar to the existing `validate_twilio_signature()` (line 14–20).
  5. In production without secret: return 503 with CRITICAL log. In development without secret: skip validation with DEBUG log.
- **Database changes:** None.
- **New dependencies:** None.
- **LOC estimate:** ~25.
- **Risk notes:**
  - The PM story assumes SendGrid sends a signature header like Twilio does. It does not for Inbound Parse. The implementation must use Basic Auth or a shared-secret header instead. This is a scope clarification, not a blocker.
  - Need to update the SendGrid Inbound Parse configuration in their dashboard to include the auth credentials in the URL.
- **Revised effort:** S — agree. Straightforward.
- **Additional acceptance criteria:**
  - Use constant-time comparison (`hmac.compare_digest`) for the secret check.

---

### S-4: Block Vapi Webhook When Secret Not Configured in Production

**PM Story:** Reject Vapi webhook requests when secret is missing in production.
**PM Effort:** XS

**Engineering Specification:**

- **Files to modify:**
  - `app/api/webhooks.py` — `vapi_post_call()` at lines 315–331. Currently, when `VAPI_WEBHOOK_SECRET` is empty, the code falls through to the `else` branch (line 324–325) and logs a warning but processes the request regardless of environment.
- **Implementation approach:**
  1. Add an environment check inside the `else` branch (line 324):
     ```python
     else:
         if settings.ENVIRONMENT != "development":
             logger.critical("VAPI_WEBHOOK_SECRET not set in production — rejecting request")
             return Response(status_code=503, content='{"error": "webhook not configured"}')
         logger.warning("VAPI_WEBHOOK_SECRET not set — skipping auth in development")
     ```
  2. That's it. Literally a 4-line change.
- **Database changes:** None.
- **New dependencies:** None.
- **LOC estimate:** ~5.
- **Risk notes:** Almost none. The 503 response body says "webhook not configured" (generic, doesn't reveal the specific env var name). Confirm with PM that 503 is acceptable — Vapi may retry on 503, so we might want 403 instead.
- **Revised effort:** XS — agree. 15 minutes including test.
- **Additional acceptance criteria:**
  - Response content-type should be `application/json` for consistency.

---

### S-5: Parameterized Column Updates in Tool Functions

**PM Story:** Add defense-in-depth for dynamic column names in SQL update functions via allowlist + regex validation.
**PM Effort:** S

**Engineering Specification:**

- **Files to modify:**
  - `app/tools/contacts.py` — `update_contact()` at lines 126–159. Currently uses f-string for column names (line 147: `f"{k} = %s" for k in filtered`). The `valid_fields` allowlist (lines 128–134) already filters keys, but the column names are inserted via f-string without secondary validation.
  - New utility: `app/db/sql_utils.py` (new file) — shared `build_safe_update_clause(fields: dict, allowed: set) -> tuple[str, list]`.
  - `app/pipeline/commands/contact.py`, `app/pipeline/commands/status.py`, `app/pipeline/classifier.py` — grep shows these also call `update_contact` but they pass known keys. Still, verify no other dynamic-column patterns exist.
- **Implementation approach:**
  1. Create `build_safe_update_clause(fields, allowed)` that:
     - Filters keys against `allowed` set.
     - Validates each remaining key matches `^[a-z_]+$` regex — raises `ValueError` if not.
     - Double-quotes each column name in the SQL (`"name" = %s`) for safety with reserved words.
     - Returns `(set_clause_str, values_list)`.
  2. Refactor `update_contact()` to use this utility.
  3. Search for other f-string SQL column patterns across the codebase and refactor any found.
- **Database changes:** None.
- **New dependencies:** None.
- **LOC estimate:** ~50 (utility ~25, refactor ~25).
- **Risk notes:**
  - Low risk. The current allowlist already prevents injection for `update_contact`. This is defense-in-depth.
  - Double-quoting column names is a good practice but must be done carefully — PostgreSQL double-quoted identifiers are case-sensitive. All our column names are lowercase so this is fine.
- **Revised effort:** S — agree.
- **Additional acceptance criteria:**
  - The regex validation must run AFTER allowlist filtering as a second gate, not as a replacement.
  - Unit test: passing `{"'; DROP TABLE contacts--": "val"}` must result in zero columns updated.

---

### S-6: Proper HTML Sanitization for KB Uploads

**PM Story:** Replace regex-based HTML stripping with a proper sanitization library.
**PM Effort:** S

**Engineering Specification:**

- **Files to modify:**
  - `app/api/console.py` — lines 845–848. Currently:
    ```python
    import re
    content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r"<[^>]+>", "", content)
    ```
    The first regex misses `<script` with attributes containing `>`. The second strips ALL tags including legitimate content with angle brackets (e.g., `price < $500K`).
- **Implementation approach:**
  1. Add `nh3` to requirements (Rust-based, faster and more secure than `bleach` which is deprecated).
  2. Replace lines 846–848 with:
     ```python
     import nh3
     content = nh3.clean(content, tags=set(), attributes={})  # strip ALL HTML, keep text
     ```
     This strips every tag but preserves text content, handles edge cases (SVG scripts, event handlers, unicode bypasses) correctly.
  3. Remove the `import re` on line 846 (it's a local import only used here).
- **Database changes:** None.
- **New dependencies:** `nh3` (~50KB wheel, no C compilation needed).
- **LOC estimate:** ~5.
- **Risk notes:**
  - `bleach` is officially deprecated as of Jan 2023. `nh3` is the recommended successor.
  - The `nh3.clean(content, tags=set())` approach strips ALL HTML. If we later want to allow safe tags (bold, italic, links), we can expand the `tags` set.
  - Verify `nh3` handles the 50,000-char limit (line 839) without memory issues — it's Rust, so it will.
- **Revised effort:** XS — PM said S, but this is a 3-line change plus adding a dep. Downgrade to XS.
- **Additional acceptance criteria:**
  - Test with SVG-based XSS payload: `<svg onload="alert(1)">`.
  - Test that `price < $500K` preserves the `<` character correctly.

---

### S-7: Rate Limiting on Console Login

**PM Story:** Add rate limiting to prevent brute-force password attacks on `/console/login`.
**PM Effort:** S

**Engineering Specification:**

- **Files to modify:**
  - `app/api/console.py` — `login_submit()` at lines 60–68. Add rate limit check before `verify_password()`.
  - `app/api/console_auth.py` — add `check_rate_limit(ip: str) -> bool` and `record_failed_login(ip: str)` and `reset_rate_limit(ip: str)` functions.
  - `app/services/redis_pool.py` — already exists (lines 1–19), provides `get_redis_pool()`. We have Redis ready.
- **Implementation approach:**
  1. Use Redis sorted sets or simple key-based counters. Key pattern: `login_ratelimit:{ip}`.
  2. On each login attempt: `INCR` the key, `EXPIRE` it with 900s (15 min). If count > 5, return 429.
  3. On successful login: `DEL` the key.
  4. If Redis is unavailable (`redis.ConnectionError`): log WARNING, allow the attempt (fail-open).
  5. Add `Retry-After: <seconds>` header to 429 responses.
- **Database changes:** None.
- **New dependencies:** None (Redis already in requirements and `redis_pool.py` exists).
- **LOC estimate:** ~40.
- **Risk notes:**
  - PM mentions IPv6 rotation bypass. For now, IP-based is sufficient. A global rate limit (total failed logins per minute across all IPs) is a good V2 addition.
  - The fail-open behavior is correct — locking out all operators because Redis is down would be worse than accepting a brute-force risk temporarily.
  - PM's AC #4 says "reset counter on successful login" — this is correct, implement it.
- **Revised effort:** S — agree.
- **Additional acceptance criteria:**
  - Rate limit key must use the IP from `request.client.host`, NOT from `X-Forwarded-For` (which can be spoofed). If behind a proxy, use FastAPI's trusted-proxy middleware to get the real IP.

---

### P-1: Eliminate N+1 Queries in Agent List

**PM Story:** Replace correlated subqueries in `get_all_agents()` with JOINs to go from O(4n) to O(1).
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - `app/services/console_queries.py` — `get_all_agents()` at lines 123–141 (sync) and `async_get_all_agents()` at lines 1095–1114 (async). Both use the same query with 4 correlated subqueries (lines 129–135).
- **Implementation approach:**
  1. Replace the 4 correlated subqueries with LEFT JOINs and GROUP BY:
     ```sql
     SELECT a.*,
       COALESCE(cc.cnt, 0) AS contact_count,
       COALESCE(um.messages_today, 0) AS messages_today,
       um.last_active,
       COALESCE(te.error_count, 0) AS errors_24h
     FROM agents a
     LEFT JOIN (
       SELECT agent_id, COUNT(*) AS cnt FROM contacts GROUP BY agent_id
     ) cc ON cc.agent_id = a.id
     LEFT JOIN (
       SELECT agent_id,
              SUM(messages_sent) FILTER (WHERE date = CURRENT_DATE) AS messages_today,
              MAX(date) AS last_active
       FROM usage_metrics GROUP BY agent_id
     ) um ON um.agent_id = a.id
     LEFT JOIN (
       SELECT agent_id, COUNT(*) AS error_count
       FROM tool_executions
       WHERE error_message IS NOT NULL AND created_at > now() - interval '24 hours'
       GROUP BY agent_id
     ) te ON te.agent_id = a.id
     ORDER BY a.name
     ```
  2. Apply the same change to both sync and async versions.
  3. Verify the dashboard template still renders correctly (field names must match).
- **Database changes:** None. Consider adding index: `CREATE INDEX idx_tool_executions_agent_error ON tool_executions(agent_id, created_at) WHERE error_message IS NOT NULL` if it doesn't exist.
- **New dependencies:** None.
- **LOC estimate:** ~30 (rewrite query in both sync/async).
- **Risk notes:**
  - The current correlated subqueries are not O(4n) queries — they're actually 4 correlated subqueries in a SINGLE query (PostgreSQL executes them per-row, but it's still 1 SQL call). The PM says "4-subquery-per-row" which is correct at the execution plan level, but total network calls is already O(1). The fix is still valuable: correlated subqueries force nested-loop plans which degrade at scale.
  - Must preserve the null-safe behavior: agents with zero of everything must return 0, not NULL.
- **Revised effort:** S — downgrade from M. This is a single query rewrite in two places. Half-day max.
- **Additional acceptance criteria:**
  - Add `EXPLAIN ANALYZE` output comparison before/after in the PR description.

---

### P-2: Bounded Listing Search in Assembler

**PM Story:** Replace in-memory listing scan with a SQL-level text search for `_find_referenced_listing()`.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - `app/pipeline/assembler.py` — `_find_referenced_listing()` at lines 149–158. Currently calls `search_listings(agent_id, filters={"status": "active"})` which loads ALL active listings (see `app/tools/listings.py` line 159–189, returns up to 10 but the issue is the query fetches all matches in the DB), then iterates in Python checking for address part matches.
- **Implementation approach:**
  1. Extract address-like tokens from the message body (numbers, capitalized words). If no address-like tokens found, return `None` immediately (short-circuit per AC #4).
  2. Build a SQL query with `ILIKE` conditions:
     ```sql
     SELECT * FROM listings
     WHERE agent_id = %s AND status = 'active'
     AND (address ILIKE %s OR address ILIKE %s ...)
     LIMIT 5
     ```
  3. Use `set_agent_context()` + RLS for tenant isolation.
  4. Return best match (most tokens matched) or first match.
  5. Add a simple address-token extractor: split body, keep tokens with digits or length > 3, ignore common words ("the", "at", "on", etc.).
- **Database changes:** Consider adding a trigram index: `CREATE INDEX idx_listings_address_trgm ON listings USING gin(address gin_trgm_ops)` for fast ILIKE. Requires `pg_trgm` extension.
- **New dependencies:** None.
- **LOC estimate:** ~50.
- **Risk notes:**
  - The current `search_listings()` already has a LIMIT 10 in the SQL, so it's not loading ALL listings into memory — it loads at most 10. The real issue is that `_find_referenced_listing()` loads all active listings without any address filter, then scans in Python. With 500 listings, this is 500 rows transferred.
  - Addresses with apostrophes (O'Brien) need proper parameterization (already handled by psycopg's `%s`).
  - `tsvector` is overkill for address matching. `ILIKE` with trigram index is the right balance.
- **Revised effort:** S — downgrade from M. The function is 10 lines. Rewriting it with SQL-level filtering is straightforward.
- **Additional acceptance criteria:**
  - Log the extracted address tokens at DEBUG level for troubleshooting.
  - If no tokens are extracted from the message, skip the query entirely and return None.

---

### P-3: Async Conversation Summarization

**PM Story:** Move `_maybe_summarize_conversation()` out of the response hot path into a background task.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - `app/pipeline/dispatcher.py` — line 107–108. Currently calls `_maybe_summarize_conversation(agent.id, contact.id)` synchronously after dispatch. The comment on line 106 says "non-blocking" but it IS blocking — the function runs synchronously (lines 300–322) and calls `generate_or_update_summary()` which makes a Haiku LLM call.
  - The issue: `dispatch()` is called from `_process_inbound_message_sync()` in `webhooks.py` (line 32), which itself runs in `asyncio.to_thread()` (line 29). So the summarization blocks the thread, not the event loop. But it still adds 200–400ms to the total processing time for the message.
- **Implementation approach:**
  1. **Option A (recommended):** Use `asyncio.create_task()` — but we're in a sync function called via `to_thread()`, so we can't directly create async tasks. Instead, modify `dispatch()` to accept a `background_tasks: BackgroundTasks` parameter and add summarization as a background task.
  2. **Option B:** Fire a separate thread for summarization via `threading.Thread(target=_maybe_summarize_conversation, args=(...), daemon=True).start()`.
  3. **Option C:** Post to a Redis queue and let the trigger worker pick it up.
  4. **Recommendation:** Option B is simplest and achieves the goal. Option A requires threading `BackgroundTasks` through the entire call chain from the webhook handler down to dispatcher, which is a larger refactor.
  5. For deduplication (AC #4): use a Redis key `summarize_lock:{agent_id}:{contact_id}` with a 30s TTL via `SET NX EX 30`.
- **Database changes:** None.
- **New dependencies:** None.
- **LOC estimate:** ~25.
- **Risk notes:**
  - The comment on line 303 says "The summarization call uses Haiku which is fast (~200-400ms)" — but 200-400ms is significant when p95 target matters. Moving to background is the right call.
  - Thread safety: `_maybe_summarize_conversation()` already handles its own DB connection via `get_db_connection()` context manager, so running in a separate thread is safe.
  - Daemon threads will be killed on process shutdown — acceptable since summarization failure is non-fatal (assembler falls back to recent-messages-only per line 321).
- **Revised effort:** S — downgrade from M. Thread + Redis lock is ~25 lines. No call chain refactor needed with Option B.
- **Additional acceptance criteria:**
  - Log when deduplication prevents a concurrent summarization call.

---

### P-4: Cached Conversation History

**PM Story:** Cache conversation history in Redis to eliminate repeated DB hits during rapid back-and-forth messaging.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - `app/pipeline/assembler.py` — `_load_conversation_history()` at lines 130–148. Add Redis cache read/write around the DB query.
  - `app/services/redis_pool.py` — already exists, provides `get_redis_pool()`.
- **Implementation approach:**
  1. Before the DB query in `_load_conversation_history()`:
     - Build key: `conv:{agent_id}:{contact_id}`.
     - Try `redis.get(key)`. If hit, deserialize (JSON) and return.
  2. After the DB query:
     - Serialize the messages to JSON (just the fields needed for Message construction).
     - `redis.setex(key, 60, json_data)` — 60s TTL.
  3. Cache invalidation: in `_log_conversation()` in `dispatcher.py` (line 101), after writing the new message, `redis.delete(f"conv:{agent_id}:{contact_id}")`.
  4. Redis failure: catch `redis.RedisError`, log WARNING, fall through to DB.
- **Database changes:** None.
- **New dependencies:** None.
- **LOC estimate:** ~40.
- **Risk notes:**
  - PM lists A-3 (Redis caching layer) as a dependency. But Redis is already in the stack (`redis_pool.py` exists, Redis dep is in requirements). A-3 is about a generic caching abstraction — we don't need that to cache one thing. Remove the dependency.
  - Message serialization: `Message` objects need a `to_dict()` / `from_dict()` round-trip. Check if `Message` is a Pydantic model (it is, based on `schemas.py`), so `.model_dump_json()` / `Message.model_validate_json()` works.
  - Cache stampede risk is low with 60s TTL and the expected concurrency per-contact.
- **Revised effort:** S — downgrade from M. No dependency on A-3. This is a cache-aside pattern on a single function.
- **Additional acceptance criteria:**
  - Cache must be invalidated on message INSERT (both inbound and outbound), not just on TTL expiry.

---

### P-5: Native Vector Parameter Passing in RAG Search

**PM Story:** Pass embedding vectors as native Python lists instead of `str()` to avoid string parsing overhead.
**PM Effort:** XS

**Engineering Specification:**

- **Files to modify:**
  - `app/services/rag_service.py`:
    - `_upsert_chunks()` line 244: `str(embedding)` — change to pass raw list.
    - `search()` lines 279, 284, 296, 299, 312, 314: `str(query_embedding)` — change to pass raw list.
    All 7 occurrences of `str(embedding)` or `str(query_embedding)` need to be changed.
- **Implementation approach:**
  1. Replace all `str(embedding)` and `str(query_embedding)` with the raw list/array.
  2. The `pgvector` Python package (already installed, v0.3.6 in requirements) provides a `register_vector()` function for psycopg that handles automatic serialization of Python lists to PostgreSQL `vector` type. Call `register_vector(conn)` after obtaining the connection.
  3. Alternative: psycopg3 (which we use, `psycopg[binary]==3.2.4`) with pgvector 0.3.x supports passing lists directly if the `::vector` cast is in the SQL. Test this first — it may already work without `register_vector()`.
  4. Remove the `str()` calls and verify queries still work.
- **Database changes:** None.
- **New dependencies:** None (`pgvector` already installed).
- **LOC estimate:** ~15 (7 `str()` removals + register_vector setup).
- **Risk notes:**
  - Must test with both `_upsert_chunks()` and `search()` paths. If psycopg3 doesn't natively handle list-to-vector conversion, we need `pgvector.psycopg.register_vector(conn)` on every connection. This should be done in `get_db_connection()` to be automatic.
  - The `::vector` cast in the SQL (line 231, 289, etc.) should handle the type conversion, but verify.
- **Revised effort:** XS — agree. Quick change, but needs careful testing.
- **Additional acceptance criteria:**
  - Verify with a timing benchmark (before/after) on at least 100 search queries to quantify improvement.

---

### P-6: Selective Column Load in Daily Scanner

**PM Story:** Change `SELECT *` to explicit columns in `_get_all_active_agents()` to avoid loading large JSONB blobs.
**PM Effort:** XS

**Engineering Specification:**

- **Files to modify:**
  - `app/worker/daily_scanner.py` — `_get_all_active_agents()` at lines 377–381. Currently `SELECT * FROM agents`.
  - Downstream usage: `scan_agent()` (line 31) uses `agent.id`, `agent.name`, `agent.listing_rules` (line 386 in `_check_dom_alerts`), `agent.timezone` (used in trigger scheduling). `compile_morning_briefing()` (line 66) uses `agent.name`, `agent.id`.
  - `AgentConfig(**r)` constructor at line 381 — need to verify which fields are required vs optional.
- **Implementation approach:**
  1. Change query to:
     ```sql
     SELECT id, name, email, phone, timezone, twilio_number, autonomy_rules,
            listing_rules, system_prompt, briefing_time, current_status,
            status_until, voice_daily_cap_minutes, kb_expiration_policy,
            kb_default_ttl_days, active
     FROM agents
     ```
     Omit: `google_oauth` (large JSONB), `scheduling_prefs` (JSONB, not used in scanner), `style_profile` (JSONB, not used in scanner), `google_review_link`.
  2. Alternatively, create a `ScannerAgentConfig` NamedTuple or slim Pydantic model with only the fields the scanner needs.
  3. Add a comment above the SELECT listing which downstream functions use which columns.
- **Database changes:** None.
- **New dependencies:** None.
- **LOC estimate:** ~10.
- **Risk notes:**
  - `AgentConfig` is a Pydantic model. If `google_oauth`, `scheduling_prefs`, or `style_profile` are required fields without defaults, the constructor will fail. Check the schema — `schema.sql` shows `scheduling_prefs JSONB NOT NULL DEFAULT '{}'` and `style_profile JSONB NOT NULL DEFAULT '{}'`, so they always have values. But the Pydantic model may still require them. Safest approach: keep using `AgentConfig` but set defaults in the model for omitted fields, OR use a slim model.
  - The scanner also calls functions like `analyze_contact_gaps(agent.id)` and creates triggers that reference `agent` attributes. Need to trace every `agent.X` access in the full scan path to avoid missing a field.
  - Actually looking at `_check_dom_alerts()` (line 384), it does `SELECT * FROM listings` too — that's a separate P-2-style issue but not in scope here.
- **Revised effort:** XS — agree. Simple SELECT column list change.
- **Additional acceptance criteria:**
  - Add a code comment above the query listing which downstream functions require which columns.
  - If `AgentConfig` fails to construct with missing optional fields, add defaults to the Pydantic model rather than creating a second model.

---

## Engineering Notes

### Priority/Effort Disagreements

| Story | PM Effort | My Estimate | Reason |
|-------|-----------|-------------|--------|
| S-6 | S | **XS** | 3-line change + adding `nh3` dep. Not a half-day. |
| P-1 | M | **S** | Single query rewrite in 2 places. Half-day. |
| P-2 | M | **S** | 10-line function rewrite. |
| P-3 | M | **S** | Thread + Redis lock. No call chain refactor needed. |
| P-4 | M | **S** | Cache-aside on one function. A-3 dependency is unnecessary. |

### Stories to Combine

- **S-1 + S-2 + S-7** should be implemented together as a single "console auth overhaul" epic. S-2 (auth guards on query layer) depends on having a proper auth context from S-1. S-7 (rate limiting) is naturally part of the login flow built in S-1. Implementing S-2 or S-7 before S-1 means reworking them when S-1 lands.

### Stories to Split

- **S-1** could be split into: (a) user table + bcrypt auth + session rewrite, (b) audit logging, (c) role-based access control. Each is independently shippable.

### Dependencies to Remove

- **P-4** lists A-3 (Redis caching layer) as a dependency. Redis is already in the stack. Remove this dependency — P-4 can ship immediately.

### Recommended Implementation Order

**Phase 1 — Quick wins (1-2 days):**
1. S-4 (Vapi production block) — 15 min
2. S-6 (HTML sanitization) — 30 min
3. P-5 (native vector params) — 1 hr
4. P-6 (selective column load) — 1 hr

**Phase 2 — Small improvements (2-3 days):**
5. S-5 (parameterized column updates) — half-day
6. S-3 (SendGrid webhook auth) — half-day
7. P-1 (N+1 query fix) — half-day
8. P-2 (bounded listing search) — half-day
9. P-3 (async summarization) — half-day
10. S-7 (rate limiting) — half-day

**Phase 3 — Console auth overhaul (1 week):**
11. S-1 (per-user auth + audit trail) — depends on migration tooling
12. S-2 (auth guards) — depends on S-1
13. P-4 (cached conversation history) — independent, but schedule after the quick wins

**Total estimated effort: ~2 weeks** for one engineer, assuming no blockers.
