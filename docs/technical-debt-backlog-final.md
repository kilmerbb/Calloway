# Calloway — Technical Debt Backlog (Final Aligned Version)

**Document ID:** PRD-DEBT-001-FINAL
**Author:** Mara (Product Manager), with engineering specifications by Atlas (Engineering Lead)
**Date:** 2026-03-14
**Status:** Final — PM/Eng Aligned. Ready for Solomon Review & Chronos Scheduling.
**Supersedes:** `docs/technical-debt-backlog.md`, `docs/eng-review-security-performance.md`, `docs/eng-review-architecture-testing.md`, `docs/eng-review-code-quality.md`

---

## 1. Change Log

Summary of all changes from the original backlog (PRD-DEBT-001) based on Atlas's engineering review across three documents.

| Story | Change Type | What Changed | Rationale |
|-------|------------|-------------|-----------|
| S-1 | Scope refined | Added bcrypt requirement, session TTL (1h) + refresh-on-activity, append-only audit_log, `LEGACY_AUTH_MODE` env var. Atlas confirmed file-level impl plan. | Eng review deepened the spec. PM agrees with all additions. |
| S-2 | Scope refined | Atlas recommends context-var approach over `Depends()` for 30+ functions. Must guard both sync and async (~60 total functions). `AuthorizationError` must be a distinct type. | Less invasive approach for 60 functions. PM accepts. |
| S-3 | Technical correction | SendGrid Inbound Parse does NOT use HMAC/ECDSA signatures. Must use HTTP Basic Auth on webhook URL instead. | Atlas read the actual SendGrid docs. PM's original assumption was wrong. Accepted. |
| S-4 | AC addition | Response should use 403 (not 503) to prevent Vapi retries. Content-type must be `application/json`. | PM agrees: 403 is safer. Updating AC #1. |
| S-5 | AC addition | Regex validation runs AFTER allowlist as second gate. Double-quote identifiers. Unit test for SQL injection payloads. | Defense-in-depth. PM accepts. |
| S-6 | Effort reduced | S -> **XS**. 3-line code change + adding `nh3` dep. `bleach` deprecated; `nh3` is the successor. | Atlas is right. This is a 30-min task, not a half-day. Accepted. |
| S-7 | AC addition | Rate limit key must use `request.client.host`, NOT `X-Forwarded-For`. Reset counter on successful login confirmed. | Prevents spoofed-header bypass. PM accepts. |
| P-1 | Effort reduced | M -> **S**. Single query rewrite in 2 places. Atlas clarified: current approach is 1 SQL call with 4 correlated subqueries (not 4 separate queries), but nested-loop plans still degrade at scale. | PM pushed back initially (see note below), but accepts S given the scope is truly one query rewrite in two code locations. |
| P-2 | Effort reduced | M -> **S**. Function is 10 lines. ILIKE with trigram index is recommended over tsvector. | PM accepts. The function really is small. |
| P-3 | Effort reduced | M -> **S**. Atlas recommends Option B (daemon thread + Redis lock) over BackgroundTasks threading. ~25 lines. | PM accepts Option B. Simpler, no call chain refactor. |
| P-4 | Absorbed into A-3 | **P-4 is now part of A-3.** A-3 already includes conversation history caching. Dependency on A-3 removed because Redis is already in the stack. | Atlas correctly identified the overlap. PM agrees to merge. |
| P-5 | No change | XS confirmed. `pgvector` 0.3.6 + psycopg3 already support native list passing. Need `register_vector()` call. | Aligned. |
| P-6 | AC addition | Must trace all `agent.X` accesses in full scan path. Add defaults to AgentConfig model if needed rather than creating a second model. | PM accepts. |
| A-1 | Dependency reversed | A-1 no longer depends on A-2. A-1 can be implemented first with consumer inside existing worker. A-2 becomes easier after A-1. | Atlas read the code: consumer can run in existing worker process. PM accepts reversal. |
| A-2 | Effort reduced | L -> **M**. Procfile already exists. Docker-compose needs one new service block. Pool tuning + graceful shutdown is the real work. | PM accepts. The Procfile discovery changes the picture. |
| A-3 | Effort reduced, scope expanded | L -> **M**. Agent config caching already exists in `agent_config.py`. Remaining: conversation + listing caches + invalidation hooks. Now absorbs P-4. | PM accepts. Partial implementation reduces effort. |
| A-4 | No change | M confirmed. Alembic is already in `requirements.txt`. Real work is baseline migration + RLS policy tracking. | Aligned. |
| A-5 | No change | L confirmed. Worker sync wrappers needed. Major test refactor (~20 mock targets change). | Aligned. |
| T-1 | No change | L confirmed. 24 functions, ~50-70 tests. Atlas confirmed existing `test_console.py` patterns to reuse. | Aligned. |
| T-2 | AC additions | Edge cases added: empty string vs None for `response_text`, NULL `consent_status`, `provider_message_id` storage. | PM accepts all additions. |
| T-3 | AC additions | Must programmatically verify all `agent_id` tables have RLS. `@pytest.mark.integration` marker. `lead_preferences` RLS uses subquery (slower, needs specific testing). | PM accepts. |
| T-4 | Scope flag | CSRF protection may not be implemented. If not, T-4 either depends on a new S-8 story or grows to L effort. | PM acknowledges. See open question OQ-9 below. |
| T-5 | AC additions | Two run modes (real + mock embeddings). `@pytest.mark.slow` marker. Accuracy report to stdout. | PM accepts. |
| T-6 | AC additions | `make load-test` must work with `docker-compose up`. Load test must NOT send real SMS. Seed script must be idempotent. DB pool utilization in results. | PM accepts all. |
| B-1 | No change | XL confirmed. Atlas agrees: do this last. 12-15 day budget. Consolidate with existing `app/dependencies.py`. | Aligned. |
| B-2 | Sequencing constraint | Must follow A-5. 60 bare excepts in `console_queries.py` would be double work if done before sync/async consolidation. Can do non-console files (123 instances) independently. | PM accepts phased approach. |
| B-3 | No change | L confirmed. TypedDict creation for ~30 console query functions is bulk of work. | Aligned. |
| B-5 | AC additions | Log model names at startup. `MODEL_COSTS` should key by tier ("haiku"/"sonnet"), not model ID string. | PM accepts. Tier-keyed costs are more robust. |
| B-6 | No change | XS confirmed. `python-dateutil` already in requirements. | Aligned. |
| B-7 | Merged with B-6 | Same PR as B-6. Same file, same function, same import. Combined: XS. | PM accepts. One PR, one review. |
| E-1 | **Closed** | Codebase already uses Pydantic v2 patterns. Zero v1 patterns found. `pydantic==2.10.6` in requirements. | Atlas's code audit is definitive. Story closed. |
| E-2 | No change | M confirmed. 40 template files, ~60 path updates in Python. Must be atomic (all at once). | Aligned. |
| E-3 | Effort reduced | M -> **S**. Agent CSS already has comprehensive token system (lines 7-90, 327 `var()` usages). Console CSS needs 19 hardcoded values replaced + token block expansion. | PM accepts. Agent CSS was further along than assumed. |
| E-4 | Effort reduced | L -> **M**. Console base template already has skip-nav, ARIA roles, `aria-current`. Foundation is better than PM assumed. | PM accepts. Atlas read the templates. |

