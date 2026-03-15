# Calloway Sprint Plan — Q2 2026

**Document ID:** PLAN-Q2-2026
**Author:** Chronos (Program Manager)
**Date:** 2026-03-15
**Inputs:** `docs/technical-debt-backlog-final.md` (30 stories, ~104 eng-days), `docs/audit-2026-03-15-consolidated.md` (67 findings)
**Status:** Draft — Pending Solomon approval

---

## Plan Summary

**Total scope:** 30 existing backlog stories (~104 eng-days) + 19 net-new audit findings (~36 eng-days) = **~140 eng-days of work**.

**Resource:** 1 engineer (Atlas), full-time.

**Sprint structure:** 2-week sprints (10 working days), 20% buffer = 8 effective days per sprint. Capacity allocation starts at 80% debt/audit work (6.4 days/sprint) in early sprints, declining to 50% (4 days/sprint) as critical items clear.

**Timeline:** 11 sprints, 2026-03-16 through 2026-08-21 (22 weeks). Critical security and performance items clear by end of Sprint 3 (2026-04-24). All P0/P1 work complete by end of Sprint 6 (2026-06-05). Full backlog closure targeted Sprint 11 (2026-08-21).

**Key milestones:**
- **M1 (Sprint 1):** All critical security vulnerabilities patched
- **M2 (Sprint 2):** All high-severity security + critical performance fixes shipped
- **M3 (Sprint 3):** Security hardening complete, test safety nets in place
- **M4 (Sprint 6):** Console auth overhaul live, architecture foundations laid
- **M5 (Sprint 9):** Architecture modernization complete
- **M6 (Sprint 11):** Full backlog + audit closure

---

## Sprint Calendar

### Sprint 1: 2026-03-16 → 2026-03-27 — Critical Security + Quick Wins
**Capacity:** 8 effective days | **Allocation:** 100% debt/audit (launch sprint, no feature interleave)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| SEC-C1: XSS in conversation deep-link | Audit (new) | 0.25d | @eng | Pending |
| SEC-C2: XSS in agent portal reply | Audit (new) | 0.25d | @eng | Pending |
| SEC-C3: Onboarding endpoint auth | Audit (new) | 0.5d | @eng | Pending |
| SEC-H1: Twilio signature on 3 endpoints | Audit (new) | 0.5d | @eng | Pending |
| SEC-H2: agent_id scoping in update_contact | Audit (new) | 0.25d | @eng | Pending |
| SEC-H3: agent_id scoping in _sync_contact_lifecycle | Audit (new) | 0.25d | @eng | Pending |
| S-4: Block Vapi webhook without secret | Backlog | 0.5d | @eng | Pending |
| S-6: HTML sanitization (nh3) | Backlog | 0.5d | @eng | Pending |
| B-6/B-7: Correct date recurrence | Backlog | 0.5d | @eng | Pending |
| P-5: Native vector params | Backlog | 0.5d | @eng | Pending |
| P-6: Selective column load | Backlog | 0.5d | @eng | Pending |
| E-1 verify: Pydantic v2 confirmation | Backlog | 0.25d | @eng | Pending |
| SEC-H5: Auth-gate /health/metrics | Audit (new) | 0.5d | @eng | Pending |

**Sprint total:** ~4.75d estimated | **Buffer remaining:** ~3.25d
**Sprint 1 exit criteria:** All critical XSS patched. Onboarding endpoint gated. Twilio signatures validated on all endpoints. All XS backlog quick wins shipped. E-1 confirmed closed.

---

