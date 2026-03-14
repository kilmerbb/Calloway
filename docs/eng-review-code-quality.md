# Engineering Review: Code Quality & Standards (B-1, B-2, B-3, B-5, B-6, B-7, E-1, E-2, E-3, E-4)

**Reviewer:** Atlas (Engineering Lead)
**Date:** 2026-03-14
**Status:** Review Complete

---

### B-1: Dependency Injection for Services

**PM Story:** Refactor module-level singletons to FastAPI `Depends()` so tests can swap mocks and service lifecycle is framework-managed.
**PM Effort:** XL

**Engineering Specification:**

- **Files to modify:**
  - `app/services/anthropic_service.py` (lines 281-288) — singleton `_client` + `get_anthropic_client()`
  - `app/services/redis_pool.py` (lines 6-19) — singleton `_pool` + `get_redis_pool()`
  - `app/services/embedding_service.py` (line 181+) — singleton `_service` + `get_embedding_service()`
  - `app/services/rag_service.py` (line 393+) — singleton `_service` + `get_rag_service()`
  - `app/services/twilio_service.py` (line 15+) — singleton `_client` + `get_twilio_client()`
  - `app/services/agent_config.py` (line 15+) — singleton `_redis_client` + `get_redis_client()`
  - `app/services/firebase_service.py` (line 31+) — singleton `_firebase_app`
  - `app/db/connection.py` (lines 38, 57, 85, 104) — 4 global pool singletons
  - `app/dependencies.py` (all) — already has `get_db()` and `get_redis()` stubs but they are unused wrappers, not real DI
  - `app/main.py` — lifespan init; services would register here
  - Every route file that calls `get_anthropic_client()`, `get_twilio_client()`, etc. directly (at least 10+ files across `app/api/`, `app/pipeline/`)
  - `app/worker/trigger_worker.py`, `app/worker/daily_scanner.py` — background workers outside request context

- **Implementation approach:**
  1. Create `app/services/container.py` with provider functions: `get_anthropic_service()`, `get_twilio_service()`, etc., each returning the service instance. These become FastAPI `Depends()` targets.
  2. Keep existing `get_*()` factory functions as compatibility shims that call the DI providers — enables incremental migration.
  3. For route handlers: add service params via `Depends()`. Migrate one router at a time, starting with `console.py` (highest call count).
  4. For workers/pipeline code that runs outside request context: use a `ServiceRegistry` class instantiated at startup and passed explicitly. Do NOT try to make `Depends()` work outside FastAPI context.
  5. Register service initialization in `app/main.py` lifespan so pools are created once and shared.