### PM Pushback Notes

**P-1 (M -> S):** I initially pushed back on this downgrade because the acceptance criteria include performance benchmarking and null-safety validation across both sync/async paths. Atlas argues the query itself is straightforward. I accept S but want to note: if we discover the current query plan is more complex than expected (e.g., requires new indexes), this could expand back to M. Ship the query rewrite as S; the index work can be a follow-on if EXPLAIN ANALYZE reveals issues.

**B-2 phased approach:** Atlas wants to defer `console_queries.py` cleanup until after A-5. I agree with the logic (avoid double work on 60 blocks), but I want a hard constraint: B-2's non-console portion (123 instances across 39 files) must not be deferred along with it. Split B-2 into B-2a (non-console files, S effort) and B-2b (console_queries, XS effort after A-5).

---

## 2. Closed/Removed Stories

| Story | Original Title | Reason for Closure | Evidence |
|-------|---------------|-------------------|----------|
| E-1 | Pydantic v2 Migration Patterns | Already complete. Codebase uses `pydantic==2.10.6` with v2 patterns throughout. Zero v1 patterns found in codebase-wide search. | Atlas grepped for `class Config:`, `validator`, `schema_extra`, `.dict()`, `.json()` -- zero matches. |

**Verification action (before closing):** Run `pytest -W error::DeprecationWarning` and confirm zero `PydanticDeprecatedSince20` warnings. If clean, story is closed with no further work. Estimated effort for verification: 15 minutes.

