# Calloway Code Review Process

**Effective:** 2026-03-15
**Owner:** Atlas (Engineering Lead)
**Applies to:** All code changes committed to the Calloway repository

---

## 1. Review Process

### Who Reviews

Every implementation is reviewed by a **separate** @eng agent — never the same agent that wrote the code. Solomon (Chief of Staff) enforces this separation and will not commit code until a review agent has approved it.

### Step-by-Step Flow

1. **Implementation agent completes work** on a working branch, including tests.
2. **Implementation agent runs pre-commit checks:**
   - `ast.parse()` on all modified `.py` files (syntax validation).
   - `pytest` on affected test files (existing tests must pass).
3. **Solomon dispatches a separate @eng review agent** with:
   - The full diff (`git diff` output).
   - The relevant user stories and acceptance criteria.
   - This review process document as context.
4. **Review agent evaluates the diff** against the checklist below and produces a structured review using the template in Section 6.
5. **Blocking issues must be resolved** before commit. The implementation agent addresses feedback and the reviewer re-evaluates changed sections.
6. **Solomon commits and pushes** only after the reviewer marks the change as "Approved" or "Approved with Non-Blocking Notes."

### Review Scope

- **Full review required:** Any change that adds or modifies application code, tests, database schema, configuration, or infrastructure.
- **Abbreviated review (checklist spot-check):** Documentation-only changes, dependency version bumps with no code changes, OpenAPI spec updates that mirror existing code.
- **No review required:** PR notes (`docs/pr-notes/`), audit documents, project plans.

---

## 2. Review Checklist

Every review must evaluate the following categories. Check each item or explicitly note why it does not apply.

### Security

- [ ] **Parameterized queries only.** No f-strings, no string concatenation in SQL. All user input goes through `%s` placeholders.
- [ ] **ILIKE wildcards escaped.** Any `ILIKE` or `LIKE` query escapes `%` and `_` characters in user-supplied input before parameterization. (See anti-pattern SP-1 below.)
- [ ] **Agent ID scoping.** Every database query, API endpoint, and background job is scoped to the authenticated agent. `WHERE agent_id = %s` is present on all tenant-data queries — never trust client-supplied IDs alone.
- [ ] **Input validation at system boundaries.** All external input (request bodies, query params, webhook payloads) validated via Pydantic models or explicit checks.
- [ ] **No XSS vectors.** Any user-supplied data rendered in HTML is escaped. No raw f-string interpolation into HTML templates. Jinja2 autoescaping is not disabled.
- [ ] **Webhook signature verification.** Inbound webhooks from Twilio, Stripe, Vapi, and SendGrid verify request signatures before processing.
- [ ] **Secrets in config only.** No hardcoded API keys, signing secrets, or credentials. All secrets sourced from `app/config.py` via environment variables.
- [ ] **Authentication enforced.** New endpoints require authentication. Unauthenticated endpoints are explicitly justified and documented.
- [ ] **Rate limiting on sensitive endpoints.** Login, verification, password reset, and similar endpoints have rate limits.
- [ ] **TCPA compliance preserved.** Changes to messaging flows do not bypass consent checks or revocation handling.

### Performance

- [ ] **Async discipline.** No blocking I/O (Twilio, Firebase, sync DB, `time.sleep()`) called directly in async endpoints or async code paths. Blocking calls wrapped in `loop.run_in_executor()`.
- [ ] **No unbounded queries.** All list/search queries have `LIMIT` clauses or pagination. No `SELECT *` without filtering on large tables.
- [ ] **Connection management.** DB connections are acquired and released promptly. No connection held across LLM calls or external API calls. Each `asyncio.gather()` task acquires its own connection.
- [ ] **Single Redis client pattern.** New code uses the shared Redis pool from `app/services/redis_pool.py` — does not create ad-hoc Redis clients.
- [ ] **No N+1 queries.** List endpoints do not issue per-row subqueries. Use JOINs, LATERAL JOINs, or batch queries.
- [ ] **Efficient writes.** Conditional UPSERTs check whether the write is necessary before executing (e.g., feedback prompt every 10th response, not every response).