- **Database changes:** None
- **New dependencies:** None (FastAPI's DI system is built-in)
- **LOC estimate:** ~400 lines changed, ~150 new (container module + shims). Touches 20+ files.
- **Risk notes:**
  - The 11 global singletons are imported by name across 40+ modules. Mass refactor of import paths is the real work.
  - Workers (`trigger_worker.py`, `daily_scanner.py`) use sync DB connections outside any FastAPI request. These need a separate initialization path — the DI container cannot serve them via `Depends()`.
  - Circular imports are a real risk: `anthropic_service` imports `get_db_connection` at function-call time (lazy import at lines 36, 62) specifically to avoid this. DI must preserve this laziness.
  - `app/dependencies.py` already exists with `get_db()` and `get_redis()` but nothing uses them. Consolidate here rather than creating a new file.

- **Revised effort:** XL is correct. This touches nearly every module and needs careful incremental rollout. I'd budget 12-15 days. Do it last in this batch — it's high-risk, low-urgency.

- **Additional acceptance criteria:**
  - Workers must continue functioning without FastAPI request context.
  - No import-time side effects (service instances must not be created on import).
  - `app.dependency_overrides` must work for all 7 service types in test fixtures.

---

### B-2: Eliminate Bare Except Swallowing

**PM Story:** Replace `except Exception` blocks with specific exception types so real bugs aren't silently swallowed.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:** 40 files containing 183 `except Exception` blocks. Top offenders:
  - `app/services/console_queries.py` — 60 instances (most are `except Exception as e: logger.error(...); return []` or `return None`)
  - `app/api/webhooks.py` — 10 instances
  - `app/api/console.py` — 8 instances
  - `app/api/harness.py` — 8 instances
  - `app/services/billing_service.py` — 6 instances
  - `app/services/summarization_service.py` — 6 instances
  - `app/pipeline/dispatcher.py` — 6 instances
  - `app/worker/daily_scanner.py` — 6 instances
  - `app/worker/trigger_worker.py` — 5 instances
  - Remaining 31 files — 1-4 instances each

- **Implementation approach:**
  1. **Triage pass (day 1):** Audit all 183 blocks. Categorize each as:
     - **(a) Reraise** — catch was hiding real bugs (e.g., logic errors in pipeline)
     - **(b) Narrow** — catch `psycopg.Error` for DB ops, `httpx.HTTPError` for HTTP, `anthropic.APIError` for LLM, `json.JSONDecodeError` for parsing, `redis.RedisError` for cache
     - **(c) Intentional** — webhook handlers that must return 200 to prevent Twilio retries, worker main loops that must not crash. Add `# noqa: BLE001` with justification comment.
  2. **Refactor pass (days 2-4):** Apply changes file by file. For category (b), the most common pattern is DB calls — replace `except Exception` with `except psycopg.Error` in all `console_queries.py` functions (60 instances, mechanical change).
  3. **Lint rule:** Add `flake8-bugbear` or `ruff` rule `BLE001` (blind exception) to `pyproject.toml`.

- **Database changes:** None
- **New dependencies:** `ruff` (linter, if not already present) or `flake8-bugbear`
- **LOC estimate:** ~200 lines changed across 40 files. Mostly changing `Exception` to specific types.
- **Risk notes:**
  - `console_queries.py` has 60 bare excepts. Changing all to `psycopg.Error` is safe but tedious. The duplicated sync/async paths (A-5) mean you'd do this work twice — **do B-2 after A-5** to avoid double work.
  - Webhook handlers (`webhooks.py` lines 73, 112, 129, etc.) genuinely need broad catches to prevent Twilio 500 retries. These are category (c).
  - Worker main loops (e.g., `trigger_worker.py` line 29) are intentional — a crash kills the entire worker process. Category (c).

- **Revised effort:** M is correct, but conditional on A-5 (sync/async consolidation). If done before A-5, effort jumps to L because you're touching 60 blocks in console_queries that will be deleted during A-5.

- **Additional acceptance criteria:**
  - Every category (c) block has a comment explaining why the broad catch is intentional.
  - CI lint rule is green on merge.
  - No change in observable behavior for webhook endpoints (they must still return 200 on internal errors).

---

### B-3: Structured Return Types with Type Hints

**PM Story:** Add return type annotations using Pydantic models or TypedDicts to the top public functions, and configure mypy.
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - 131 functions across 23 files currently lack return type annotations entirely (no `->` in signature).
  - Worst offenders: `app/api/console.py` (40 unannotated), `app/api/agent_portal.py` (21), `app/api/harness.py` (15), `app/api/webhooks.py` (14).
  - `app/services/console_queries.py` — 38 functions have `-> dict` or `-> list` (not `-> None`) but return untyped dicts. These need TypedDict or Pydantic model replacements.
  - New file: `app/models/responses.py` — TypedDict definitions for console query return shapes.
  - `pyproject.toml` — mypy configuration.

- **Implementation approach:**
  1. Create `app/models/responses.py` with TypedDict definitions for the most-returned shapes: `AgentSummary`, `ConversationRow`, `TriggerRow`, `HealthOverview`, `SystemPulse`, etc. Start with the 10 most-called console query functions.
  2. Annotate route handlers in `console.py` and `agent_portal.py` — these are FastAPI routes, so return types also affect OpenAPI docs. Use `HTMLResponse` or `dict[str, Any]` as appropriate.
  3. Add `[tool.mypy]` config to `pyproject.toml` with `strict = false`, `check_untyped_defs = false` initially (incremental adoption). Enable per-module overrides for annotated files.
  4. Prioritize the 20 most-imported functions first (console_queries, anthropic_service, agent_config).

- **Database changes:** None
- **New dependencies:** `mypy` (dev dependency), `types-redis`, `types-psycopg2` (type stubs)
- **LOC estimate:** ~300 lines new (TypedDict definitions), ~150 lines changed (annotations on existing functions), ~20 lines config.
- **Risk notes:**
  - Many `console_queries.py` functions return `dict | None` where the dict shape varies by code path. Defining stable TypedDicts requires reading every return statement carefully.
  - FastAPI route handlers that return `templates.TemplateResponse(...)` don't benefit from return type annotations for API doc purposes — only useful for internal type checking.
  - Running mypy in strict mode on this codebase would produce thousands of errors. Must be incremental with per-file opt-in.

- **Revised effort:** L is correct. The TypedDict creation for ~30 console query functions is the bulk of the work. 5-8 days.

- **Additional acceptance criteria:**
  - `mypy` passes with zero errors on newly annotated files (can exclude legacy files).
  - TypedDicts match actual returned dict keys (verified by running existing tests).
  - A `py.typed` marker file exists for downstream consumers.

---

### B-5: Configurable Model Names

**PM Story:** Make Claude model IDs environment-configurable so model upgrades don't require code deploys.
**PM Effort:** S

**Engineering Specification:**

- **Files to modify:**
  - `app/config.py` (line 27 area) — add `CLAUDE_HAIKU_MODEL` and `CLAUDE_SONNET_MODEL` to `Settings` class with defaults.
  - `app/services/anthropic_service.py` (lines 15-22) — replace hardcoded `HAIKU_MODEL = "claude-haiku-4-5-20251001"` and `SONNET_MODEL = "claude-sonnet-4-5-20241022"` with reads from settings. Also update `MODEL_COSTS` dict keys.
  - `app/services/summarization_service.py` (lines 22, 314, 370, 408) — imports `HAIKU_MODEL` from anthropic_service. Update these references.

- **Implementation approach:**
  1. Add to `Settings` in `config.py`:
     ```python
     CLAUDE_HAIKU_MODEL: str = "claude-haiku-4-5-20251001"
     CLAUDE_SONNET_MODEL: str = "claude-sonnet-4-5-20241022"
     ```
  2. In `anthropic_service.py`, change lines 15-16 to read from `get_settings()` at init time (in `__init__`, not module level, since settings may not be loaded yet at import time). Store as `self.haiku_model` and `self.sonnet_model`.
  3. `MODEL_COSTS` needs to become a method or instance-level dict keyed by the configured model names. Alternatively, key by tier ("haiku"/"sonnet") instead of model ID — more robust.
  4. Update `summarization_service.py` to accept model name as parameter or read from settings directly.

- **Database changes:** None
- **New dependencies:** None
- **LOC estimate:** ~30 lines changed, ~10 new.
- **Risk notes:**
  - `MODEL_COSTS` is keyed by model string. If the configured model name doesn't match a cost entry, cost tracking silently falls back to Haiku costs (line 38). This is fine as a default but should log a warning.
  - Model names change Anthropic's pricing. When you change model via env var, cost tracking may be wrong. Consider making cost-per-token configurable too, or fetching from a config map.
  - Module-level constants `HAIKU_MODEL` and `SONNET_MODEL` are imported by name in `summarization_service.py`. After refactoring to instance vars, these imports break. Need to export the defaults or refactor the import.

- **Revised effort:** S is correct. Half a day to a day. Straightforward.

- **Additional acceptance criteria:**
  - Log the configured model names at startup (INFO level) so operators can verify.
  - If a configured model ID fails on first API call, the error log includes the model ID string.

---

### B-6: Correct Monthly Recurrence with relativedelta

**PM Story:** Replace `timedelta(days=30)` with `relativedelta(months=1)` for monthly trigger recurrence.
**PM Effort:** XS

**Engineering Specification:**

- **Files to modify:**
  - `app/worker/trigger_worker.py` line 200: `next_at = trigger.scheduled_at + timedelta(days=30)` -> `next_at = trigger.scheduled_at + relativedelta(months=1)`
  - `app/worker/trigger_worker.py` line 4: add `from dateutil.relativedelta import relativedelta` import.

- **Implementation approach:**
  1. Add import at line 4.
  2. Change line 200 from `timedelta(days=30)` to `relativedelta(months=1)`.
  3. `python-dateutil` is already in `requirements.txt` (line 24: `python-dateutil==2.9.0`). No new dependency needed.
  4. Consider a one-time migration query to fix drifted `next_fire_at` values for existing monthly triggers. This is OQ-7 from the backlog — flag for PM decision.

- **Database changes:** Optional one-time data fix for drifted triggers (depends on OQ-7 answer).
- **New dependencies:** None (`python-dateutil` already present).
- **LOC estimate:** 2 lines changed, 1 line added.
- **Risk notes:**
  - Zero risk. `relativedelta(months=1)` from `dateutil` is well-tested and handles month-end edge cases correctly (Jan 31 + 1 month = Feb 28).
  - Existing triggers that have already drifted by 1-2 days will self-correct on next fire (the new recurrence calculation uses the trigger's `scheduled_at`, not the current time).

- **Revised effort:** XS is correct. 15 minutes of coding, 30 minutes of testing.

- **Additional acceptance criteria:**
  - Unit test: Jan 31 + monthly = Feb 28 (non-leap), Feb 29 (leap year).
  - Unit test: regular month (e.g., Mar 15 + monthly = Apr 15).

---

### B-7: Correct Annual Recurrence with relativedelta

**PM Story:** Replace `timedelta(days=365)` with `relativedelta(years=1)` for annual trigger recurrence.
**PM Effort:** XS

**Engineering Specification:**

- **Files to modify:**
  - `app/worker/trigger_worker.py` line 198: `next_at = trigger.scheduled_at + timedelta(days=365)` -> `next_at = trigger.scheduled_at + relativedelta(years=1)`
  - Import already added in B-6.

- **Implementation approach:**
  1. Change line 198 from `timedelta(days=365)` to `relativedelta(years=1)`.
  2. This is a one-line change if B-6 is done first (import already present).

- **Database changes:** Same optional data fix as B-6 for annual triggers.
- **New dependencies:** None (covered by B-6).
- **LOC estimate:** 1 line changed.
- **Risk notes:**
  - Zero risk. Same pattern as B-6.
  - Annual triggers that fired on Feb 29 in a leap year: `relativedelta(years=1)` correctly produces Feb 28 for the next year. The existing `timedelta(days=365)` produces Mar 1 in a leap year (366-day year), which is wrong.

- **Revised effort:** XS is correct. Do in same PR as B-6.

- **Additional acceptance criteria:**
  - Unit test: Feb 29 2024 (leap) + 1 year = Feb 28 2025.
  - Unit test: Mar 1 + 1 year = Mar 1.

---

### E-1: Pydantic v2 Migration Patterns

**PM Story:** Migrate any remaining Pydantic v1 patterns to v2 equivalents. Eliminate deprecation warnings.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - `app/config.py` — already uses `model_config` dict (line 65). Clean.
  - `app/models/schemas.py` — 15 models, all using `BaseModel` with v2-style `Field()`. No `class Config:`, no `validator()`, no `.dict()`. **Already v2-compliant.**
  - Codebase-wide search for v1 patterns (`class Config:`, `validator`, `schema_extra`, `.dict()`, `.json()`) found **zero matches**.

- **Implementation approach:**
  - The codebase is already on Pydantic v2 (`pydantic==2.10.6` in requirements.txt) and uses v2 patterns throughout. No migration is needed.
  - Only action: verify no deprecation warnings at runtime by running the test suite with `-W error::DeprecationWarning` and checking for `PydanticDeprecatedSince20`.

- **Database changes:** None
- **New dependencies:** None
- **LOC estimate:** 0 lines changed (already done).
- **Risk notes:** None. This story is already complete.

- **Revised effort:** ~~M~~ -> **XS (or skip entirely)**. The codebase already uses v2 patterns. PM likely wrote this story based on the audit flagging Pydantic usage without checking that migration had already happened. Recommend closing as "already resolved" after a confirmation test run.

- **Additional acceptance criteria:**
  - Run `pytest -W error::DeprecationWarning` and confirm zero Pydantic deprecation warnings.

---

### E-2: Template Component Organization

**PM Story:** Reorganize Jinja2 templates from flat files into `layouts/`, `pages/`, `components/`, `partials/` structure.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - 40 template files across 3 existing directories:
    - `app/templates/console/` — 17 files (pages + 1 `base.html` + `partials/` subdir with 4 files)
    - `app/templates/agent/` — 12 files (pages + 1 `base.html`)
    - `app/templates/harness/` — 7 files
  - All route handlers in `app/api/console.py`, `app/api/agent_portal.py`, `app/api/harness.py` that reference template paths in `templates.TemplateResponse()`.
  - `app/main.py` (line 110-111) — static file mount is fine, templates use Jinja2 loader which handles subdirs.

- **Implementation approach:**
  1. Proposed structure:
     ```
     app/templates/
       layouts/
         console-base.html (from console/base.html)
         agent-base.html (from agent/base.html)
       pages/
         console/ (dashboard.html, tenants.html, ...)
         agent/ (dashboard.html, contacts.html, ...)
         harness/ (composer.html, history.html, ...)
       components/
         agent-card.html, metric-card.html, etc. (extract from pages)
       partials/
         console/ (existing 4 partials + new HTMX fragments)
         agent/ (extract HTMX swap targets from pages)
     ```
  2. Update all `TemplateResponse` calls to use new paths. This is ~60 references across 3 route files.
  3. Update all `{% extends %}` and `{% include %}` references in templates.
  4. Extract repeated UI patterns (stat cards, conversation thread, trigger rows) into `components/`.

- **Database changes:** None
- **New dependencies:** None
- **LOC estimate:** 0 lines of logic changed. ~60 template path string updates in Python. ~40 template files moved/renamed. ~20 new component extractions.
- **Risk notes:**
  - Console already has a `partials/` subdir — it's partially organized. The reorganization is additive, not a full rewrite.
  - Every template path change must be updated in both the Python route handler AND the `{% extends %}` / `{% include %}` directives. Missing one produces a 500 error.
  - HTMX `hx-get` attributes in templates reference route paths, not template paths, so those are unaffected.
  - Must update all at once (atomic rename) or use symlinks during transition. Partial migration = broken pages.

- **Revised effort:** M is correct. 3-4 days. The work is mechanical but high-surface-area.

- **Additional acceptance criteria:**
  - Every page loads without 500 errors after reorganization (manual smoke test or automated template rendering test).
  - No orphaned template files in old locations.
  - `{% include %}` and `{% extends %}` paths are all relative to the template root, not using `../`.

---

### E-3: CSS Design Token System

**PM Story:** Create CSS custom properties for all visual values and replace hardcoded colors/spacing with token references.
**PM Effort:** M

**Engineering Specification:**

- **Files to modify:**
  - `app/static/console/style.css` (1,027 lines) — has `:root` block with 11 tokens (lines 2-16: `--bg`, `--bg-card`, `--border`, `--text`, `--accent`, etc.) and 134 `var(--...)` usages. But 19 hardcoded hex colors remain, plus no spacing/typography tokens.
  - `app/static/agent/style.css` (1,226 lines) — already has a comprehensive token system (lines 7-90: spacing, radius, shadow, color tokens). 327 `var(--...)` usages vs 39 hardcoded hex values.

- **Implementation approach:**
  1. **Console CSS (primary work):** Expand the `:root` token block from 11 to ~30 tokens. Add spacing tokens (`--space-*`), typography tokens (`--font-size-*`, `--font-weight-*`, `--line-height-*`), radius tokens (`--radius-*`). Replace the 19 remaining hardcoded hex colors with token references.
  2. **Agent CSS (cleanup):** Replace the remaining 39 hardcoded hex values with existing token references. Most are likely in edge-case selectors or pseudo-elements that were missed.
  3. **Shared tokens file:** Create `app/static/shared/tokens.css` with the base token definitions. Import from both console and agent stylesheets. This enables future theming.
  4. Mirror the agent CSS token structure (which is already well-organized) for the console CSS.

- **Database changes:** None
- **New dependencies:** None
- **LOC estimate:** ~80 lines new (expanded token definitions for console), ~60 lines changed (replacing hardcoded values). Agent CSS: ~40 lines changed.
- **Risk notes:**
  - Agent CSS is already 80% there — it has a full design token system. The PM story was written as if neither CSS had tokens. **The real work is console CSS only.**
  - CSS specificity issues when replacing `color: #333` with `color: var(--border)` — the semantic meaning must match. Need to visually verify each replacement.
  - No build pipeline for CSS — changes are live on save. No risk of build failures, but no minification either.

- **Revised effort:** ~~M~~ -> **S**. Agent CSS already has tokens. Console CSS needs ~20 hardcoded values replaced and a token block expansion. This is 1-2 days, not 3-5.

- **Additional acceptance criteria:**
  - Zero hardcoded hex color values in either CSS file (all use `var(--...)`).
  - Shared tokens file imported by both stylesheets.
  - Console and agent token names are consistent (same `--space-*`, `--radius-*` naming scheme).

---

### E-4: Accessibility Basics (ARIA, Focus Management)

**PM Story:** Add WCAG 2.1 AA basics: ARIA labels, focus trapping in modals, logical tab order, aria-live for HTMX regions.
**PM Effort:** L

**Engineering Specification:**

- **Files to modify:**
  - `app/templates/console/base.html` — already has good a11y foundations: `<a href="#main-content" class="skip-nav">`, `role="navigation"`, `aria-label="Main navigation"`, `aria-current="page"`, `aria-hidden="true"` on decorative icons. This is better than the PM assumed.
  - All 40 template files — audit for missing labels, roles, and live regions.
  - Currently: 8 `aria-live` or `role="alert"` usages across 7 templates. Need more for HTMX swap regions.
  - `app/static/console/style.css` — add focus-visible styles, skip-nav styles (may already exist).
  - `app/static/agent/style.css` — same.
  - New: `app/static/shared/a11y.js` — focus trap utility for modals, HTMX `afterSwap` event handler for aria-live announcements.

- **Implementation approach:**
  1. **Audit (day 1):** Run `axe-core` or `pa11y` against each console page. Log all violations. Current state is better than typical — skip-nav, ARIA roles, and aria-current are already present.
  2. **ARIA labels (day 2):** Add `aria-label` to any unlabeled interactive elements (form inputs, icon-only buttons). Add `aria-labelledby` to modal dialogs.
  3. **Focus management (day 3):** Create a lightweight focus-trap utility (or use `focus-trap` npm library inlined, ~3KB). Apply to any modal/dialog patterns. Add HTMX `afterSwap` handler to move focus to updated content.
  4. **aria-live regions (day 4):** Add `aria-live="polite"` to all HTMX swap targets (elements with `hx-target` or `id` values referenced by `hx-swap`). This announces dynamic content changes to screen readers.
  5. **Tab order (day 5):** Verify logical tab order. Remove any `tabindex` values > 0. Ensure no focus traps outside modals.
  6. **Color contrast:** Verify token colors from E-3 meet 4.5:1 ratio. Console dark theme (`#B3B3B3` on `#121212` = 9.7:1, passes; `#A7A7A7` on `#121212` = 8.2:1, passes; `#1ED760` on `#121212` = 8.0:1, passes).

- **Database changes:** None
- **New dependencies:** None (custom focus-trap is ~30 lines of JS). Optionally `pa11y` as a dev dependency for CI.
- **LOC estimate:** ~150 lines across templates (ARIA attributes), ~50 lines CSS (focus styles), ~50 lines JS (focus trap + HTMX handler).
- **Risk notes:**
  - The console base template already has solid a11y foundations. This is less work than the PM estimated.
  - HTMX's dynamic swaps are the biggest a11y gap. The `htmx:afterSwap` event is the hook for focus management, but it fires for every swap — need to be selective.
  - Focus-trap in modals can break if HTMX replaces modal content mid-focus. Need to re-trap after swap.
  - E-4 depends on E-2 (template organization) — if templates move during E-2, ARIA changes need to target the final file locations.

- **Revised effort:** ~~L~~ -> **M**. The base template already has skip-nav, ARIA roles, and aria-current. The remaining work is auditing individual pages and adding live regions for HTMX. 3-4 days, not 5-8.

- **Additional acceptance criteria:**
  - `pa11y` or `axe-core` scan of all console pages reports zero critical/serious violations.
  - Keyboard-only navigation test: can reach all interactive elements via Tab.
  - Screen reader test (VoiceOver or NVDA): HTMX swaps announce new content.

---

## Engineering Notes

### Priority/Effort Disagreements

| Story | PM Effort | Revised | Reason |
|-------|-----------|---------|--------|
| E-1 | M | **XS / Skip** | Codebase already uses Pydantic v2 patterns. Zero v1 patterns found. Just needs a confirmation test run. |
| E-3 | M | **S** | Agent CSS already has a comprehensive token system. Console CSS has 11 tokens + 19 hardcoded values to fix. 1-2 days, not 3-5. |
| E-4 | L | **M** | Console base template already has skip-nav, ARIA roles, aria-current. Better foundation than assumed. 3-4 days. |

### Stories to Combine

- **B-6 + B-7** should be a single PR. They're on the same file, same function (`_create_next_recurrence`), same import. One PR, one review, one deploy. Combined effort: XS (30 minutes).

### Stories to Sequence / Reorder

1. **B-6 + B-7 first.** Active bug causing trigger drift. XS effort, P1 priority. Ship today.
2. **B-5 next.** Quick config win, no dependencies, S effort.
3. **E-1: verify and close.** Run `pytest -W error::DeprecationWarning`, confirm clean, close the story.
4. **E-3 before E-4.** E-4 depends on E-3's token colors for contrast verification.
5. **E-2 before E-4.** E-4 depends on E-2's final template locations.
6. **B-2 after A-5.** Don't narrow 60 bare excepts in `console_queries.py` just to delete them in A-5's sync/async consolidation. If A-5 is not imminent, do B-2's non-console-queries files first (123 instances across 39 other files) and defer the console_queries cleanup.
7. **B-3 after B-2.** Adding type annotations is easier once exception types are explicit (return types depend on which exceptions are caught).
8. **B-1 last.** XL effort, touches everything, highest regression risk. Do after all other code quality work is stable.

### Recommended Implementation Order

```
Week 1:  B-6+B-7 (XS) -> B-5 (S) -> E-1 verify (XS) -> E-3 (S)
Week 2:  E-2 (M)
Week 3:  E-4 (M, depends on E-2 + E-3)
Week 4:  B-2 non-console files (S portion)
Week 5:  B-3 (L)
Week 8+: B-1 (XL, after A-5 consolidation)
```

Total revised estimate for this batch: ~25-30 days (vs PM's ~43 days). Primary savings from E-1 being already done and E-3/E-4 being smaller than estimated.