---

## 3. Merged Stories

### Merge 1: B-6 + B-7 -> B-6/B-7 (Correct Date Recurrence)

**Rationale:** Same file (`trigger_worker.py`), same function (`_create_next_recurrence`), same import (`relativedelta`). Atlas confirms: one PR, one review, one deploy. Combined effort: XS (30 minutes coding, 30 minutes testing).

**Combined acceptance criteria:**
1. Monthly recurrence: Jan 31 + 1 month = Feb 28/29.
2. Annual recurrence: Feb 29 2024 + 1 year = Feb 28 2025.
3. Regular cases: Mar 15 + 1 month = Apr 15. Mar 1 + 1 year = Mar 1.
4. `python-dateutil` is already in `requirements.txt` (line 24). No new dep.
5. Unit tests for all edge cases above.

### Merge 2: P-4 absorbed into A-3

**Rationale:** A-3 (Redis caching layer) already includes conversation history caching in its scope. P-4 was a subset. Atlas confirmed: Redis is already in the stack (`redis_pool.py` exists, `redis==5.2.1` in requirements). The original P-4 dependency on A-3 is eliminated because A-3 now includes P-4's scope directly.

**Impact on A-3 acceptance criteria:** A-3 now includes:
- Agent config caching (already partially done in `agent_config.py` -- consolidate)
- Conversation history caching at `conv:{agent_id}:{contact_id}` with 60s TTL
- Active listings caching at `listings:{agent_id}` with 5-min TTL
- Cache invalidation on all write paths (message INSERT, agent config update, listing create/update)
- Generic cache layer in `app/services/cache.py` with `get/set/invalidate` + failure fallback
- Cache hit/miss counters on health endpoint
- All keys namespaced: `calloway:{type}:{id}`

### Merge 3: S-1 + S-2 + S-7 (Recommended Implementation Group)

**Note:** These are NOT merged into a single story -- they retain individual story IDs and acceptance criteria. However, Atlas strongly recommends implementing them together as a "console auth overhaul" unit because:
- S-2 (auth guards) depends on having a proper auth context from S-1
- S-7 (rate limiting) is naturally part of the login flow built in S-1
- Implementing S-2 or S-7 before S-1 means reworking them when S-1 lands

**PM decision:** Accept this as an implementation group. S-1 ships first within the group. S-2 and S-7 ship in the same sprint but as follow-on PRs. They share a single QA cycle.

---

## 4. Updated Backlog Table

After all merges, closures, effort revisions, and dependency changes. **30 active stories** (was 33; E-1 closed, P-4 absorbed into A-3, B-7 merged into B-6).

