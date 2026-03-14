# Code Documentation Audit — Calloway Codebase

**Auditor:** Atlas, Engineering Lead
**Date:** 2026-03-14
**Scope:** 21 files across core, API, pipeline, services, workers, tools, database, and models

---

## 1. Executive Summary

**Overall Documentation Health: YELLOW (Adequate, with notable gaps)**

The Calloway codebase is in better shape than most early-stage SaaS products. Module-level docstrings exist on nearly every file, most public functions have docstrings, and the code itself is reasonably self-documenting with descriptive variable names and logical structure. A senior developer joining tomorrow could orient themselves within a day.

However, there are real gaps that would cause confusion, wasted time, or incorrect assumptions:

- **Business rules are underexplained.** TCPA consent gating, autonomy levels, model tiering decisions, and lifecycle stage transitions are implemented but not documented at the point of implementation.
- **Integration quirks are mostly undocumented.** Twilio signature validation bypass in dev, Vapi webhook authentication patterns, the RLS bypass in console_queries, and the "C-3 fix" pattern (asyncio.to_thread) are mentioned in passing but never explained thoroughly.
- **Magic numbers and thresholds are scattered without justification.** Why is the gap threshold for active_buyer 7 days? Why does voice cost ~$0.05/min? Why 50 messages before summarization? These are product decisions baked into code with no trail.
- **The largest file (handlers.py, ~474 lines visible) is actually well-structured** but could use more documentation on the system prompt design philosophy and tool execution safety model.
- **console_queries.py is 800+ lines of dense query logic** with good section headers but minimal function-level documentation explaining what each query powers and why it's shaped the way it is.

**Headline numbers:**
- 21 files audited
- 15 have module-level docstrings (good)
- 2 files have no module-level docstring at all (main.py, connection.py)
- ~60% of public functions have adequate docstrings
- ~10% of business-critical code sections have "why" comments
- 0 architecture decision records inline (patterns explained only in CLAUDE.md)

---

## 2. File-by-File Assessment

### Core

#### `app/main.py`
**Grade: C+**
**Priority: Medium**

What's documented well:
- OpenAPI tags have clear descriptions
- CORS section has a brief inline comment
- The CorrelationMiddleware has a class docstring

What's missing:
- No module-level docstring. A new developer opening this file first needs to know: this is the FastAPI entrypoint, here's the startup/shutdown lifecycle, here's the middleware stack order and why it matters.
- `lifespan()` function has no docstring explaining the initialization sequence (sync pool, async pool, why both exist).
- No comment explaining why routers are included in this specific order (if it matters) or that the order doesn't matter.
- No comment on the `STATIC_DIR` path resolution explaining the directory structure.

#### `app/config.py`
**Grade: B-**
**Priority: Low**

What's documented well:
- Settings are grouped by service with section comments
- `validate_production_secrets()` has a clear docstring and purpose
- `FIREBASE_SERVER_KEY` has a "Legacy — kept for backward compat" comment

What's missing:
- No module-level docstring explaining that this uses pydantic-settings, reads from .env, and is cached via lru_cache (singleton pattern).
- RAG settings (RAG_TOP_K, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP) have no comments explaining what these values mean or why these defaults were chosen.
- No comment on why `CONSOLE_PASSWORD` defaults to "changeme" rather than an empty string (the validate_production_secrets explains the safety check, but the default itself could confuse someone).

---

### API Layer

#### `app/api/webhooks.py`
**Grade: B**
**Priority: Medium**

What's documented well:
- Every endpoint has a docstring
- The pipeline processing flow is numbered (1. Normalize, 2. Resolve, etc.)
- "C-3 fix" and "C-4 fix" references point to known bug fixes
- TCPA keyword check has clear inline comment explaining it runs before pipeline processing
- Consent gate comment at step 2C

What's missing:
- No module-level docstring explaining what webhooks this file handles (Twilio SMS/voice, Vapi post-call, SendGrid email) and the overall pattern (receive, validate, enqueue to background, return 200 immediately).
- `_process_inbound_message_sync()` uses deferred imports (from app.pipeline.normalizer import ...) with no comment explaining why. This is a deliberate pattern to avoid circular imports, and a developer will wonder about it.
- The voice cost calculation `int(float(voice_mins) * 5)` — why 5? What rate does this represent? Is this Vapi's rate? Twilio's rate? An approximation?
- `_process_vapi_transcript_sync()` creates contacts with `name=f"Caller {event.sender_phone[-4:]}"` — why last 4 digits? This is a product decision that should be commented.
- The empty TwiML response pattern `<?xml ... <Response></Response>` is used multiple times but never explained (Twilio expects TwiML back; empty Response means "don't say/send anything").
- Voice fallback flow (ring agent 20 seconds, then forward to Vapi) has no comment explaining the 20-second/4-ring business decision.

