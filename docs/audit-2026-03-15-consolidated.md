# Calloway — Consolidated Codebase Audit

**Date:** 2026-03-15
**Audited by:** Atlas (Engineering Lead) × 5 parallel agents
**Scope:** Full codebase — security, performance, architecture, test coverage, API documentation
**Codebase:** 87 Python files, 18,630 LOC application code, 12,334 LOC tests (45 test files)

---

## Executive Summary

The Calloway codebase is **architecturally sound with strong foundations** — parameterized SQL everywhere, RLS tenant isolation on 15/19 tables, fail-safe Redis caching, production secret validation at startup, and a well-designed pipeline stage pattern. However, the audit identified **3 critical security vulnerabilities, 4 critical performance issues, and 10 critical test coverage gaps** that need attention. The API documentation is 78% complete but missing the entire Mobile API (16 endpoints).

### Findings by Severity

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Security | 3 | 5 | 4 | 4 | 16 |
| Performance | 4 | 7 | 9 | 5 | 25 |
| Architecture | 3 | 5 | 4 | — | 12 |
| Test Coverage | 10 gaps | — | — | — | 10 |
| API Docs | — | 2 | 2 | 5 | 9 |
| **Total** | **20** | **14** | **19** | **14** | **67** |

---

## 1. Security Audit

### Critical (fix immediately)

| ID | Issue | File | Impact |
|----|-------|------|--------|
| SEC-C1 | **XSS in conversation deep-link view** — message bodies interpolated into raw HTML via f-strings with zero escaping | `app/api/conversations.py:79,83-95` | Stored XSS via push notification deep link |
| SEC-C2 | **XSS in agent portal conversation reply** — `body` variable inserted into HTML without escaping | `app/api/agent_portal.py:772-777` | Reflected XSS on agent-submitted input |
| SEC-C3 | **Onboarding endpoint has no authentication** — anyone can create agent accounts | `app/api/onboarding.py:33-83` | Resource exhaustion, data pollution |

### High (fix before next release)

| ID | Issue | File | Impact |
|----|-------|------|--------|
| SEC-H1 | Twilio webhook signature validation missing on 3 of 4 endpoints (status, voice, voice-fallback) | `app/api/webhooks.py:251-366` | Forged delivery status / voice call flows |
| SEC-H2 | `update_contact()` missing `agent_id` scoping — updates by `contact_id` alone | `app/tools/contacts.py:127-158` | Cross-tenant contact modification |
| SEC-H3 | `_sync_contact_lifecycle()` missing `agent_id` scoping | `app/tools/transactions.py:133-154` | Cross-tenant lifecycle update |
| SEC-H4 | Agent portal login has no rate limiting on SMS code verification | `app/api/agent_portal.py:148-209` | Brute-force 6-digit code |
| SEC-H5 | `/health/metrics` exposes cross-tenant aggregate data without auth | `app/api/health.py:67-88` | Business intelligence leak |

### Medium

| ID | Issue | File |
|----|-------|------|
| SEC-M1 | ILIKE wildcard injection in 7 search locations (not SQL injection, but data leakage) | Multiple files |
| SEC-M2 | `CONSOLE_SESSION_SECRET` reused for agent portal sessions (trivially derived) | `app/api/agent_portal.py:80` |
| SEC-M3 | Logout uses GET (CSRF vulnerable via link prefetching) | Console + agent portal |
| SEC-M4 | Missing password complexity validation on console user creation | `app/api/console_auth.py:316-350` |

### Positive Security Findings

- Parameterized SQL everywhere (60+ queries audited)
- scrypt password hashing with random 32-byte salt + `hmac.compare_digest`
- Production secret validation refuses startup with weak secrets
- No `|safe` filters or autoescape disabling in 30 Jinja2 templates
- CSRF double-submit cookie pattern on all state-changing forms
- Mobile JWT: JTI deny-list, token rotation on refresh, 30-min access expiry
- Anti-enumeration on mobile login
- Webhook signature verification for Stripe, Vapi, SendGrid
- httponly + samesite=lax + secure cookies
- Audit logging on console state-changing operations

---

## 2. Performance Audit

### Critical

| ID | Issue | File | Impact |
|----|-------|------|--------|
| PERF-C1 | **Sync Anthropic API calls block pipeline** — `time.sleep()` on rate limits, sync HTTP calls tie up thread for 5-45s per message | `app/services/anthropic_service.py:82-96` | ThreadPoolExecutor saturation at 50+ concurrent messages |
| PERF-C2 | **Sync DB pool saturation** — pipeline holds sync connection for full duration including LLM calls (5-45s) | `app/pipeline/assembler.py`, `resolver.py`, `router.py` | Pool exhausted (max 5) with 20 concurrent messages |
| PERF-C3 | **Duplicate Redis client** in `agent_config.py` — unbounded pool separate from `redis_pool.py` | `app/services/agent_config.py:15-19` | Redis connection exhaustion under load |
| PERF-C4 | **ILIKE wildcard not escaped in assembler** — user message tokens match unintended listings | `app/pipeline/assembler.py:224` | Performance degradation + incorrect listing matches |