| ID | Story Title | Epic | Priority | Effort (Original) | Effort (Final) | Dependencies | Status |
|----|------------|------|----------|-------------------|----------------|-------------|--------|
| **S-4** | Block Vapi webhook without secret in prod | Security | P0 | XS | **XS** | None | Ready |
| **S-6** | Proper HTML sanitization for KB uploads | Security | P1 | S | **XS** | None | Ready |
| **S-3** | SendGrid webhook auth (Basic Auth) | Security | P0 | S | **S** | None | Ready |
| **S-5** | Parameterized column updates in tools | Security | P1 | S | **S** | None | Ready |
| **S-7** | Rate limiting on console login | Security | P1 | S | **S** | S-1 (impl group) | Ready |
| **S-2** | Authorization guard on console queries | Security | P0 | S | **S** | S-1 (impl group) | Ready |
| **S-1** | Per-user console auth with audit trail | Security | P0 | L | **L** | A-4 | Ready |
| **P-5** | Native vector params in RAG search | Performance | P1 | XS | **XS** | None | Ready |
| **P-6** | Selective column load in daily scanner | Performance | P1 | XS | **XS** | None | Ready |
| **P-1** | Eliminate N+1 queries in agent list | Performance | P0 | M | **S** | None | Ready |
| **P-2** | Bounded listing search in assembler | Performance | P0 | M | **S** | None | Ready |
| **P-3** | Async conversation summarization | Performance | P0 | M | **S** | None | Ready |
| **A-4** | Database migration tooling (Alembic) | Architecture | P1 | M | **M** | None | Ready |
| **A-2** | Separate worker from web server | Architecture | P1 | L | **M** | None | Ready |
| **A-3** | Redis caching layer (includes P-4) | Architecture | P1 | L | **M** | None | Ready |
| **A-5** | Consolidate sync/async query paths | Architecture | P1 | L | **L** | T-1 | Ready |
| **A-1** | Message queue for pipeline processing | Architecture | P1 | XL | **XL** | None (reversed) | Ready |
| **T-1** | Console queries test suite | Testing | P1 | L | **L** | None | Ready |
| **T-2** | Dispatcher test suite | Testing | P1 | M | **M** | None | Ready |
| **T-3** | Integration tests with real DB / RLS | Testing | P1 | L | **L** | None | Ready |
| **T-4** | Security test suite | Testing | P1 | M | **M** | S-3, S-4 | Ready |
| **T-5** | RAG search accuracy tests | Testing | P2 | M | **M** | None | Ready |
| **T-6** | Load/stress test harness | Testing | P2 | L | **L** | None | Ready |
| **B-6/B-7** | Correct date recurrence (monthly + annual) | Code Quality | P1 | XS+XS | **XS** | None | Ready |
| **B-5** | Configurable model names | Code Quality | P2 | S | **S** | None | Ready |
| **B-2a** | Bare except cleanup (non-console files) | Code Quality | P2 | M | **S** | None | Ready |
| **B-2b** | Bare except cleanup (console_queries) | Code Quality | P2 | M | **XS** | A-5 | Blocked |
| **B-3** | Structured return types | Code Quality | P2 | L | **L** | B-2a | Ready |
| **E-2** | Template component organization | Standards | P2 | M | **M** | None | Ready |
| **E-3** | CSS design token system | Standards | P2 | M | **S** | None | Ready |
| **E-4** | Accessibility basics (ARIA, focus mgmt) | Standards | P2 | L | **M** | E-2, E-3 | Blocked |
| **B-1** | Dependency injection for services | Code Quality | P2 | XL | **XL** | A-5 | Blocked |

### Revised Effort Summary

| Size | Count | Est. Days Each | Total Days |
|------|-------|---------------|------------|
| XS | 5 | 0.5 | 2.5 |
| S | 8 | 1-2 | 12 |
| M | 8 | 3-5 | 32 |
| L | 5 | 5-8 | 32.5 |
| XL | 2 | 10-15 | 25 |
| **Total** | **30** (was 33) | | **~104 days** (was ~128) |

**Net savings from eng review:** ~24 days. Primary reductions: E-1 closed (3-5 days), P-1/P-2/P-3 reduced (3 days each -> 1.5 each), A-2/A-3 reduced (5-8 days each -> 3-5 each), S-6 reduced (1-2 days -> 0.5), E-3 reduced (3-5 days -> 1-2 days), E-4 reduced (5-8 days -> 3-5 days).

---

## 5. Final Sequencing

This sequencing incorporates both PM priorities and Atlas's implementation order recommendations. Key principles:
1. Active bugs and quick security wins first
2. Test safety nets before major refactors
3. Foundation (Alembic) before schema-changing stories
4. Parallelize independent tracks
5. XL stories last, with full coverage in place

### Phase 1: Quick Wins & Active Bugs (Days 1-3)