### Testing

- [ ] **Tests ship with the code.** Every new endpoint, service function, or tool has tests in the same commit. Tests are not deferred to a separate task.
- [ ] **Three-path coverage.** Each endpoint or public function has at minimum: (1) happy path, (2) error/edge case, (3) auth/security path. Each service calling external APIs covers: success, API error/timeout, and rate limit/retry.
- [ ] **Deterministic tests.** No `time.sleep()`, no real network calls, no clock-dependent assertions. External dependencies (Redis, DB, Twilio, Firebase, Anthropic) are mocked. FastAPI test clients use dependency overrides.
- [ ] **Existing tests still pass.** New code does not break existing tests. Intentional behavior changes update affected tests (not delete them).
- [ ] **Contract-based assertions.** Tests verify inputs, outputs, side effects, and error codes — not internal method call counts or implementation details.

### Code Quality

- [ ] **Type hints on all signatures.** Function parameters and return types are annotated. `str | None` preferred over `Optional[str]`.
- [ ] **Appropriate error responses.** `HTTPException` with correct status codes: 400, 401, 403, 404, 409, 410, 422, 429, 503.
- [ ] **Logging at the right level.** `info` for successful operations, `warning` for degraded states, `error` for data loss or broken flows, `debug` for dev troubleshooting. No secrets, tokens, or full request bodies logged.
- [ ] **Module-level docstrings.** Every new Python file has a one-sentence docstring describing its purpose.
- [ ] **Function/class docstrings.** Public APIs and non-trivial helpers have docstrings.
- [ ] **Inline rationale comments.** Non-obvious design decisions have comments explaining *why*, not *what*. Security trade-offs, compliance requirements, threshold choices, and deliberate deviations from the obvious approach are documented.
- [ ] **No bare excepts.** Exception handlers catch specific exception types, not bare `except:` or `except Exception:` without re-raising or logging. (See anti-pattern CQ-1 below.)
- [ ] **Section headers in long files.** Files over 200 lines use `# --- Section Name ---` comment headers to organize code.

### Architecture

- [ ] **No copy-paste orchestration.** Shared logic is extracted into functions, not duplicated across endpoints (e.g., pipeline orchestration should not be repeated for SMS, voice, and email).
- [ ] **Module boundaries respected.** API routes call services; services call DB. No direct SQL in route handlers. No HTTP response formatting in services.
- [ ] **No god-module growth.** Files over 500 LOC are flagged for discussion. New functionality added to already-large modules (console_queries.py, console.py, agent_portal.py) must justify why it cannot be a separate module.
- [ ] **Consistent patterns.** New code follows the same patterns as existing well-reviewed code (e.g., mobile API patterns for new API endpoints, not agent portal patterns).

---

## 3. Severity Levels

### Blocking (must fix before commit)

Changes that introduce or fail to prevent:

- **Security vulnerabilities:** SQL injection, XSS, missing auth, missing agent_id scoping, unescaped ILIKE wildcards, hardcoded secrets, TCPA compliance violations.
- **Data correctness issues:** Cross-tenant data access, incorrect writes, lost messages, silent data corruption.
- **Production stability risks:** Unbounded queries that can OOM, sync calls blocking async event loop, connection pool exhaustion, missing error handling on critical paths.
- **Missing tests:** No tests shipped with new code. Tests that are not deterministic (real network calls, sleeps). Zero coverage on security-sensitive paths.
- **Contract violations:** Endpoint returns wrong status codes, breaks documented API contract, changes behavior without updating dependent tests.

### Non-Blocking (should fix, but does not hold up commit)