#### `app/api/console.py`
**Grade: B+**
**Priority: Low**

What's documented well:
- Module-level docstring present
- Clear section separators (Auth, Dashboard, Tenants, etc.)
- HTMX partials are marked in docstrings
- CSRF handling pattern is documented with inline comments
- The `_render()` helper explains the CSRF cookie transfer pattern

What's missing:
- No comment explaining why CSRF is skipped on login (`# No CSRF on login` comment exists but doesn't explain the security reasoning fully — should note this is safe because the password itself is the auth factor and there's no CSRF cookie yet on first visit).
- Knowledge base tab routes have no comments explaining the chunk/embedding model — what is a "source_type"? What does "reindex" actually do? A developer looking at `/kb/{source_type}/{source_id}/reindex` needs context.
- The `50_000` character limit on KB uploads has no justification comment.
- HTML sanitization regex (`re.sub(r"<script[^>]*>.*?</script>"...`) has no comment explaining this is a security measure against XSS in user-uploaded content.

#### `app/api/console_auth.py`
**Grade: A-**
**Priority: Low**

What's documented well:
- Module-level docstring is clear and concise
- Every function has a docstring
- Session cookie configuration has comments on security flags
- CSRF section is clearly separated
- `httponly=False` on CSRF cookie has inline comment explaining why ("JS needs to read this for HTMX")

What's missing:
- `SESSION_MAX_AGE = 86400` — a comment noting "24 hours" is there, but no explanation of why 24 hours was chosen.
- No comment on why `hmac.compare_digest` is used instead of `==` (timing-attack prevention). A junior developer might "simplify" this.
- No explanation of the `URLSafeTimedSerializer` choice and what `itsdangerous` provides (signed tokens, expiration, tamper resistance).

---

### Pipeline

#### `app/pipeline/handlers.py`
**Grade: B**
**Priority: High**

What's documented well:
- Module-level docstring clearly lists what the module provides
- `COMMAND_CLASSIFY_PROMPT` is self-documenting — the prompt itself explains command types
- Command dispatch table `_COMMAND_HANDLERS` is clean and readable
- `SYSTEM_PROMPT_TEMPLATE` documents the AI assistant's behavioral rules
- Tool definitions have descriptions