All items are independent. Execute in parallel or rapid sequence.

| Order | Story | Effort | Why Now |
|-------|-------|--------|---------|
| 1 | B-6/B-7 | XS | Active bug causing trigger date drift. Ship today. |
| 2 | S-4 | XS | 4-line security fix. Ship today. |
| 3 | S-6 | XS | 3-line XSS fix. Ship today. |
| 4 | P-5 | XS | Free perf win. 7 `str()` removals. |
| 5 | P-6 | XS | Free perf win. SELECT column list change. |
| 6 | E-1 verify | XS | Run `pytest -W error::DeprecationWarning`, close the story. |

**Phase 1 exit criteria:** All XS items shipped and verified. E-1 confirmed closed.

### Phase 2: Small Security & Performance (Days 4-8)

| Order | Story | Effort | Why Now |
|-------|-------|--------|---------|
| 7 | S-3 | S | Open attack vector on email webhook. |
| 8 | S-5 | S | Defense-in-depth for SQL construction. |
| 9 | P-1 | S | Dashboard perf for operator experience. |
| 10 | P-2 | S | Prevents unbounded memory for large listing agents. |
| 11 | P-3 | S | 200-400ms latency reduction per message. |
| 12 | B-5 | S | Quick config win, no dependencies. |

**Phase 2 exit criteria:** All P0 performance stories done. Email webhook secured. Model names configurable.

### Phase 3: Foundation & Test Safety Nets (Days 9-18)

Two parallel tracks:

**Track A -- Foundation:**

| Order | Story | Effort | Why Now |
|-------|-------|--------|---------|
| 13 | A-4 | M | Enables all future schema changes. Prerequisite for S-1. |

**Track B -- Test Coverage:**

| Order | Story | Effort | Why Now |
|-------|-------|--------|---------|
| 14 | T-1 | L | Safety net for A-5 refactor. Must complete before A-5 starts. |
| 15 | T-2 | M | Safety net for pipeline changes (P-3, A-1). |
| 16 | T-4 | M | Security regression tests. S-3 and S-4 now done. |

**Phase 3 exit criteria:** Alembic operational with baseline migration. Console queries and dispatcher have test coverage. Security test suite green.

### Phase 4: Console Auth Overhaul (Days 19-28)

This is the S-1 + S-2 + S-7 implementation group.

| Order | Story | Effort | Why Now |
|-------|-------|--------|---------|
| 17 | S-1 | L | Core auth rewrite. A-4 is done (migration tooling ready). |
| 18 | S-2 | S | Auth guards on query layer. S-1 provides the auth context. |
| 19 | S-7 | S | Rate limiting. Login flow from S-1 is the integration point. |

**Phase 4 exit criteria:** Per-user auth live. Audit logging operational. Auth guards on all 60 query functions. Rate limiting active. `LEGACY_AUTH_MODE` available for transition.

### Phase 5: Architecture (Days 29-48)

Two parallel tracks:

**Track A -- Core Architecture:**

| Order | Story | Effort | Why Now |
|-------|-------|--------|---------|
| 20 | A-5 | L | Eliminates 700+ lines of duplication. T-1 provides safety net. |
| 21 | A-3 | M | Redis caching layer + P-4 conversation caching. Independent of A-5. |
| 22 | A-2 | M | Worker process separation. Independent. |

**Track B -- Integration Testing:**

| Order | Story | Effort | Why Now |
|-------|-------|--------|---------|
| 23 | T-3 | L | RLS verification with real DB. Independent. |

**Phase 5 exit criteria:** Console queries consolidated to async-only. Redis caching layer operational with conversation + listing + agent config caches. Worker runs as separate process. RLS policies verified by integration tests.

### Phase 6: Message Queue (Days 49-63)

| Order | Story | Effort | Why Now |
|-------|-------|--------|---------|
| 24 | A-1 | XL | Highest-risk story. All test coverage in place. Worker separation done (A-2). Full fallback to current behavior on failure. |

**Phase 6 exit criteria:** Redis Streams consumer operational. DLQ visible in console. Fallback to BackgroundTasks on Redis failure. Idempotent message processing.