- **Code style issues:** Missing docstrings on internal helpers, suboptimal variable names, section headers not yet added to a growing file.
- **Minor performance notes:** A query that could be slightly more efficient but handles bounded data. A cache that could be added but is not critical.
- **Documentation gaps:** Missing inline rationale comment on a straightforward decision. Docstring could be more detailed.
- **Refactoring suggestions:** "This would be cleaner as a separate module" when the current approach is correct and maintainable.
- **Test enhancements:** "Consider adding a test for this edge case" when the three required paths are already covered.

### Informational (noted for future reference)

- **Tech debt observations:** "This module is approaching the 500 LOC threshold."
- **Pattern suggestions:** "The mobile API handles this differently — consider aligning in a future pass."
- **Cross-cutting concerns:** "This is the third place we handle X; worth a shared utility eventually."

---

## 4. Common Anti-Patterns

These specific anti-patterns have been identified in the Calloway codebase through audit. Reviewers must watch for them in every review.

### SP-1: ILIKE Wildcard Injection

**The problem:** Parameterized queries protect against SQL injection, but `%` and `_` characters in user input are still interpreted as ILIKE wildcards. A user searching for "100%" matches every row.

**What to look for:** Any `ILIKE %s` or `LIKE %s` query where the parameter is user-supplied text.

**The fix:** Escape `%` and `_` in user input before wrapping with wildcards:
```python
escaped = value.replace("%", "\\%").replace("_", "\\_")
pattern = f"%{escaped}%"
cursor.execute("SELECT ... WHERE name ILIKE %s", (pattern,))
```

**Known locations:** 7 search functions across console_queries.py, agent_portal.py, and assembler.py.

### SP-2: Missing Agent ID Scoping

**The problem:** Queries that filter by `contact_id`, `trigger_id`, `listing_id`, or similar without also filtering by `agent_id`. Even though RLS provides a safety net, application-level scoping is defense-in-depth.

**What to look for:** `UPDATE`, `DELETE`, or `SELECT` queries on tenant-scoped tables that use only a record ID without `AND agent_id = %s`.

**Known locations:** `update_contact()` in contacts.py, `_sync_contact_lifecycle()` in transactions.py.

### SP-3: Bare Except Blocks

**The problem:** `except:` or `except Exception:` without logging or re-raising silently swallows errors, making debugging nearly impossible.

**What to look for:** Any `except` clause that does not specify a concrete exception type, or catches `Exception` without logging the error and either re-raising or returning a meaningful response.

**The fix:** Catch specific exceptions. If a broad catch is truly needed (e.g., fail-safe caching), log at `warning` level with the exception details.

**Known scope:** 183 bare except blocks across 39 files (audit ARCH-4).

### SP-4: Sync Calls in Async Context

**The problem:** Calling blocking I/O (Twilio API, Firebase, sync psycopg2, `time.sleep()`) directly in an async endpoint or within `asyncio.gather()` blocks the event loop and kills concurrency.

**What to look for:**
- `time.sleep()` anywhere in async code paths.
- Sync HTTP client calls (requests, httpx sync) in async functions.
- Sync database connections used inside async route handlers without `run_in_executor()`.
- `asyncio.gather()` tasks that share a single DB connection instead of each acquiring their own.

**Known locations:** Anthropic API calls in anthropic_service.py use sync client with `time.sleep()` for rate limit retry. Pipeline holds sync DB connection across LLM calls (5-45 seconds).

### SP-5: Copy-Paste Orchestration

**The problem:** The same sequence of pipeline steps (normalize, classify, assemble, handle, dispatch) duplicated across multiple webhook handlers instead of extracted into a shared function.

**What to look for:** Near-identical code blocks (10+ lines) appearing in multiple functions within the same file or across files.

**Known locations:** SMS, voice, and email handlers in webhooks.py each contain ~50 identical lines of pipeline orchestration.

### SP-6: Unbounded List Queries

**The problem:** Queries that return all rows from a table without `LIMIT`, used in list endpoints. Works fine with 10 contacts, causes OOM with 10,000.