### Sprint 2: 2026-03-30 → 2026-04-10 — High Security + Small Performance
**Capacity:** 8 effective days | **Allocation:** 80% debt/audit (6.4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| S-3: SendGrid webhook auth (Basic Auth) | Backlog | 1.5d | @eng | Pending |
| S-5: Parameterized column updates | Backlog (covers SEC-M1/PERF-C4) | 1.5d | @eng | Pending |
| SEC-H4: Rate limit agent portal login | Audit (new) | 1d | @eng | Pending |
| SEC-M2: Separate agent portal session secret | Audit (new) | 0.5d | @eng | Pending |
| SEC-M3: POST-based logout | Audit (new) | 0.5d | @eng | Pending |
| SEC-M4: Password complexity validation | Audit (new) | 0.5d | @eng | Pending |
| PERF-C3: Consolidate Redis clients | Audit (covers ARCH-2 partial) | 1d | @eng | Pending |

**Sprint total:** ~6.5d estimated | **Buffer remaining:** ~1.5d (feature-available)
**Sprint 2 exit criteria:** Email webhook secured. ILIKE wildcards escaped in all 7 locations. Agent portal login rate-limited. All medium security findings addressed. Redis client consolidation complete.

---

### Sprint 3: 2026-04-13 → 2026-04-24 — Performance Fixes + Critical Test Gaps
**Capacity:** 8 effective days | **Allocation:** 80% debt/audit (6.4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| P-1: Eliminate N+1 in agent list | Backlog | 1.5d | @eng | Pending |
| P-2: Bounded listing search | Backlog | 1.5d | @eng | Pending |
| P-3: Async conversation summarization | Backlog | 1.5d | @eng | Pending |
| B-5: Configurable model names | Backlog | 1.5d | @eng | Pending |
| PERF-H2: Conditional feedback prompt | Audit (new) | 0.5d | @eng | Pending |
| PERF-H3: Deduplicate usage metric tracking | Audit (new) | 0.5d | @eng | Pending |

**Sprint total:** ~7d estimated | **Buffer remaining:** ~1d
**Sprint 3 exit criteria:** All P0 performance stories done. Dashboard query performance improved. Model names configurable. Unnecessary DB writes eliminated.

---

### Sprint 4: 2026-04-27 → 2026-05-08 — Foundation + Test Safety Nets
**Capacity:** 8 effective days | **Allocation:** 80% debt/audit (6.4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| A-4: Database migration tooling (Alembic) | Backlog | 4d | @eng | Pending |
| ARCH-1: Extract shared pipeline orchestration | Audit (new) | 1.5d | @eng | Pending |
| PERF-H7: Optimize analyze_contact_gaps | Audit (new) | 0.5d | @eng | Pending |

**Sprint total:** ~6d estimated | **Buffer remaining:** ~2d (feature-available)
**Sprint 4 exit criteria:** Alembic operational with baseline migration. Pipeline orchestration deduplicated from 3 copies to 1 shared function.

---

### Sprint 5: 2026-05-11 → 2026-05-22 — Test Coverage + Console Auth Start
**Capacity:** 8 effective days | **Allocation:** 70% debt/audit (5.6d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| T-1: Console queries test suite | Backlog | 6d | @eng | Pending |
| T-4: Security test suite (depends S-3, S-4) | Backlog | 4d | @eng | Pending |

**Sprint total:** ~10d estimated — **overflows to Sprint 6** (T-4 starts here, finishes Sprint 6)
**Note:** T-1 is the critical-path blocker for A-5. Prioritize T-1 completion within this sprint. T-4 may carry over 1-2 days into Sprint 6.

**Sprint 5 exit criteria:** T-1 complete (console queries have safety net for A-5). T-4 in progress.

---

### Sprint 6: 2026-05-25 → 2026-06-05 — Console Auth Overhaul (S-1 Group)
**Capacity:** 8 effective days | **Allocation:** 70% debt/audit (5.6d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| T-4: Security test suite (carry-over) | Backlog | 1d (remaining) | @eng | Pending |
| T-2: Dispatcher test suite | Backlog | 4d | @eng | Pending |
| S-1: Per-user console auth + audit trail | Backlog | — | @eng | Pending |

**Sprint total:** ~5d T-4+T-2 | S-1 starts late in sprint if capacity allows
**Note:** S-1 is L-sized (6-8 days) and depends on A-4 (done Sprint 4). S-1 begins here and carries into Sprint 7. T-2 provides safety net for pipeline changes.

**Sprint 6 exit criteria:** T-4 and T-2 complete. S-1 implementation in progress.

---

### Sprint 7: 2026-06-08 → 2026-06-19 — Console Auth Completion + Agent Portal Tests
**Capacity:** 8 effective days | **Allocation:** 60% debt/audit (4.8d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| S-1: Per-user console auth (continued) | Backlog | 5d (remaining) | @eng | Pending |
| S-2: Authorization guard on console queries | Backlog | 1.5d | @eng | Pending |
| S-7: Rate limiting on console login | Backlog | 1.5d | @eng | Pending |
| PERF-H4: Agent portal contacts pagination | Audit (new) | 1d | @eng | Pending |
| PERF-H5: Agent portal messages limit | Audit (new) | 0.5d | @eng | Pending |

**Sprint total:** ~9.5d — tight, may push PERF-H4/H5 to Sprint 8
**Sprint 7 exit criteria:** Per-user auth live. Audit logging operational. Auth guards on all 60 query functions. Rate limiting active. LEGACY_AUTH_MODE available.

---

### Sprint 8: 2026-06-22 → 2026-07-03 — Architecture Phase
**Capacity:** 8 effective days | **Allocation:** 60% debt/audit (4.8d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| A-5: Consolidate sync/async query paths | Backlog | 6d | @eng | Pending |
| PERF-H4: Agent portal contacts pagination (carry-over if needed) | Audit | 1d | @eng | Pending |
| PERF-H5: Agent portal messages limit (carry-over if needed) | Audit | 0.5d | @eng | Pending |

**Sprint total:** ~7.5d
**Note:** A-5 depends on T-1 (completed Sprint 5). This is the 800-line deletion that consolidates sync/async duplication. High-risk — T-1 safety net is essential.

**Sprint 8 exit criteria:** Console queries consolidated to async-only. ~700 lines of duplication removed.

---

### Sprint 9: 2026-07-06 → 2026-07-17 — Architecture Continued + Caching
**Capacity:** 8 effective days | **Allocation:** 50% debt/audit (4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| A-3: Redis caching layer (includes P-4) | Backlog | 4d | @eng | Pending |
| A-2: Separate worker from web server | Backlog | 4d | @eng | Pending |
| PERF-H6: LATERAL JOIN for agent portal conversations | Audit (new) | 0.5d | @eng | Pending |
| B-2a: Bare except cleanup (non-console) | Backlog | 1.5d | @eng | Pending |
| B-2b: Bare except cleanup (console, post-A-5) | Backlog | 0.5d | @eng | Pending |

**Sprint total:** ~10.5d — **overflows**. A-2 may carry to Sprint 10.
**Sprint 9 exit criteria:** Redis caching layer operational. B-2a/B-2b complete. Worker separation in progress.

---

### Sprint 10: 2026-07-20 → 2026-07-31 — Message Queue + Code Quality
**Capacity:** 8 effective days | **Allocation:** 50% debt/audit (4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| A-2: Worker separation (carry-over) | Backlog | 2d (remaining) | @eng | Pending |
| T-3: Integration tests with real DB / RLS | Backlog | 6d | @eng | Pending |
| E-3: CSS design token system | Backlog | 1.5d | @eng | Pending |

**Sprint total:** ~9.5d — tight. T-3 may carry over.
**Sprint 10 exit criteria:** Worker runs as separate process. RLS verification tests in progress. Console CSS tokens expanded.

---

### Sprint 11: 2026-08-03 → 2026-08-14 — Standards + Remaining Quality
**Capacity:** 8 effective days | **Allocation:** 50% debt/audit (4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| T-3: Integration tests (carry-over) | Backlog | 2d (remaining) | @eng | Pending |
| E-2: Template component organization | Backlog | 4d | @eng | Pending |
| B-3: Structured return types | Backlog | 6d | @eng | Pending |

**Sprint total:** ~12d — **overflows**. B-3 carries to Sprint 12.
**Sprint 11 exit criteria:** RLS integration tests complete. Templates reorganized.

---

### Sprint 12: 2026-08-17 → 2026-08-28 — Structured Types + Accessibility
**Capacity:** 8 effective days | **Allocation:** 50% debt/audit (4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| B-3: Structured return types (carry-over) | Backlog | 2d (remaining) | @eng | Pending |
| E-4: Accessibility basics (ARIA, focus mgmt) | Backlog | 4d | @eng | Pending |
| DOC-1: Mobile API documentation (16 endpoints) | Audit (new) | 2d | @eng | Pending |
| DOC-2: Fix inaccurate OpenAPI schemas | Audit (new) | 0.5d | @eng | Pending |

**Sprint total:** ~8.5d
**Sprint 12 exit criteria:** TypedDicts on console query functions. WCAG 2.1 AA basics met. Mobile API documented.

---

### Sprint 13: 2026-08-31 → 2026-09-11 — XL Stories + Remaining Items
**Capacity:** 8 effective days | **Allocation:** 50% debt/audit (4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| A-1: Message queue for pipeline processing | Backlog | 12d | @eng | Pending |

**Sprint total:** A-1 spans Sprints 13-14 (XL story). Design review with Solomon before coding begins.

---

### Sprint 14: 2026-09-14 → 2026-09-25 — Message Queue Completion + Test Harnesses
**Capacity:** 8 effective days | **Allocation:** 50% debt/audit (4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| A-1: Message queue (continued) | Backlog | 4d (remaining) | @eng | Pending |
| T-5: RAG search accuracy tests | Backlog | 4d | @eng | Pending |
| T-6: Load/stress test harness | Backlog | 6d | @eng | Pending |

**Sprint total:** ~14d — T-6 carries to Sprint 15.

---

### Sprint 15: 2026-09-28 → 2026-10-09 — DI Migration + Load Testing
**Capacity:** 8 effective days | **Allocation:** 50% debt/audit (4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| T-6: Load test harness (carry-over) | Backlog | 2d (remaining) | @eng | Pending |
| B-1: Dependency injection for services | Backlog | 12d | @eng | Pending |

**Sprint total:** B-1 spans Sprints 15-16.

---

### Sprint 16: 2026-10-12 → 2026-10-23 — DI Migration Completion
**Capacity:** 8 effective days | **Allocation:** 50% debt/audit (4d)

| Story/Finding | Source | Effort | Owner | Status |
|---|---|---|---|---|
| B-1: Dependency injection (continued) | Backlog | 4d (remaining) | @eng | Pending |
| ARCH-3: Split god-modules (console_queries, console, agent_portal) | Audit (new) | 3d | @eng | Pending |

**Sprint total:** ~7d
**Sprint 16 exit criteria:** DI migration complete. God-modules split. **Full backlog + audit closure.**

---

## Milestone Tracker

| ID | Milestone | Target Date | Exit Criteria | Status |
|----|-----------|-------------|---------------|--------|
| M1 | Critical security patched | 2026-03-27 | SEC-C1/C2/C3, SEC-H1/H2/H3, S-4, S-6 all deployed | Pending |
| M2 | High security + perf fixes | 2026-04-10 | All high-severity security, ILIKE wildcards, Redis consolidation done | Pending |
| M3 | Performance baseline | 2026-04-24 | All P0 performance stories shipped, unnecessary writes eliminated | Pending |
| M4 | Foundation in place | 2026-05-08 | Alembic operational, pipeline deduped | Pending |
| M5 | Test safety nets | 2026-05-22 | T-1 complete (console queries covered), T-4 in progress | Pending |
| M6 | Console auth live | 2026-06-19 | S-1+S-2+S-7 shipped, per-user auth, audit logging, rate limiting | Pending |
| M7 | Sync/async consolidated | 2026-07-03 | A-5 complete, 700+ LOC duplication removed | Pending |
| M8 | Architecture modernized | 2026-07-31 | A-2, A-3 complete, caching layer live, worker separated | Pending |
| M9 | Full coverage | 2026-08-28 | T-3 integration tests, E-2/E-3/E-4, B-3, API docs complete | Pending |
| M10 | Backlog closure | 2026-10-23 | A-1, B-1, T-5, T-6 complete. All 67 audit findings resolved. | Pending |

---

## Risk Register

| ID | Risk | Probability | Impact | Mitigation |
|----|------|-------------|--------|------------|
| R-1 | S-1 (per-user auth) exceeds L estimate due to LEGACY_AUTH_MODE dual-path testing | Medium | High — blocks S-2, S-7 | Time-box legacy mode to 30 days post-deploy. Limit test matrix to happy + 3 key error paths per mode. |
| R-2 | A-5 (sync/async consolidation) breaks console routes — 800-line deletion | Medium | Critical — production outage | T-1 must be 100% green before A-5 starts. No exceptions. Feature-flag rollback path. |
| R-3 | A-1 (message queue) disrupts critical message pipeline | High | Critical — messages lost | Design review with Solomon before Sprint 13. Full fallback to BackgroundTasks on Redis failure. Idempotent processing. DLQ monitoring. |
| R-4 | B-1 (DI migration) exceeds XL estimate — 40+ modules, circular import risk | High | Medium — schedule slip | Incremental migration with compatibility shims. Bi-weekly check-ins. Do absolutely last. |
| R-5 | Feature work exceeds planned interleave capacity (20-50% per sprint) | Medium | Medium — debt sprints slip | Track feature hours weekly. If >30% of sprint consumed by features in Sprints 1-3, escalate to Solomon immediately. |
| R-6 | OQ-9 (CSRF existence) not answered before T-4 | Low | Medium — T-4 scope uncertain | Atlas checks `app/api/console.py` for CSRF middleware during Sprint 1. If missing, create S-8 story (M effort) and insert into Sprint 3. |
| R-7 | SEC-C3 (onboarding auth) fix may break agent onboarding flow for legitimate users | Medium | High — blocks new agent setup | Implement auth (API key or admin token), test with existing onboarding flow before deploy. Coordinate with Solomon on rollout. |
| R-8 | 1 engineer capacity insufficient for 140-day backlog in 22 weeks | High | Medium — tail extends | Accept: at 50% capacity post-Sprint 6, effective output is ~4d/sprint. Plan already accounts for this. XL stories (A-1, B-1) are last and can be deprioritized if feature pressure mounts. |
| R-9 | Net-new audit findings introduce unplanned dependencies with existing stories | Low | Low — minor rework | Cross-reference table below tracks all overlaps. No hidden dependencies identified. |

---

## Audit Finding → Backlog Cross-Reference

### Security Findings (16 total)

| Audit Finding | Severity | Existing Story | Action | Sprint |
|---|---|---|---|---|
| SEC-C1 (XSS conversation deep-link) | Critical | None | **New story** — `html.escape()` on message body interpolation | 1 |
| SEC-C2 (XSS agent portal reply) | Critical | None | **New story** — `html.escape()` on body variable | 1 |
| SEC-C3 (Onboarding no auth) | Critical | None | **New story** — Add authentication to onboarding endpoint | 1 |
| SEC-H1 (Twilio signature on 3 endpoints) | High | None — S-3 covers SendGrid only, not Twilio status/voice | **New story** — Extend Twilio validation to status, voice, voice-fallback | 1 |
| SEC-H2 (update_contact missing agent_id) | High | None | **New story** — Add `WHERE agent_id = %s` to update_contact | 1 |
| SEC-H3 (_sync_contact_lifecycle missing agent_id) | High | None | **New story** — Add `WHERE agent_id = %s` to _sync_contact_lifecycle | 1 |
| SEC-H4 (Agent portal login rate limit) | High | None — S-7 covers console login, not agent portal | **New story** — Rate limit SMS code verification on agent portal | 2 |
| SEC-H5 (/health/metrics no auth) | High | None | **New story** — Auth-gate metrics endpoint | 1 |
| SEC-M1 (ILIKE wildcard injection, 7 locations) | Medium | **S-5** (parameterized column updates + ILIKE escaping) | **Already covered** — S-5 AC includes regex validation + ILIKE escaping | 2 |
| SEC-M2 (Session secret reuse for agent portal) | Medium | None | **New story** — Separate `AGENT_PORTAL_SESSION_SECRET` | 2 |
| SEC-M3 (GET-based logout, CSRF) | Medium | None | **New story** — Change logout to POST with CSRF token | 2 |
| SEC-M4 (Password complexity) | Medium | None | **New story** — Add password complexity validation | 2 |
| Positive: Parameterized SQL everywhere | — | — | No action | — |
| Positive: scrypt hashing | — | — | No action | — |
| Positive: CSRF on forms | — | — | No action (contradicts SEC-M3 for logout only) | — |
| Positive: JWT deny-list, rotation | — | — | No action | — |

### Performance Findings (25 total)

| Audit Finding | Severity | Existing Story | Action | Sprint |
|---|---|---|---|---|
| PERF-C1 (Sync Anthropic blocks pipeline) | Critical | **A-5** (sync/async consolidation) + **A-1** (message queue) | **Already covered** — A-5 eliminates sync path, A-1 decouples pipeline | 8, 13-14 |
| PERF-C2 (Sync DB pool saturation) | Critical | **A-5** (sync/async consolidation) | **Already covered** — async pipeline eliminates held sync connections | 8 |
| PERF-C3 (Duplicate Redis client) | Critical | **ARCH-2** partial overlap, but no existing story | **New story** — Consolidate agent_config.py Redis client into redis_pool.py | 2 |
| PERF-C4 (ILIKE wildcard in assembler) | Critical | **S-5** (ILIKE escaping) | **Already covered** — S-5 covers all 7 ILIKE locations | 2 |
| PERF-H1 (Dispatcher sequential DB queries) | High | **P-1** (N+1 queries) partial overlap | **Partially covered** — P-1 addresses agent list. Dispatcher optimization is separate but lower priority. Defer to A-5 async consolidation. | 8 |
| PERF-H2 (Feedback prompt on every response) | High | None | **New story** — Conditional check (every 10th response) before DB UPDATE | 3 |
| PERF-H3 (Double usage metric tracking) | High | None | **New story** — Deduplicate UPSERT to single call per message | 3 |
| PERF-H4 (Agent portal contacts no pagination) | High | None | **New story** — Add pagination to agent portal contacts list | 7 |
| PERF-H5 (Agent portal messages no limit) | High | None | **New story** — Add message limit/pagination to conversation detail | 7 |
| PERF-H6 (Correlated subquery in agent portal) | High | None | **New story** — Replace correlated subquery with LATERAL JOIN | 9 |
| PERF-H7 (analyze_contact_gaps SELECT *) | High | None — P-6 covers daily scanner, not analyze_contact_gaps | **New story** — Replace SELECT * with specific columns + DB-side filtering | 4 |
| PERF-M1 through M9 (9 medium findings) | Medium | Various partial overlaps with A-3, A-5 | **Mostly covered** by existing architecture stories. Residual items are low-effort optimizations that can ride along with parent stories. | Various |
| PERF-L1 through L5 (5 low findings) | Low | None | **Deferred** — Track as backlog items for future sprints. No dedicated sprint allocation. | Backlog |

### Architecture Findings (12 total)

| Audit Finding | Severity | Existing Story | Action | Sprint |
|---|---|---|---|---|
| ARCH-1 (Pipeline orchestration copy-pasted 3x) | Critical | None | **New story** — Extract shared pipeline orchestration function in webhooks.py | 4 |
| ARCH-2 (3 Redis client patterns) | Critical | **A-3** (Redis caching layer) partial overlap | **Partially covered** — PERF-C3 fix consolidates clients. A-3 builds proper caching layer on unified client. | 2 (client), 9 (layer) |
| ARCH-3 (3 god-modules need splitting) | Critical | None — B-3 adds types but does not split modules | **New story** — Split console_queries.py, console.py, agent_portal.py into sub-modules | 16 |
| ARCH-4 (183 bare excepts) | High | **B-2a** (123 non-console) + **B-2b** (console post-A-5) | **Already covered** — B-2a/B-2b address all 183 locations | 9 |
| ARCH-5 (Sync/async duplication) | High | **A-5** (consolidate sync/async) | **Already covered** | 8 |
| ARCH-6 through ARCH-12 (remaining) | Med-Low | Various overlaps with A-2, A-3, B-1 | **Mostly covered** by existing architecture stories | Various |

### Test Coverage Gaps (10 total)

| Audit Finding | Existing Story | Action | Sprint |
|---|---|---|---|
| Gap 1: agent_portal.py (0 tests) | None | **New story** — Covered by agent portal pagination work + security fixes. Add functional tests during PERF-H4/H5 implementation. | 7 |
| Gap 2: console_auth.py (indirect only) | **T-4** (security test suite) | **Already covered** — T-4 includes auth bypass, rate limit regression tests | 5-6 |
| Gap 3: message_consumer.py (0 tests) | None | **Deferred** — Add tests when A-1 (message queue) refactors consumer | 13-14 |
| Gap 4: twilio_service.py (0 tests) | None | **Deferred** — Lower risk (well-established SDK wrapper). Track for future sprint. | Backlog |
| Gap 5: billing_service.py (minimal) | None | **Deferred** — Financial risk but low change frequency. Track for future sprint. | Backlog |
| Gap 6: firebase_service.py (minimal) | None | **Deferred** — SDK wrapper. Track for future sprint. | Backlog |
| Gap 7: onboarding.py (0 tests) | None | **Add tests with SEC-C3 fix** — Auth gate needs test coverage | 1 |
| Gap 8: lead_scoring.py (0 tests) | None | **Deferred** — Algorithmic but not user-facing critical path. Track for future sprint. | Backlog |
| Gap 9: drip_campaigns.py (0 tests) | None | **Deferred** — TCPA compliance risk, but consent pipeline is separately tested. Track. | Backlog |
| Gap 10: dispatcher.py core functions | **T-2** (dispatcher test suite) | **Already covered** — T-2 specifically targets dispatcher | 6 |

### API Documentation Gaps (9 total)

| Audit Finding | Existing Story | Action | Sprint |
|---|---|---|---|
| Mobile API undocumented (16 endpoints) | None | **New story** — Document all mobile REST + WebSocket endpoints in openapi.yaml | 12 |
| JWT Bearer scheme missing from YAML | None | **Bundle with Mobile API docs** | 12 |
| SendGrid auth undocumented | None | **Bundle with S-3 implementation** — Update openapi.yaml when adding Basic Auth | 2 |
| Console login schema inaccurate | None | **Bundle with S-1 implementation** — Update openapi.yaml when adding per-user auth | 7 |
| 5 low-severity doc gaps | None | **Deferred** — Track for future sprint | Backlog |

---

## Summary: Net-New Work from Audit

| ID | Description | Effort | Sprint |
|----|-------------|--------|--------|
| SEC-C1 | XSS fix: conversation deep-link | 0.25d | 1 |
| SEC-C2 | XSS fix: agent portal reply | 0.25d | 1 |
| SEC-C3 | Auth gate on onboarding endpoint + tests | 0.5d | 1 |
| SEC-H1 | Twilio signature on 3 additional endpoints | 0.5d | 1 |
| SEC-H2 | agent_id scoping in update_contact | 0.25d | 1 |
| SEC-H3 | agent_id scoping in _sync_contact_lifecycle | 0.25d | 1 |
| SEC-H4 | Rate limit agent portal login | 1d | 2 |
| SEC-H5 | Auth-gate /health/metrics | 0.5d | 1 |
| SEC-M2 | Separate agent portal session secret | 0.5d | 2 |
| SEC-M3 | POST-based logout | 0.5d | 2 |
| SEC-M4 | Password complexity validation | 0.5d | 2 |
| PERF-C3 | Consolidate Redis clients | 1d | 2 |
| PERF-H2 | Conditional feedback prompt | 0.5d | 3 |
| PERF-H3 | Deduplicate usage metrics | 0.5d | 3 |
| PERF-H4 | Agent portal contacts pagination | 1d | 7 |
| PERF-H5 | Agent portal messages limit | 0.5d | 7 |
| PERF-H6 | LATERAL JOIN for agent portal | 0.5d | 9 |
| PERF-H7 | Optimize analyze_contact_gaps | 0.5d | 4 |
| ARCH-1 | Extract shared pipeline orchestration | 1.5d | 4 |
| ARCH-3 | Split god-modules | 3d | 16 |
| DOC-1 | Mobile API documentation | 2d | 12 |
| DOC-2 | Fix inaccurate OpenAPI schemas | 0.5d | 12 |
| **Total net-new** | | **~16.5d** | |

**Note:** The original estimate of ~36 net-new days was conservative. After thorough cross-referencing, many audit findings are already covered by existing backlog stories. The true net-new effort is ~16.5 engineering days, bringing the combined total to **~120.5 days** (down from the initial 140-day estimate).

---

## Dependency Graph (Simplified)

```
Sprint 1: SEC-C1/C2/C3, SEC-H1/H2/H3/H5, S-4, S-6, B-6/B-7, P-5, P-6
    │
Sprint 2: S-3, S-5(+SEC-M1/PERF-C4), SEC-H4, SEC-M2/M3/M4, PERF-C3
    │
Sprint 3: P-1, P-2, P-3, B-5, PERF-H2, PERF-H3
    │
Sprint 4: A-4, ARCH-1, PERF-H7
    │
Sprint 5: T-1 ─────────────────────────────────────┐
    │                                                │
Sprint 6: T-4, T-2                                   │
    │                                                │
Sprint 7: S-1 → S-2 → S-7, PERF-H4/H5              │
    │                                                │
Sprint 8: A-5 (depends on T-1) ◄────────────────────┘
    │
Sprint 9: A-3, A-2, B-2a/B-2b (B-2b depends on A-5), PERF-H6
    │
Sprint 10: T-3, E-3, A-2 carry-over
    │
Sprint 11: E-2, B-3 (depends on B-2a)
    │
Sprint 12: E-4 (depends on E-2, E-3), B-3 carry-over, DOC-1/DOC-2
    │
Sprint 13-14: A-1 (depends on A-2), T-5, T-6
    │
Sprint 15-16: B-1 (depends on A-5), ARCH-3
```

---

## Open Questions

| ID | Question | Needed By | Blocking? | Default |
|----|----------|-----------|-----------|---------|
| OQ-1 | Console user management scope for S-1: simple admin/viewer or full RBAC? | Sprint 7 | No | Simple admin/viewer |
| OQ-4 | Worker separation deployment target: staying on Railway? | Sprint 9 | No | Railway (Procfile already exists) |
| OQ-5 | Test database strategy for T-3: Docker testcontainers, Supabase, or transaction rollback? | Sprint 10 | No | Docker + docker-compose.test.yml |
| OQ-6 | Load test target environment for T-6: dedicated staging? | Sprint 14 | No | Local docker-compose |
| OQ-9 | Does CSRF protection currently exist in the console? Impacts T-4 scope. | Sprint 5 | **Yes** | Atlas checks during Sprint 1. If missing, create S-8 (M effort) and insert into Sprint 3. |
| OQ-10 | SEC-C3: What auth mechanism for onboarding? API key, admin token, or invitation-link? | Sprint 1 | **Yes — answer before implementation** | Admin-generated invitation token with expiry. |
| OQ-11 | ARCH-3 (god-module split): Should this precede or follow B-1 (DI migration)? | Sprint 15 | No | After B-1 — DI patterns inform module boundaries. |
| OQ-12 | Agent portal tests (Gap 1): Standalone test suite story or bundle with PERF-H4/H5 fixes? | Sprint 7 | No | Bundle with pagination work — tests ship with the code. |

---

## Revision History

| Date | Change | Author |
|------|--------|--------|
| 2026-03-15 | Initial plan created from backlog + audit cross-reference | Chronos |

---

*This plan is the scheduling authority for all technical debt and audit remediation work. The technical debt backlog (`docs/technical-debt-backlog-final.md`) remains the source of truth for story acceptance criteria and engineering specifications. The audit report (`docs/audit-2026-03-15-consolidated.md`) remains the source of truth for finding details.*

*— Chronos, Program Manager*