### Phase 7: Code Quality & Standards (Days 64-104)

Lower urgency. Can be interleaved with feature work. Order matters for dependencies.

| Order | Story | Effort | Dependencies |
|-------|-------|--------|-------------|
| 25 | B-2a | S | None. 123 bare excepts across 39 non-console files. |
| 26 | B-2b | XS | A-5 done. Remaining ~30 bare excepts in consolidated console_queries. |
| 27 | E-3 | S | None. Console CSS token expansion. |
| 28 | E-2 | M | None. Template reorganization. |
| 29 | B-3 | L | B-2a done. TypedDicts + mypy config. |
| 30 | E-4 | M | E-2 + E-3 done. Accessibility audit + ARIA + focus management. |
| 31 | T-5 | M | None. RAG accuracy benchmark. |
| 32 | T-6 | L | None. Locust load test harness. |
| 33 | B-1 | XL | A-5 done. DI migration. Do absolutely last. |

**Phase 7 exit criteria:** All stories complete. CI lint rules for bare excepts. mypy passing on annotated files. All templates reorganized. WCAG 2.1 AA basics met. Load test harness operational.

### Critical Path

```
B-6/B-7, S-4, S-6, P-5, P-6 (parallel quick wins)
    |
    v
S-3, S-5, P-1, P-2, P-3, B-5 (parallel small items)
    |
    v
A-4 ---------> S-1 -> S-2 -> S-7
    |
T-1 ---------> A-5 ---------> B-2b -> B-1
    |
T-2, T-4       A-3 (parallel)
                A-2
    |             |
    v             v
T-3           A-1
    |
    v
E-3 -> E-2 -> E-4
B-2a -> B-3
T-5, T-6 (independent)
```

### Total Timeline

- **1 engineer:** ~104 working days (~5 months)
- **2 engineers (parallel tracks):** ~65 working days (~3 months)
- **2 engineers + feature work interleaving:** ~4 months realistic

---

## 6. Open Questions Update

### Resolved by Engineering Review

| OQ | Original Question | Resolution |
|----|------------------|------------|
| OQ-2 | Which SendGrid inbound parse version (v2 vs v3)? Signature verification differs. | **Resolved.** Atlas confirmed: SendGrid Inbound Parse does not use HMAC/ECDSA signatures at all. Implementation uses HTTP Basic Auth on the webhook URL. No version question applies. |
| OQ-3 | Redis Streams vs arq vs Celery for message queue? | **Resolved.** Atlas confirms Redis Streams is the right choice. `redis==5.2.1` already supports Streams (`XADD`, `XREADGROUP`, `XACK`). No new dependencies needed. Celery/arq are overkill for our throughput. |
| OQ-7 | Should drifted triggers from `timedelta` bugs get a one-time data migration? | **Partially resolved.** Atlas notes that existing triggers self-correct on next fire because the new recurrence calculation uses the trigger's `scheduled_at`, not current time. However, triggers that have not yet fired will remain off by 1-2 days until they do. **PM recommendation:** Ship B-6/B-7 code fix immediately. Run a one-time UPDATE query to correct `next_fire_at` for all monthly/annual triggers as a follow-up. Low risk, high correctness value. |
| OQ-8 | DI migration: big bang or incremental? | **Resolved.** Atlas recommends incremental migration with compatibility shims. PM agrees. Consolidate into existing `app/dependencies.py` rather than creating new file. Workers need separate `ServiceRegistry` (not `Depends()`). |

### Remaining Open