What's missing:
- No documentation explaining the model tiering decision: WHY does command classification use Haiku while full reasoning uses Sonnet? What's the cost/quality tradeoff? This is a core architectural decision.
- `handle_full_reasoning()` assembles the system prompt from multiple sources (template, RAG context, contact info, listings, calendar) but there's no comment explaining the prompt assembly strategy or token budget considerations.
- `_execute_tool()` has no comment explaining the safety model: some tools return `{"queued": True}` for deferred execution vs. immediate execution. Why? What's the security implication?
- Tool definitions lack comments about which tools are "safe" (read-only) vs. which have side effects. The `create_showing_hold` description says "Do NOT confirm until client agrees" but this constraint isn't explained architecturally.
- The `max_rounds=3` in `handle_full_reasoning` calls `client.reason()` with no comment explaining why 3 rounds is the limit.
- `handle_listing_qa()` always uses Haiku — no comment explaining why this is safe (listing Q&A doesn't need complex reasoning, just factual recall).
- The system prompt includes "YOU NEVER" rules — no comment explaining these are TCPA/legal compliance guardrails, not just style preferences.

#### `app/pipeline/assembler.py`
**Grade: A-**
**Priority: Low**

What's documented well:
- Excellent module-level docstring explaining the summary injection strategy
- `TOKEN_BUDGET = 8000` and `TOKENS_PER_MESSAGE = 50` are named constants with a comment ("rough estimate")
- `RECENT_MESSAGES_WITH_SUMMARY = 15` is explained in context
- `assemble_context()` has clear intent-specific loading comments
- Token budget trimming strategy is documented with inline comments (trim history first, then listings, then drop summary as last resort)
- `_load_history_with_summary()` has a thorough docstring

What's missing:
- `_find_referenced_listing()` uses a heuristic (split address into parts, check if any part > 2 chars matches message body) with only `# Simple:` as a comment. This heuristic will produce false positives (e.g., "123" matching any address containing "123") and a developer needs to know this is a known limitation.
- `_load_relevant_listings()` loads ALL active listings for a contact — the function name suggests filtering by preferences but it doesn't. This discrepancy needs a comment or a TODO.
- `_load_calendar_placeholder()` says "Returns empty until Step 18" but doesn't explain what Step 18 is (Google Calendar integration). A developer won't know this refers to a build step from the project plan.
- `_estimate_tokens()` uses `200` tokens per listing and `50` per trigger with no explanation of how these estimates were derived.

#### `app/pipeline/dispatcher.py`
**Grade: B+**
**Priority: Medium**

What's documented well:
- Module-level docstring is present
- `MODEL_COST_MAP` has a clear comment ("Cost in cents per 1M tokens")
- Consent gate at the top of `dispatch()` is clearly commented
- Step numbering (0 through 7) provides clear flow
- `_maybe_append_feedback_prompt()` has a docstring referencing "Step 23A"
- `_maybe_summarize_conversation()` has a thorough docstring explaining why it's synchronous and what happens on failure

What's missing:
- `FEEDBACK_INTERVAL = 10` — why 10? Was this tested? Is this a product decision? No context.
- `MODEL_COST_MAP` duplicates the map in `anthropic_service.py`. No comment noting this duplication or explaining why it exists in two places (dispatcher uses it for usage metrics, anthropic_service uses it for per-call tracking).
- `_update_usage_metrics()` uses a cost formula `int(decision.tokens_used * (cost_rates["input"] + cost_rates["output"]) / 2_000_000)` — averaging input and output rates is an approximation. No comment explaining this trade-off vs. tracking input/output tokens separately.
- `_execute_queued_tool()` handles `send_personalized_listing_alert` with just a log message and a comment "Will be fully implemented with broadcast feature" — this should be a TODO/FIXME.
- Channel routing logic (email vs. SMS vs. agent command) in `dispatch()` has no comment explaining the priority order or why email is checked before SMS.

---

### Services

#### `app/services/anthropic_service.py`
**Grade: B+**
**Priority: Medium**

What's documented well:
- Module-level docstring covers the key concerns (tiering, caching, retry, token counting)
- Model constants are clearly named (HAIKU_MODEL, SONNET_MODEL)
- `MODEL_COSTS` has comments with dollar equivalents
- `_track_usage()` docstring explains the C-2 fix (migration from in-memory to DB)
- `classify()`, `reason()`, `compose()` all have docstrings explaining their purpose and model choice
- `cache_control: {"type": "ephemeral"}` is used but not explained

What's missing:
- `cache_control: {"type": "ephemeral"}` appears on every system prompt but is never explained. This is Anthropic's prompt caching feature that reduces cost on repeated system prompts. A developer unfamiliar with the Anthropic API will not know what this does or why it's there.
- `_call_with_retry()` uses exponential backoff (`2 ** (attempt + 1)`) but only retries on `RateLimitError`. No comment explaining why other errors aren't retried (API errors may indicate bad input, not transient failures).
- `reason()` handles the multi-round tool-use loop but there's no comment explaining why `max_rounds=3` is the default. What happens if a conversation legitimately needs 4+ tool calls?
- The exhaustion message "I need a moment to process this. Let me get back to you." is returned when rounds are exhausted — no comment explaining this is a graceful degradation, not an error.
- `compose()` can use either model but defaults to Haiku — no comment explaining when a caller should pass `model=SONNET_MODEL`.
- The singleton pattern (`_client: AnthropicClient | None = None`) has no comment about thread safety.

#### `app/services/console_queries.py`
**Grade: B-**
**Priority: Medium**

What's documented well:
- Module-level docstring explains the RLS bypass pattern clearly
- Section headers (System Pulse, Dashboard, Tenants, etc.) provide navigation
- `get_system_pulse()` docstring is clear
- Async wrapper functions follow a consistent naming pattern (`async_get_*`)

What's missing:
- Most functions lack docstrings beyond the section headers. When there are 800+ lines of query logic, each function needs a one-line docstring at minimum.
- The sync-to-async wrapper pattern (every `get_*` has an `async_get_*` that calls `asyncio.to_thread`) is never explained. Why do both exist? When should you use which?
- `create_agent_from_wizard()` and `create_agent_tenant()` contain significant business logic (default trigger creation, onboarding checklist) with no comments explaining the onboarding flow.
- Complex queries (e.g., health overview, cost aggregation) have no comments explaining what they're calculating or why specific time windows were chosen.
- No documentation on the relationship between this file and the console UI — which functions power which pages.

#### `app/services/rag_service.py`
**Grade: A-**
**Priority: Low**

What's documented well:
- Module-level docstring is clear
- Class docstring on `RAGService`
- All public methods have thorough docstrings with Args/Returns
- `_upsert_chunks()` explains the deduplication strategy
- `search()` documents the RLS enforcement
- `get_context_for_message()` is well-documented as the high-level API

What's missing:
- The `search()` method has duplicated SQL construction logic (the `if source_types:` branch builds params twice with different structures). This looks like a refactoring artifact and should have a comment or be cleaned up.
- No comment explaining why chunk content is truncated to 500 chars in `get_context_for_message()` — is this a token budget consideration?
- No explanation of why `set_agent_context` is called in `search()` but not in `_upsert_chunks()` (it is called in `_upsert_chunks` — but the pattern inconsistency between index methods calling `set_agent_context` directly vs. search also calling it could confuse someone).
- The HNSW index choice (vs. IVFFlat) for pgvector is documented in schema.sql but not referenced here.

#### `app/services/embedding_service.py`
**Grade: A**
**Priority: Low**

What's documented well:
- Module-level docstring is concise and accurate
- Constants are well-named with comments (EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, MAX_BATCH_SIZE)
- All methods have docstrings with Args/Returns
- `chunk_text()` explains the token approximation strategy ("1 token ~ 4 characters")
- Boundary detection logic in chunking is clear
- Infinite loop prevention comment is present

What's missing:
- `embed_query()` uses `input_type="query"` while `embed_texts()` uses `input_type="document"` — the docstring mentions "better retrieval" but doesn't explain the asymmetric embedding model (Voyage AI uses different embeddings for queries vs. documents for improved search relevance).
- No comment explaining why `voyage-3-lite` was chosen over `voyage-3` (cost vs. quality tradeoff, 512 vs. 1024 dimensions).

#### `app/services/summarization_service.py`
**Grade: A**
**Priority: Low**

What's documented well:
- Excellent module-level docstring explaining the entire design: model choice, summary structure, incremental approach, graceful fallback
- All thresholds are named constants with clear names
- Time-based thresholds have comments ("catches slow-burn buyers")
- Prompts are self-documenting and thorough
- `_needs_full_resummarization()` explains drift prevention
- The incremental update flow is well-commented
- `FULL_RESUMMARIZE_EVERY = 5` is used in context that makes the purpose clear

What's missing:
- `SUMMARIZATION_THRESHOLD = 50` — no comment explaining why 50 messages was chosen as the threshold. Is this based on token budget math? User testing?
- `INCREMENTAL_BATCH = 30` — same: why 30?
- `SUMMARY_TOKEN_ESTIMATE = 450` — how was this derived? Does it match the prompt instruction ("~450 tokens")?
- `_save_summary()` uses `ON CONFLICT (conversation_id)` — no comment explaining this means one summary per conversation (not per contact, which would be a different model).

---

### Workers

#### `app/worker/trigger_worker.py`
**Grade: B+**
**Priority: Medium**

What's documented well:
- Module-level docstring
- `process_due_triggers()` has excellent documentation of the `SELECT ... FOR UPDATE SKIP LOCKED` pattern with the C-1 fix reference
- `_fire_trigger()` clearly routes by action_type
- Recurrence logic is straightforward and readable

What's missing:
- `POLL_INTERVAL = 60` — no comment explaining why 60 seconds (tradeoff between latency and DB load).
- `LIMIT 50` in trigger claiming query — no comment explaining why 50 (batch size for throughput vs. lock contention).
- `_send_trigger_message()` checks `trigger.autonomy_level == "auto"` before sending directly, but no comment explains the full autonomy model (auto = send without approval, ask_agent = notify only).
- `revert_expired_statuses()` has no comment explaining what agent statuses are (e.g., "in_showings until 3pm" auto-reverts to "available"). The status system is a product feature that needs context.
- `_create_next_recurrence()` uses `timedelta(days=30)` for monthly — no comment noting this is approximate (not calendar-month accurate). February will drift.
- `_compile_report()` delegates to `_notify_agent()` with a comment "expanded in Step 34" — Step 34 is meaningless to a new developer.

#### `app/worker/daily_scanner.py`
**Grade: B**
**Priority: Medium**

What's documented well:
- Module-level docstring covers the three main responsibilities
- `scan_agent()` returns a results dict that documents what it checks
- `compile_morning_briefing()` is well-structured and readable
- `process_kb_expirations()` has a thorough docstring explaining the two policy modes
- `format_briefing_text()` and `format_seller_report()` are straightforward

What's missing:
- `run_daily_scan()` has no docstring explaining WHEN this runs, HOW it's invoked (cron? Railway scheduler? manual?), or how timezone-aware it is.
- `_check_dom_alerts()` references `agent.listing_rules.get("dom_alert_days", [30, 60, 90])` — no comment explaining what DOM means (Days On Market) or why [30, 60, 90] are the defaults.
- `_find_proactive_followups()` filters for `last_contact_at < now() - interval '2 days' AND last_contact_at > now() - interval '5 days'` — no comment explaining the 2-5 day window (not too early, not too late) or why this differs from gap analysis thresholds.
- `compile_seller_report()` references "Step 34" with no context.
- KB expiration processing has no comment explaining when `expires_at` gets set on embeddings (it's set via the console UI, but that's not obvious from this file).

---

### Tools

#### `app/tools/contacts.py`
**Grade: B**
**Priority: Medium**

What's documented well:
- Module-level docstring lists capabilities
- `GAP_THRESHOLDS` is a named constant with clear structure
- `lookup_contact()` explains the phone vs. name lookup difference
- `analyze_contact_gaps()` docstring explains it's shared between command and scanner

What's missing:
- `GAP_THRESHOLDS` values have no justification comments. Why is `active_buyer` 7 days and `active_seller` 14 days? These are product decisions.
- `create_contact()` builds PostgreSQL array syntax manually (`"{" + ",".join(...) + "}"`). No comment explaining why this is necessary (psycopg requires this format for TEXT[] columns) or noting this is a potential injection point if values aren't sanitized.
- `update_contact()` has a `valid_fields` allowlist but no comment explaining this is a security measure to prevent mass assignment.
- `search_contacts()` builds SQL dynamically with f-strings — no comment noting this is safe because column names come from a controlled set, not user input.
- `analyze_contact_gaps()` has `days_since = 999` for contacts with no `last_contact_at` — no comment explaining this sentinel value choice.

#### `app/tools/listings.py`
**Grade: B-**
**Priority: Medium**

What's documented well:
- Module-level docstring
- `LISTING_PARSE_PROMPT` is self-documenting
- `ingest_listing()` docstring explains the return tuple
- Freshness warning logic is clear

What's missing:
- `ingest_listing()` uses Haiku for parsing but no comment explains why (cheap, structured extraction is a good Haiku use case).
- The "check if listing already exists" logic in `ingest_listing()` silently converts new listing creation into an update if the address matches. This behavior should be documented as it could surprise a developer.
- `get_listing()` address matching uses `LIKE LOWER(%s)` which is fuzzy — no comment explaining the tradeoff (finds "123 Oak" even if agent typed "123 Oak Street") and the risk (could match wrong listing if addresses are similar).
- `search_listings()` `LIMIT 10` has no justification.
- `freshness_warning` is set on the model instance after DB load but isn't persisted. No comment explaining this is a computed, transient property.
- `update_listing()` returns `tuple[Listing, list[str]]` — the `list[str]` is always empty for updates. No comment explaining this asymmetry with `ingest_listing()` which returns missing fields.

#### `app/tools/transactions.py`
**Grade: B**
**Priority: Low**

What's documented well:
- Module-level docstring
- `VALID_STATUSES` and `VALID_TRANSACTION_TYPES` are clear constants
- `_sync_contact_lifecycle()` has a clear `stage_map` that documents the state machine
- Function signatures are descriptive

What's missing:
- `create_transaction()` auto-updates contact lifecycle to `under_contract` — this side effect should be prominently documented because it changes data outside the transactions table.
- `_sync_contact_lifecycle()` maps `fell_through` back to `active_buyer` — no comment explaining this assumes buyers, not sellers. A fell-through sale would need different handling.
- No comment on `update_transaction()` explaining that it doesn't validate status transitions (e.g., you could go from "closed" to "pending_offer").
- `VALID_STATUSES` and `VALID_TRANSACTION_TYPES` are defined but never enforced with validation in the create/update functions.

---

### Database

#### `app/db/schema.sql`
**Grade: B+**
**Priority: Medium**

What's documented well:
- Clear section separators with table numbers
- `embeddings` table has inline comments for `source_type` values and `vector(512)` dimensions
- HNSW index has a comment explaining its purpose
- pgvector extension creation is at the top
- Index names are descriptive

What's missing:
- No header comment explaining the overall schema design philosophy: tenant isolation via RLS, why `agent_id` is on every table, the relationship between `agents` and all other tables.
- RLS policy section at the bottom has no explanation of HOW `app.current_agent_id` gets set (via `set_agent_context()` in connection.py) or what happens if it's not set (queries return nothing).
- The `lead_preferences` RLS policy uses a subquery join through `contacts` — no comment explaining why (no `agent_id` column on `lead_preferences`).
- JSONB columns (`scheduling_prefs`, `style_profile`, `autonomy_rules`, `listing_rules`, `access_rules`) have no comments describing their expected shape/schema. These are effectively untyped and a developer won't know what to put in them.
- `consent_status` on contacts defaults to `'pending'` — no comment explaining the valid values (pending, granted, revoked) and the TCPA implications.
- `conversation_summaries.tenant_id` uses `tenant_id` while every other table uses `agent_id` — no comment explaining this naming inconsistency.
- `sender_type` on messages has no comment listing valid values (client, ai, agent_command).
- Table numbering jumps (8, 8A, 8B, 8C) suggesting tables were added incrementally — a note explaining this would help.

#### `app/db/connection.py`
**Grade: B**
**Priority: Medium**

What's documented well:
- Clear section separators (Sync pool, Async pool, RLS helpers, Query helpers)
- `get_db_connection()` has a good docstring with usage example
- `get_async_db_connection()` has a usage example
- Legacy alias is clearly marked as deprecated
- Pool initialization/close functions have clear docstrings
- `set_agent_context()` docstring is clear

What's missing:
- No module-level docstring. This is a critical infrastructure file that should explain: dual pool architecture (sync for workers, async for FastAPI), the RLS pattern, and the fallback behavior for tests.
- `get_connection_string()` builds a Supabase connection string from env vars with no comment explaining the URL format or why `pooler.supabase.com` is used (Supabase's connection pooler, required for serverless environments).
- `open=False` and `wait=False` on pool initialization have no comment explaining why (non-blocking startup, pool fills in background).
- The RLS helpers use `set_config(..., true)` — the `true` parameter means "local to current transaction." This is critical for security and has no comment.
- `execute_query()` has a subtle behavior: if `fetch_one` and `fetch_all` are both False, it commits. This should be documented.

---

### Models

#### `app/models/schemas.py`
**Grade: C+**
**Priority: High**

What's documented well:
- Module-level docstring is present
- Clear section separators (Core Data Models, Pipeline Models)
- Model names map clearly to database tables

What's missing:
- No model has field-level documentation. For a Pydantic models file, this is the single biggest gap. Key fields that NEED documentation:
  - `AgentConfig.autonomy_rules` — what's the schema? What are valid values?
  - `AgentConfig.listing_rules` — same problem
  - `AgentConfig.style_profile` — what keys does this contain?
  - `AgentConfig.scheduling_prefs` — undocumented shape
  - `AgentConfig.current_status` — what are the valid values?
  - `Contact.consent_status` — what values? What do they mean for TCPA?
  - `Contact.lifecycle_stage` — what are the valid stages and transitions?
  - `Contact.role` — what are valid roles?
  - `Listing.access_rules` — undocumented JSONB shape
  - `NormalizedEvent.channel` — the Literal type documents valid values, which is good
  - `IntentClassification.intent` — Literal type is good, but no docstring explaining what each intent means
  - `AgentDecision.triggers_to_create` — what's the dict shape?
  - `AgentDecision.notifications` — what's the dict shape?
  - `AgentDecision.tool_calls` — what's the dict shape?
- No class-level docstrings on any model explaining its purpose or relationship to other models.
- `Listing.freshness_warning` is a computed transient field — needs a comment explaining it's not persisted.
- `ConversationSummary.tenant_id` uses a different naming convention than all other models (`agent_id`). No comment explaining the inconsistency.

---

## 3. Pattern Analysis

### Business Rules Documentation
**Rating: Weak**

Business rules are implemented but rarely explained at the implementation site:
- TCPA consent model (pending/granted/revoked) is in code but the legal reasoning isn't documented
- Lifecycle stage transitions exist in multiple files with no central documentation of the state machine
- Autonomy levels (auto, ask_agent, supervised) are used in triggers and commands but never formally defined
- Gap thresholds, DOM alert days, and follow-up intervals are product decisions encoded as magic numbers

### Integration Quirks Documentation
**Rating: Moderate**

- Twilio: Signature validation bypass in dev is documented. TwiML response pattern is not.
- Anthropic: Cache control and model tiering are implemented but the cost/quality rationale is missing.
- Voyage AI: Asymmetric query/document embeddings are mentioned but not explained.
- Vapi: Webhook secret validation is documented. The voice flow (ring agent, then Vapi fallback) is partially documented.
- Supabase: RLS pattern is documented in console_queries but not in connection.py where it's implemented.

### Algorithm Documentation
**Rating: Moderate**

- Token estimation uses rough heuristics (50 tokens/message, 200 tokens/listing) without justification
- Address matching heuristic in assembler.py is acknowledged as "Simple" but not documented as limited
- Chunking algorithm in embedding_service.py is well-documented
- Summary incremental merge strategy is excellently documented

### Error Handling Documentation
**Rating: Weak**

- Most error handling follows a `try/except Exception` + `logger.error()` pattern
- No documentation on the error handling philosophy (fail silently, log, continue)
- No documentation on what happens to the user when pipeline errors occur
- The "graceful fallback" pattern (summarization failure falls back to recent messages) is well-documented in the one place it's used, but the same pattern appears elsewhere without comment

---

## 4. Specific Recommendations

### High Priority (Confusion-causing gaps)

#### `app/models/schemas.py`
1. Add class-level docstrings to every model explaining its purpose and which DB table it mirrors
2. Add field-level documentation for all JSONB-typed dict fields: `autonomy_rules`, `listing_rules`, `style_profile`, `scheduling_prefs`, `access_rules`, `preferences` — document expected keys and values
3. Add comments on `Contact.consent_status` listing valid values and TCPA implications
4. Add comments on `Contact.lifecycle_stage` listing valid stages and noting transitions happen in `transactions.py` and `contacts.py`
5. Add docstring to `AgentDecision` explaining the structure of `tool_calls`, `notifications`, and `triggers_to_create` dicts

#### `app/pipeline/handlers.py`
6. Add comment above `COMMAND_CLASSIFY_PROMPT` explaining why Haiku is used for classification (cost: ~$0.001/call, good enough accuracy for structured extraction)
7. Add comment in `handle_full_reasoning()` explaining the system prompt assembly order and why RAG context is injected into the system prompt rather than user messages
8. Add comment on `_execute_tool()` explaining the "queued" pattern: some tools return a deferred action that the dispatcher will execute, rather than executing immediately during LLM reasoning
9. Add comment on `SYSTEM_PROMPT_TEMPLATE` noting the "YOU NEVER" rules are TCPA/legal compliance requirements, not style preferences
10. Add comment explaining `max_rounds=3` default — prevents runaway tool loops while allowing multi-step reasoning

#### `app/db/schema.sql`
11. Add header comment explaining the RLS architecture: every table has `agent_id`, RLS policies use `app.current_agent_id` session variable, and `set_agent_context()` must be called before queries
12. Add comments on JSONB columns documenting expected shape (at minimum: `scheduling_prefs`, `style_profile`, `autonomy_rules`, `listing_rules`)
13. Add comment on `consent_status` column listing valid values and their meaning
14. Add comment on `conversation_summaries.tenant_id` explaining the naming inconsistency with `agent_id`
15. Add comment on `sender_type` in messages listing valid values

#### `app/db/connection.py`
16. Add module-level docstring explaining the dual pool architecture (sync for workers/backward compat, async for FastAPI handlers)
17. Add comment on `set_config(..., true)` explaining the `true` parameter means "local to current transaction" and is critical for RLS security

### Medium Priority (Time-wasting gaps)

#### `app/api/webhooks.py`
18. Add module-level docstring listing all webhook endpoints and the overall pattern (validate, enqueue, return 200)
19. Add comment explaining the deferred import pattern in `_process_inbound_message_sync()` (circular import avoidance)
20. Add comment on voice cost calculation `int(float(voice_mins) * 5)` explaining the rate and source
21. Add comment on the empty TwiML response pattern explaining Twilio expects TwiML

#### `app/pipeline/dispatcher.py`
22. Add comment on `MODEL_COST_MAP` noting it duplicates `anthropic_service.py` and explaining why
23. Add comment on `FEEDBACK_INTERVAL = 10` explaining the product reasoning
24. Convert the `send_personalized_listing_alert` stub to a proper `# TODO:` marker

#### `app/worker/trigger_worker.py`
25. Add comment on `POLL_INTERVAL = 60` explaining the latency/load tradeoff
26. Add comment on autonomy levels in `_send_trigger_message()` explaining the full model
27. Add comment on `_create_next_recurrence()` noting `timedelta(days=30)` is approximate for monthly

#### `app/worker/daily_scanner.py`
28. Add docstring to `run_daily_scan()` explaining invocation method and timezone handling
29. Add comment explaining what DOM means (Days On Market) on first use
30. Add comment on the 2-5 day follow-up window in `_find_proactive_followups()`
31. Replace "Step 34" references with actual descriptions

#### `app/tools/contacts.py`
32. Add justification comments to `GAP_THRESHOLDS` values
33. Add comment on the PostgreSQL array syntax construction explaining why it's necessary
34. Add comment on `valid_fields` allowlist noting it prevents mass assignment

#### `app/tools/listings.py`
35. Add comment in `ingest_listing()` explaining the silent update behavior when address matches
36. Add comment on address fuzzy matching explaining tradeoffs and risks

#### `app/services/anthropic_service.py`
37. Add comment on `cache_control: {"type": "ephemeral"}` explaining Anthropic's prompt caching feature
38. Add comment on the singleton pattern and thread safety considerations
39. Add comment explaining why only `RateLimitError` triggers retry

#### `app/services/console_queries.py`
40. Add one-line docstrings to all functions that currently lack them
41. Add comment explaining the sync/async wrapper pattern and when to use which

### Low Priority (Nice-to-have)

42. `app/main.py` — Add module-level docstring
43. `app/config.py` — Add module-level docstring; add comments on RAG default values
44. `app/api/console_auth.py` — Add comment on `hmac.compare_digest` explaining timing-attack prevention
45. `app/services/rag_service.py` — Clean up the duplicated SQL construction in `search()`
46. `app/services/embedding_service.py` — Add comment explaining `voyage-3-lite` selection rationale
47. `app/services/summarization_service.py` — Add comments on threshold values (50, 30, 450)

---

## 5. Documentation Standards Recommendation

### Proposed Standard: "Onboarding-Ready Documentation"

The goal is not academic completeness. The goal is: a senior developer can read any file and understand WHY it exists, WHY it makes the decisions it makes, and WHERE the landmines are — without asking anyone.

#### Required (enforce in code review):

1. **Module-level docstring on every file.** One to three sentences: what this module does, its role in the system, and any non-obvious dependencies. This is the single highest-impact documentation practice.

2. **Docstrings on all public functions.** At minimum: one sentence explaining what it does. For functions with non-obvious behavior, include params, returns, and side effects.

3. **"Why" comments on business rules.** Any time a number, threshold, or behavioral rule comes from a product decision (not a technical constraint), add a comment. Format: `# Business rule: [explanation]. See [source if applicable].`

4. **Integration comments on external service calls.** When calling Twilio, Anthropic, Voyage, Vapi, or Supabase, add a one-line comment if the call pattern is non-obvious (e.g., cache_control, input_type, TwiML format).

5. **Side-effect documentation.** If a function modifies data outside its primary table/concern, document it. Example: `create_transaction()` also updates the contact's lifecycle stage.

#### Encouraged (not blocking, but valued):

6. **Constants with justification.** Named constants are good. Named constants with a brief rationale are better. `POLL_INTERVAL = 60  # seconds — balances trigger latency against DB connection load`

7. **TODO/FIXME with context.** Always include WHO should address it and WHAT needs to happen. `# TODO(atlas): Replace with actual Google Calendar integration when OAuth flow is complete`

8. **Error handling comments.** When a try/except intentionally swallows errors (logging but continuing), add a one-line comment explaining why this is acceptable.

#### Explicitly NOT required:

- Type annotations on every variable (Python type hints on function signatures are sufficient)
- Docstrings on private helper functions (unless the logic is non-obvious)
- Inline comments restating what code does (`# Increment counter` before `counter += 1`)
- Separate documentation files for code that changes frequently (keep docs near the code)

---

*End of audit. 21 files reviewed. 47 specific recommendations provided.*