### High

| ID | Issue | Impact |
|----|-------|--------|
| PERF-H1 | Dispatcher makes 4-5 sequential sync DB queries per message + Twilio does 3 more = ~8-10 per message | ~50-100ms DB I/O per message |
| PERF-H2 | `_maybe_append_feedback_prompt` fires DB UPDATE on every response (only needed every 10th) | 90% unnecessary writes |
| PERF-H3 | Double usage metric tracking — 3-4 UPSERTs per message where 1 suffices | Lock contention on `usage_metrics` |
| PERF-H4 | Agent portal contacts list loads ALL contacts — no pagination | OOM for agents with 1000+ contacts |
| PERF-H5 | Agent portal conversation detail loads ALL messages — no limit | OOM for long conversations |
| PERF-H6 | Correlated subquery per conversation row in agent portal (vs LATERAL JOIN in mobile API) | O(N) subqueries |
| PERF-H7 | `analyze_contact_gaps` loads all contacts with `SELECT *` then filters in Python | High memory, wasted bandwidth |

### Architecture Bottlenecks

1. **Synchronous pipeline design** — entire message processing runs in `asyncio.to_thread()`, tying up thread + sync DB connection for LLM call duration. Needs async pipeline or much larger thread pool.
2. **Single-connection DB pattern in console** — multiple independent queries serialized on one async connection (vs mobile briefing which correctly uses `asyncio.gather()` with separate connections).
3. **No connection pooling for Twilio/Firebase** — synchronous HTTP calls create TCP connections per call.

### Positive Performance Findings

- Dual DB pool architecture (sync for workers, async for FastAPI) with process-type-aware sizing
- Redis caching is fail-safe (catches exceptions, falls through to DB)
- `FOR UPDATE SKIP LOCKED` in trigger worker prevents double-firing
- Conversation summarization dedup via Redis `SET NX EX`
- Token budget management in context assembler
- Mobile briefing correctly parallelizes 6 queries via `asyncio.gather()`
- Consumer group pattern for Redis Streams (XREADGROUP + DLQ)
- Well-chosen indexes covering key query patterns

---

## 3. Architecture Audit

### Top Structural Issues

| ID | Issue | Impact |
|----|-------|--------|
| ARCH-1 | **Pipeline orchestration copy-pasted 3 times** in webhooks.py (SMS, voice, email each have ~50 identical lines) | Maintenance risk — changes must be made in 3 places |
| ARCH-2 | **Three separate Redis client creation patterns** across redis_pool.py, agent_config.py, dependencies.py, and ad-hoc calls in health.py and console_queries.py | Connection leak risk, inconsistent configuration |
| ARCH-3 | **Three god-modules** need splitting: console_queries.py (1,694 LOC), console.py (1,359 LOC), agent_portal.py (937 LOC) | Hard to test, hard to maintain, high coupling |
| ARCH-4 | Error handling inconsistency — bare `except:` in 183 locations across 39 files | Silent failure masking, debugging difficulty |
| ARCH-5 | Sync/async duplication — ~60 functions have both sync and async variants | 700+ lines of duplicated code |

### Positive Architecture Decisions

- Pipeline stage design (normalize → classify → assemble → handle → dispatch) — clean separation of concerns
- RLS tenant isolation at the database layer — defense in depth
- Redis Streams with consumer groups and DLQ — production-grade message processing
- SKIP LOCKED trigger processing — prevents race conditions
- Fail-safe caching — availability over consistency (appropriate for this use case)
- Model tiering (Haiku/Sonnet) with cost tracking per agent/day
- TCPA compliance pipeline — consent checking before automated messages

---

## 4. Test Coverage Gap Analysis

### Summary Statistics

- **Source modules:** 82
- **Fully tested:** 25 | **Partially tested:** 22 | **Minimally tested:** 10 | **Untested:** 17
- **Endpoints:** 97 total, 52 tested (54%), 45 untested (46%)
- **Test functions:** 652 total

### Critical Gaps (ranked by risk)