| OQ | Question | Needed By | Blocking? |
|----|----------|----------|-----------|
| OQ-1 | Console user management scope (S-1): How many operators? Full RBAC or simple admin/viewer? | Before S-1 implementation (Phase 4) | No -- simple admin/viewer is the default. Expand later if needed. |
| OQ-4 | Worker separation deployment target: Staying on Railway? | Before A-2 implementation (Phase 5) | No -- Railway is the default. Procfile already supports it. |
| OQ-5 | Test database strategy (T-3): Docker testcontainers, Supabase test project, or transaction rollback? | Before T-3 implementation (Phase 5) | No -- Docker + `docker-compose.test.yml` is the default per Atlas. |
| OQ-6 | Load test target environment: Dedicated staging? | Before T-6 implementation (Phase 7) | No -- local `docker-compose up` is the default per Atlas. |
| **OQ-9 (NEW)** | Does CSRF protection currently exist in the console? Atlas flagged that T-4 assumes CSRF is implemented but it may not be. If not, we need a new story S-8 (CSRF implementation) or T-4 grows from M to L. | Before T-4 implementation (Phase 3) | **Yes -- must answer before T-4 starts.** Atlas or any engineer should check `app/api/console.py` for CSRF middleware or token validation. |

---

## 7. PM Sign-Off Notes

### Assessment: Specs Are Tight Enough to Implement

After reviewing Atlas's engineering specifications across all three review documents, I am confident that **28 of 30 active stories are implementation-ready.** Atlas provided file-level location, line numbers, implementation approach options, LOC estimates, and risk notes for every story. The two stories needing more work before implementation:

1. **T-4 (Security test suite):** Blocked on OQ-9 (CSRF existence check). Once answered, scope is clear.
2. **A-1 (Message queue):** Implementation-ready on paper, but this is the highest-risk story (touches the critical message path). I want a design review session between Atlas and Solomon before coding begins in Phase 6. The fallback-to-BackgroundTasks pattern is critical and must be tested explicitly.

### What I Am Most Confident About

- **Quick wins (Phase 1-2):** These are fully specified down to the line number. B-6/B-7 is literally a 2-line change. S-4 is 4 lines. S-6 is 3 lines. Ship them.
- **Security stories:** Atlas's specifications for S-1 through S-7 are thorough. The SendGrid correction (S-3) was a valuable catch -- my original assumption was wrong.
- **Performance stories:** All downgrades from M to S are justified. The scope really is smaller than I estimated. I wrote the original estimates conservatively.

### What I Am Watching Closely

- **A-5 (sync/async consolidation):** This is an 800-line deletion that touches every console route import. T-1 must be green before this starts. No exceptions.
- **B-1 (dependency injection):** XL effort, touches 40+ modules, circular import risk. This is the story most likely to blow its estimate. I want bi-weekly check-ins during implementation.
- **S-1 (per-user auth):** The `LEGACY_AUTH_MODE` transition period doubles the auth testing surface. Consider time-boxing legacy mode to 30 days after deployment, then hard-cut.
- **B-2 split (B-2a/B-2b):** I split this to avoid double work, but I want B-2a to include the `ruff` lint rule (`BLE001`) in CI immediately so we stop accumulating new bare excepts while waiting for A-5 to unblock B-2b.

### What Changed My Mind

Atlas's code-level review changed my understanding in three places:
1. **SendGrid doesn't do HMAC on Inbound Parse.** I wrote S-3 assuming it worked like Twilio. It does not. Basic Auth is the correct approach.
2. **Agent CSS already has a full token system.** I wrote E-3 assuming both CSS files needed tokens from scratch. Agent CSS has 327 `var()` usages already. The real work is console-only.
3. **Pydantic v2 migration is already done.** I included E-1 based on the audit flag without checking the actual code. Atlas found zero v1 patterns. Story closed.

These three corrections alone save ~10-12 engineering days. This is why PM/Eng alignment reviews matter.

### Final Recommendation to Solomon

This backlog is ready for Chronos to build a project plan. The sequencing above is agreed between PM and Eng. Total effort is ~104 days for one engineer, ~65 days with two parallel tracks, ~4 months realistic with feature work interleaving. I recommend starting Phase 1 immediately -- every item in it is a quick win that reduces active risk.

---

*This document is the single source of truth for the technical debt backlog. The four source documents (`technical-debt-backlog.md`, `eng-review-security-performance.md`, `eng-review-architecture-testing.md`, `eng-review-code-quality.md`) are retained for reference but should not be used for planning or implementation. All acceptance criteria from both PM and Eng reviews are incorporated above.*

*-- Mara, Product Manager*