**What to look for:** `SELECT ... FROM contacts WHERE agent_id = %s` without `LIMIT` or pagination parameters. Any list endpoint response that returns an array without a `total`/`has_more` indicator.

**Known locations:** Agent portal contacts list, agent portal conversation detail (loads all messages).

### SP-7: Duplicate Redis Client Creation

**The problem:** Creating new Redis client instances outside the shared pool, leading to connection exhaustion and inconsistent configuration.

**What to look for:** `redis.Redis()` or `redis.from_url()` calls anywhere except `app/services/redis_pool.py`. Import of `redis` directly instead of using the pool dependency.

**Known locations:** agent_config.py creates its own unbounded Redis connection pool.

### SP-8: Unauthenticated Endpoints

**The problem:** New endpoints added without authentication, allowing anyone on the internet to invoke them.

**What to look for:** FastAPI route handlers without a dependency that validates session cookies, JWT tokens, or API keys. Particularly dangerous on endpoints that create resources or return tenant data.

**Known locations:** Onboarding endpoint (SEC-C3) allows unauthenticated agent account creation.

---

## 5. Review Boundaries

### What Reviewers Should NOT Do

- **Rewrite the implementation.** The reviewer evaluates correctness and adherence to standards. If the approach is fundamentally wrong, request a redesign — do not provide a complete rewrite in review comments.
- **Enforce personal style preferences.** If the code follows project conventions and is readable, do not request changes for stylistic reasons.
- **Expand scope.** If the diff is correct but adjacent code has issues, note them as Informational — do not block the current change for pre-existing problems.
- **Approve without reading.** Every file in the diff must be read. "LGTM" without specific observations is not an acceptable review.

---

## 6. Review Template

Reviewers must use this exact format for their feedback.

```markdown
# Code Review: [Brief Description of Change]

**Reviewer:** Atlas (@eng)
**Date:** YYYY-MM-DD
**Diff scope:** [files changed / lines added / lines removed]

## Verdict: [APPROVED | APPROVED WITH NON-BLOCKING NOTES | CHANGES REQUESTED]

## Summary

[2-3 sentences: what the change does, whether it achieves its goal, overall assessment.]

## Blocking Issues

[If none, write "None." Otherwise, list each issue:]

### B-1: [Short title]
- **File:** `path/to/file.py:line`
- **Category:** Security | Performance | Testing | Code Quality | Architecture
- **Issue:** [What is wrong]
- **Required fix:** [What must change]

### B-2: ...

## Non-Blocking Notes

[If none, write "None." Otherwise, list each note:]

### NB-1: [Short title]
- **File:** `path/to/file.py:line`
- **Category:** Security | Performance | Testing | Code Quality | Architecture
- **Suggestion:** [What could be improved and why]

### NB-2: ...

## Informational

[Observations for future reference, tech debt notes, pattern alignment suggestions. If none, write "None."]

## Checklist Coverage

| Category | Checked | Notes |
|----------|---------|-------|
| Security | Yes/No/N/A | [Brief note] |
| Performance | Yes/No/N/A | [Brief note] |
| Testing | Yes/No/N/A | [Brief note] |
| Code Quality | Yes/No/N/A | [Brief note] |
| Architecture | Yes/No/N/A | [Brief note] |
```

---

## 7. Review Metrics

Solomon tracks the following to ensure review quality over time:

- **Blocking issues caught per review** — trending toward zero indicates improving implementation quality.
- **Post-commit defects** — issues found after review approval indicate review gaps. Root-cause each one and update this checklist.
- **Anti-patterns recurrence** — if the same anti-pattern appears in 3+ reviews, add it to engineering standards in CLAUDE.md and consider automated linting.
- **Review turnaround** — reviews should not bottleneck implementation. If reviews consistently take longer than implementation, the checklist may need simplification.

---

*This is a living document. When a new anti-pattern is identified in production or audit, add it to Section 4. When a checklist item consistently has zero findings across 10+ reviews, consider whether it can be enforced by automated tooling instead.*