| Priority | Module | LOC | Routes | Tests | Risk |
|----------|--------|-----|--------|-------|------|
| 1 | `app/api/agent_portal.py` | 937 | 20 | 0 functional | Agent data exposure, unintended messages |
| 2 | `app/api/console_auth.py` | 350 | — | Indirect only | Auth bypass, rate limit regression |
| 3 | `app/worker/message_consumer.py` | 183 | — | 0 | Dropped/duplicated messages |
| 4 | `app/services/twilio_service.py` | 121 | — | 0 | Silent message loss |
| 5 | `app/services/billing_service.py` | 419 | — | Minimal | Financial errors |
| 6 | `app/services/firebase_service.py` | 341 | — | Minimal | Missed push notifications |
| 7 | `app/api/onboarding.py` | 154 | 2 | 0 | Agent provisioning corruption |
| 8 | `app/tools/lead_scoring.py` | 264 | — | 0 | Bad lead prioritization |
| 9 | `app/tools/drip_campaigns.py` | 204 | — | 0 | TCPA compliance risk |
| 10 | `app/pipeline/dispatcher.py` (core fns) | 416 | — | Partial | Side-effect functions untested |

### What's Tested Well

- Mobile API (auth, contacts, conversations, briefing, devices) — comprehensive
- Pipeline stages (normalizer, classifier, resolver, consent) — good
- Console queries — extensive
- Tools (contacts, listings, triggers, seller, sql_utils, transactions) — good
- Cache service — thorough including error paths

---

## 5. API Documentation Audit

### Summary

- **Total endpoints in code:** 103 (including WebSocket)
- **Documented in openapi.yaml:** 81
- **Missing from docs:** 22 (16 mobile API, 4 console tabs, 2 console docs)
- **Inaccurate docs:** 4
- **Stale docs:** 0

### Critical Gaps

1. **Entire Mobile API undocumented** — 16 REST endpoints + 1 WebSocket, all with Pydantic request/response models. These are the only true JSON API endpoints and will be consumed by the mobile app.
2. **JWT Bearer security scheme missing** from YAML security definitions.
3. **SendGrid email webhook auth undocumented** — uses Basic Auth, not mentioned in YAML.
4. **Console login schema inaccurate** — missing `email` field for per-user auth.

---

## 6. Cross-Cutting Findings

Issues that appeared in multiple audit categories:

| Issue | Security | Performance | Architecture | Tests |
|-------|----------|-------------|--------------|-------|
| ILIKE wildcard injection (7 locations) | SEC-M1 | PERF-C4 | — | — |
| Duplicate Redis clients | — | PERF-C3 | ARCH-2 | — |
| Agent portal god-module | — | PERF-H4/H5/H6 | ARCH-3 | Gap #1 |
| Sync/async duplication | — | PERF-C1/C2 | ARCH-5 | — |
| Missing agent_id scoping | SEC-H2/H3 | — | — | — |
| Bare except blocks (183) | — | — | ARCH-4 | — |

---

## 7. Recommended Priority Order

### Immediate (this week)

1. **SEC-C1, SEC-C2:** Fix XSS in conversation deep-link and agent portal reply — `html.escape()` calls
2. **SEC-C3:** Add authentication to onboarding endpoint
3. **SEC-H1:** Add Twilio signature validation to status, voice, voice-fallback endpoints
4. **SEC-H2, SEC-H3:** Add `agent_id` scoping to `update_contact()` and `_sync_contact_lifecycle()`

### Short-term (next 2 weeks)

5. **SEC-H4:** Rate limit agent portal login
6. **SEC-H5:** Auth-gate `/health/metrics`
7. **PERF-C3:** Consolidate Redis client instances
8. **SEC-M1 / PERF-C4:** Escape ILIKE wildcards across all 7 locations
9. Write tests for agent_portal.py (Gap #1) and console_auth.py (Gap #2)

### Medium-term (next 30 days)

10. Write tests for message_consumer.py, twilio_service.py, billing_service.py
11. Document entire Mobile API in openapi.yaml
12. Refactor pipeline orchestration (ARCH-1 — extract shared function)
13. Consolidate Redis client patterns (ARCH-2)
14. Address PERF-H1 through H7 (DB query optimizations, pagination)

### Ongoing

15. Continue tech debt backlog execution (30 stories across 7 phases, ~104 days)
16. Eliminate bare except blocks (ARCH-4 — 183 locations)
17. Split god-modules (ARCH-3 — console_queries, console, agent_portal)

---

*This audit should be treated as a living document. Findings should be cross-referenced with the technical debt backlog (`docs/technical-debt-backlog-final.md`) to avoid duplicate story creation. Many findings here overlap with existing backlog stories (S-1 through S-7 for security, P-1 through P-6 for performance, etc.).*

*— Solomon, Chief of Staff, synthesizing 5 parallel Atlas audit reports*
