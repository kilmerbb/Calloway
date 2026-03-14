# Calloway Engineering Standards & Patterns Guide

**Owner:** Atlas, Engineering Lead
**Last Updated:** 2026-03-14
**Status:** Authoritative — all new code MUST follow these standards

---

## Table of Contents

1. [Python / FastAPI Standards](#1-python--fastapi-standards)
2. [Database / PostgreSQL Standards](#2-database--postgresql-standards)
3. [Frontend / HTMX Standards](#3-frontend--htmx-standards)
4. [Security Standards](#4-security-standards)
5. [Testing Standards](#5-testing-standards)
6. [API Standards](#6-api-standards)
7. [Code Organization](#7-code-organization)
8. [Anthropic Claude API Standards](#8-anthropic-claude-api-standards)
9. [Tech Debt Register](#9-tech-debt-register)

---

## 1. Python / FastAPI Standards

### 1.1 Route Organization

Every feature area gets its own `APIRouter` with a prefix and tag. Routers are registered in `app/main.py`.

**REQUIRED pattern:**

```python
# app/api/my_feature.py
from fastapi import APIRouter

router = APIRouter(prefix="/my-feature", tags=["my-feature"])

@router.get("/items")
async def list_items():
    ...
```

```python
# app/main.py
from app.api.my_feature import router as my_feature_router
app.include_router(my_feature_router)
```

**Reference:** `app/api/console.py` line 16 — `router = APIRouter(prefix="/console", tags=["console"])`

**ANTI-PATTERN:** Defining routes directly on the `app` object, or using a single router for unrelated endpoints. Every feature gets its own file and router.

---

### 1.2 Dependency Injection

Use FastAPI's `Depends()` for shared resources (database connections, auth checks, settings). Use `Annotated` types for clarity.

**REQUIRED pattern:**

```python
from typing import Annotated
from fastapi import Depends

from app.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]

@router.get("/items")
async def list_items(settings: SettingsDep):
    ...
```

**ANTI-PATTERN:** Importing and calling `get_settings()` inline inside route handlers. Using module-level global singletons for services that need to be testable.

> **Tech debt:** Current codebase uses module-level `_service` globals with `get_*()` factory functions in `anthropic_service.py`, `rag_service.py`, `embedding_service.py` (audit finding B-1). New code MUST use `Depends()`. Existing code will be migrated.

---

### 1.3 Error Handling

Use structured exception classes. Never use bare `except Exception` with `pass` on data-integrity paths.

**REQUIRED pattern:**

```python
# app/exceptions.py
from fastapi import HTTPException

class CallowayError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, code: str, status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code

class TenantNotFoundError(CallowayError):
    def __init__(self, agent_id: str):
        super().__init__(f"Agent {agent_id} not found", "TENANT_NOT_FOUND", 404)

class ConsentBlockedError(CallowayError):
    def __init__(self, contact_id: str):
        super().__init__(f"No consent for contact {contact_id}", "CONSENT_BLOCKED", 403)
```

Exception handler middleware:

```python
@app.exception_handler(CallowayError)
async def calloway_error_handler(request: Request, exc: CallowayError):
    logger.warning(f"{exc.code}: {exc.message}", extra={"code": exc.code})
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})
```

**Allowed `except Exception` usage:** Non-critical side effects only (notifications, metrics, analytics). Always log with `logger.error` and include the exception.

```python
# OK — notification failure is non-critical
try:
    await send_push_notification(agent_id, msg)
except Exception as e:
    logger.error("Push notification failed", extra={"agent_id": str(agent_id)}, exc_info=True)
```

**ANTI-PATTERN:** `except Exception: pass` (swallows errors silently). `except Exception` on database writes, conversation logging, or trigger creation — these MUST propagate or retry.

> **Tech debt:** Dozens of bare `except Exception` across `webhooks.py`, `dispatcher.py`, `trigger_worker.py` (audit finding B-2). Each must be classified as critical vs non-critical.

---

### 1.4 Async Patterns

FastAPI runs on an async event loop. Blocking calls freeze ALL concurrent requests.

**Rules:**

1. All route handlers that call the database or external APIs MUST be `async def`.
2. If you must call synchronous code from an async context, wrap it in `asyncio.to_thread()`.
3. Never call `time.sleep()` in async code — use `await asyncio.sleep()`.
4. Never call synchronous DB functions from async route handlers.

**REQUIRED pattern:**

```python
# Async route with async DB call
@router.get("/agents/{agent_id}")
async def get_agent(agent_id: UUID):
    async with get_async_db_connection() as conn:
        row = await conn.fetchone("SELECT * FROM agents WHERE id = %s", [agent_id])
    return row

# If you MUST call sync code from async context:
result = await asyncio.to_thread(sync_function, arg1, arg2)
```

**ANTI-PATTERN:** Calling `get_db_connection()` (sync) from inside an `async def` route handler. This blocks the event loop.

> **Tech debt:** `process_inbound_message` in `webhooks.py` is `async def` but calls sync DB functions internally (audit finding C-3). Must be wrapped in `asyncio.to_thread()` or migrated to async.

---

### 1.5 Pydantic v2 Patterns

All data validation uses Pydantic v2. Models use `model_config` dict (not inner `Config` class).

**REQUIRED pattern:**

```python
from pydantic import BaseModel, Field, field_validator

class ContactCreate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    name: str = Field(min_length=1, max_length=200)
    phone: str
    email: str | None = None
    role: str = "lead"

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # Strip non-digits, validate E.164 format
        digits = "".join(c for c in v if c.isdigit() or c == "+")
        if not digits.startswith("+") or len(digits) < 11:
            raise ValueError("Phone must be E.164 format (e.g., +12675551234)")
        return digits
```

For serialization, always use `model_dump()` (not `.dict()`):

```python
data = contact.model_dump(exclude_none=True)
```

**Reference:** `app/models/schemas.py` — uses `BaseModel`, `Field`, proper type annotations.

**ANTI-PATTERN:** Using `class Config:` inner class (Pydantic v1 style). Calling `.dict()` or `.json()` (deprecated v1 methods). Putting validation logic outside of Pydantic models.

---

### 1.6 Logging Standards

All logging is structured JSON via `app/pipeline/structured_logging.py`. Every log entry includes a correlation ID automatically.

**REQUIRED pattern:**

```python
import logging

logger = logging.getLogger(__name__)

# Simple log with structured extras
logger.info("Message processed",
    extra={"agent_id": str(agent_id), "channel": "sms", "latency_ms": 142})

# Error log — always include exc_info for stack traces
logger.error("Tool execution failed",
    extra={"agent_id": str(agent_id), "tool_name": "create_showing"},
    exc_info=True)
```

**Log level rules:**

| Level | Use For |
|-------|---------|
| `DEBUG` | Detailed execution flow (disabled in production) |
| `INFO` | Normal operations: message received, tool executed, trigger fired |
| `WARNING` | Recoverable issues: rate limited, fallback used, config missing |
| `ERROR` | Failures: API error, DB error, unhandled exception |
| `CRITICAL` | System-level failures: pool exhaustion, security violation, startup failure |

**Reference:** `app/pipeline/structured_logging.py` — StructuredFormatter with correlation ID, extra fields.

**ANTI-PATTERN:** Using f-strings for log messages when structured extra fields should be used. Logging without `extra={}` context. Using `print()` for debugging.

```python
# BAD — no structured data, can't filter/aggregate
logger.info(f"Processed message for agent {agent_id} in {latency}ms")

# GOOD — structured, searchable, aggregatable
logger.info("Message processed", extra={"agent_id": str(agent_id), "latency_ms": latency})
```

---

### 1.7 Settings Management

All configuration is loaded from environment variables via `pydantic-settings`. Settings are cached with `lru_cache`.

**REQUIRED pattern** (already correct in `app/config.py`):

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str = ""
    ANTHROPIC_API_KEY: str = ""
    ENVIRONMENT: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def validate_production_secrets(self) -> None:
        """Refuse to start with default credentials in production."""
        if self.ENVIRONMENT == "development":
            return
        # ... validation logic ...

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production_secrets()
    return settings
```

**Reference:** `app/config.py` — exemplary implementation.

**ANTI-PATTERN:** Reading `os.environ` directly. Hardcoding secrets or API keys. Putting defaults that are valid production values (use obviously-invalid defaults like empty strings).

---

## 2. Database / PostgreSQL Standards

### 2.1 Query Function Pattern

All database queries follow a consistent pattern: pool-based connection, parameterized queries, dict rows.

**REQUIRED pattern (async — primary for FastAPI handlers):**

```python
from app.db.connection import get_async_db_connection

async def get_conversations(agent_id: UUID, limit: int = 20) -> list[dict]:
    """Fetch recent conversations for an agent."""
    async with get_async_db_connection() as conn:
        rows = await conn.execute(
            """SELECT c.id, c.contact_id, c.status, c.last_message_at
               FROM conversations c
               WHERE c.agent_id = %s AND c.status = 'active'
               ORDER BY c.last_message_at DESC
               LIMIT %s""",
            [agent_id, limit],
        )
        return rows.fetchall()
```

**REQUIRED pattern (sync — workers only):**

```python
from app.db.connection import get_db_connection

def process_triggers() -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT * FROM triggers
                   WHERE status = 'pending' AND scheduled_at <= %s
                   FOR UPDATE SKIP LOCKED
                   LIMIT 50""",
                [now],
            )
            rows = cur.fetchall()
        conn.commit()
    return rows
```

**Reference:** `app/services/console_queries.py` — uses `get_db_connection()` with context manager, parameterized queries, `dict_row` format.

**ANTI-PATTERN:** String formatting/concatenation for SQL values. Using `f"WHERE id = '{user_id}'"` — this is SQL injection. Forgetting to parameterize. Using `SELECT *` when only specific columns are needed.

---

### 2.2 Connection Pool Management

Pools are initialized at app startup in `app/main.py` via the lifespan handler.

**Pool sizing:**

| Pool | Min | Max | Use Case |
|------|-----|-----|----------|
| Sync pool | 2 | 20 | Workers, background tasks |
| Async pool | 5 | 20 | FastAPI route handlers |

**Rules:**
- Always use `with` / `async with` for connection lifecycle — never acquire without releasing.
- Set `statement_cache_size=0` if connecting through Supavisor/PgBouncer.
- Prefer transaction mode pooling (port 6543 on Supabase).
- Set `idle_in_transaction_session_timeout` on the database to prevent connection starvation.

**Reference:** `app/db/connection.py` — proper pool init with `open=False`, background fill, dict_row default.

**ANTI-PATTERN:** Creating new connections per request instead of using the pool. Leaving connections open (not using context managers). Setting pool `max_size` higher than the database's `max_connections`.

---

### 2.3 RLS Enforcement

Every table with tenant data uses Row-Level Security. RLS is the last line of defense — it stops data leaks even if application code has bugs.

**REQUIRED pattern:**

```sql
-- Schema definition
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts FORCE ROW LEVEL SECURITY;

CREATE POLICY agent_isolation ON contacts
  FOR ALL
  USING (agent_id = current_setting('app.current_agent_id')::uuid);
```

```python
# Application code — SET LOCAL scoped to transaction
async with get_async_db_connection() as conn:
    async with conn.transaction():
        await conn.execute("SET LOCAL app.current_agent_id = %s", [str(agent_id)])
        # All queries in this transaction are now tenant-scoped
        rows = await conn.execute("SELECT * FROM contacts")
```

**Critical rules:**
1. `FORCE ROW LEVEL SECURITY` is MANDATORY on every tenant table — without it, the table owner bypasses all policies.
2. Always use `SET LOCAL` (transaction-scoped), NEVER `SET SESSION` — session state leaks across requests in pooled connections.
3. The operator console intentionally bypasses RLS for cross-tenant visibility. This is by design, but console query functions MUST NOT be callable from unauthenticated routes.

**Reference:** `app/db/schema.sql` — all tables have `agent_isolation` policies. `app/db/connection.py` — has `set_agent_context()` helper.

**ANTI-PATTERN:** Using `SET SESSION` with connection pooling (state leaks). Forgetting `FORCE ROW LEVEL SECURITY` (superusers bypass). Complex RLS policies with subqueries (performance killer). Bypassing RLS "temporarily" for convenience.

---

### 2.4 Index Strategy

**Rules:**
1. `tenant_id` (or `agent_id`) MUST be the **leading column** in every composite index on tenant tables. This matches the implicit RLS WHERE clause.
2. Use partial indexes for hot-path queries.
3. Use `CREATE INDEX CONCURRENTLY` in production — never lock tables.
4. Monitor unused indexes via `pg_stat_user_indexes` and drop them (they slow writes).

**REQUIRED pattern:**

```sql
-- Composite index with tenant_id leading
CREATE INDEX CONCURRENTLY idx_conversations_agent_status
  ON conversations (agent_id, status, last_message_at DESC);

-- Partial index for hot path
CREATE INDEX CONCURRENTLY idx_triggers_pending
  ON triggers (agent_id, scheduled_at)
  WHERE status = 'pending';

-- Expression index
CREATE INDEX CONCURRENTLY idx_contacts_phone_normalized
  ON contacts (agent_id, regexp_replace(phone, '[^0-9+]', '', 'g'));
```

**ANTI-PATTERN:** Creating indexes without `tenant_id` as the leading column. Using `CREATE INDEX` (blocking) instead of `CREATE INDEX CONCURRENTLY`. Creating indexes on low-cardinality columns alone (e.g., boolean flags).

---

### 2.5 Migration Patterns

All schema changes must be safe for zero-downtime deployments.

**REQUIRED checklist for every migration:**

1. Set `lock_timeout` to prevent indefinite blocking:
   ```sql
   SET lock_timeout = '5s';
   ```

2. Use `CREATE INDEX CONCURRENTLY` (cannot run inside a transaction).

3. Add columns with defaults (PG11+ does this without table rewrite):
   ```sql
   ALTER TABLE contacts ADD COLUMN language_detected text DEFAULT 'en';
   ```

4. Use `NOT VALID` for new constraints, validate later:
   ```sql
   ALTER TABLE contacts ADD CONSTRAINT valid_email
     CHECK (email ~* '^.+@.+$') NOT VALID;
   -- Later, during low traffic:
   ALTER TABLE contacts VALIDATE CONSTRAINT valid_email;
   ```

5. Use **expand-and-contract** for breaking changes:
   - Add new column/table alongside old
   - Migrate data
   - Switch application code
   - Remove old column/table

> **Tech debt:** No Alembic migrations directory exists yet (audit finding A-4). `schema.sql` is monolithic. All future changes must be migrations.

**ANTI-PATTERN:** Running `ALTER TABLE ... DROP COLUMN` without expand-and-contract. Using `CREATE INDEX` (non-concurrent) on production tables. Not setting `lock_timeout`.

---

### 2.6 pgvector Patterns

Vector embeddings use HNSW indexes with cosine distance.

**REQUIRED pattern:**

```sql
-- Index creation
CREATE INDEX CONCURRENTLY idx_embeddings_vector
  ON embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);
```

```python
# Query — use proper parameter binding, not str()
async with get_async_db_connection() as conn:
    rows = await conn.execute(
        """SELECT id, content, 1 - (embedding <=> %s::vector) AS similarity
           FROM embeddings
           WHERE agent_id = %s
           ORDER BY embedding <=> %s::vector
           LIMIT %s""",
        [query_embedding, agent_id, query_embedding, top_k],
    )
```

**Critical:** The query operator MUST match the index ops class. If the index uses `vector_cosine_ops`, the query MUST use `<=>` (cosine distance). Mismatched operators cause silent fallback to sequential scan — 5ms becomes 30s.

| Metric | Operator | Index Ops Class |
|--------|----------|----------------|
| Cosine | `<=>` | `vector_cosine_ops` |
| L2 (Euclidean) | `<->` | `vector_l2_ops` |
| Inner Product | `<#>` | `vector_ip_ops` |

**Reference:** `app/services/rag_service.py` — uses HNSW search with cosine distance.

**ANTI-PATTERN:** Passing embedding vectors via `str(embedding)` instead of proper parameter binding (forces DB to parse string). Using `<->` (L2) when the index is `vector_cosine_ops`. Building IVFFlat indexes on empty tables.

> **Tech debt:** `rag_service.py` line 295 passes vector as `str(query_embedding)` (audit finding P-5). Must switch to proper parameter binding.

---

## 3. Frontend / HTMX Standards

### 3.1 Template Organization

Templates follow a 3-level inheritance hierarchy maximum.

**REQUIRED structure:**

```
templates/
├── base.html                    # Root: <html>, <head>, <body>, nav, footer
├── layouts/
│   ├── console.html             # Admin layout (sidebar + main), extends base
│   └── public.html              # Public layout, extends base
├── partials/                    # HTMX fragment targets (NO <html>/<body>)
│   ├── _toast.html
│   ├── _modal.html
│   └── _table_rows.html
├── components/                  # Reusable Jinja2 macros
│   ├── _macros.html             # Buttons, cards, badges, inputs
│   └── _pagination.html
├── console/                     # Full pages
│   ├── dashboard.html           # extends layouts/console.html
│   ├── conversations.html
│   └── triggers.html
└── emails/
    └── base_email.html
```

**Rules:**
1. Maximum 3 levels of template inheritance: `base.html → layouts/console.html → console/dashboard.html`
2. Partials are prefixed with `_` (e.g., `_toast.html`)
3. Partials NEVER extend a base template — they are bare HTML fragments
4. Partials are the ONLY templates targeted by HTMX swaps
5. Reusable UI components are Jinja2 macros in `components/`

**ANTI-PATTERN:** More than 3 levels of inheritance (debugging nightmare). Returning full pages from HTMX endpoints. Putting HTMX attributes on elements that swap entire pages.

---

### 3.2 HTMX Patterns

**Dual-response endpoints (full page vs fragment):**

Every endpoint that serves both initial page loads and HTMX partial updates MUST detect the `HX-Request` header:

```python
@router.get("/console/conversations")
async def conversations(request: Request):
    data = await get_conversations(...)
    if request.headers.get("HX-Request"):
        return _render(request, "partials/_conversation_list.html", **data)
    return _render(request, "console/conversations.html", **data)
```

**CSRF via hx-headers (global):**

Apply CSRF token on `<body>` so every HTMX request includes it automatically:

```html
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
```

**Reference:** `app/api/console.py` line 29 — `generate_csrf_token()` injected into every template render via `_render()`.

**hx-swap strategies:**

| Strategy | Use Case |
|----------|----------|
| `innerHTML` (default) | Replace contents of target |
| `outerHTML` | Replace the target element itself |
| `beforeend` | Append (infinite scroll, chat) |
| `afterbegin` | Prepend (newest-first lists) |
| `delete` | Remove target (after delete action) |
| `none` | Fire request, don't swap (side effects) |

**Request management:**
- Search inputs: `hx-trigger="keyup changed delay:300ms"` — debounce
- Forms: `hx-sync="closest form:replace"` — cancel stale requests
- Dashboard widgets: stagger lazy loads with `hx-trigger="load delay:100ms"`, `delay:200ms`, etc.

**Out-of-band swaps for multi-region updates:**

```html
<!-- Primary response -->
<div id="record-detail">...updated content...</div>

<!-- OOB swap: updates notification count regardless of hx-target -->
<span id="notification-count" hx-swap-oob="true">3</span>
```

**ANTI-PATTERN:** Returning JSON from HTMX endpoints (HTMX expects HTML). Swapping entire pages when only a fragment changed. Missing debounce on search/filter inputs. Calling untrusted third-party HTML endpoints via HTMX.

---

### 3.3 CSS Architecture

Use CSS custom properties (design tokens) with a layered architecture.

**REQUIRED structure:**

```
static/css/
├── tokens/
│   ├── _primitives.css          # Raw values: --blue-500, --gray-100
│   ├── _semantic-light.css      # Semantic: --surface-bg, --text-primary
│   └── _semantic-dark.css       # Dark theme overrides
├── base/
│   ├── _reset.css               # Modern CSS reset
│   ├── _typography.css          # Font stacks, scale
│   └── _utilities.css           # .visually-hidden, .flex-center, etc.
├── layout/
│   ├── _shell.css               # App shell: sidebar, topbar, main
│   └── _responsive.css          # Viewport breakpoints (page-level only)
├── components/
│   ├── _button.css
│   ├── _card.css
│   ├── _data-table.css
│   ├── _modal.css
│   └── _form.css
└── main.css                     # Single entry: @import all in layer order
```

**Cascade layers for specificity control:**

```css
/* main.css */
@layer tokens, reset, base, layout, components, utilities;

@import "tokens/_primitives.css" layer(tokens);
@import "tokens/_semantic-light.css" layer(tokens);
@import "base/_reset.css" layer(reset);
@import "layout/_shell.css" layer(layout);
@import "components/_button.css" layer(components);
@import "base/_utilities.css" layer(utilities);
```

This guarantees utilities always beat components, components beat layout — no `!important` needed.

**Design tokens — always use semantic tokens, never raw values:**

```css
/* GOOD */
.card { background: var(--surface-card); color: var(--text-primary); }

/* BAD — raw color values break theming */
.card { background: #ffffff; color: #111827; }
```

**Dark mode** via `data-theme` attribute on `<html>`:

```css
[data-theme="dark"] {
    --surface-bg: #0f172a;
    --surface-card: #1e293b;
    --text-primary: #f1f5f9;
}
```

**Responsive rules:**
- `@media` queries: page-level layout only (sidebar collapse, grid columns)
- `@container` queries: component-level adaptation (card layout, table density)

**ANTI-PATTERN:** Using `!important`. Inline styles. Magic color/spacing values not from the token system. Using `@media` for component-level responsiveness when `@container` is appropriate.

---

### 3.4 Accessibility Requirements

Accessibility is a requirement, not a nice-to-have. Target WCAG 2.2 AA compliance.

**Dynamic content announcements (critical for HTMX):**

```html
<!-- HTMX swap targets that update async MUST have aria-live -->
<div id="results" role="region" aria-live="polite" aria-label="Search results">
    <!-- HTMX swaps content here; screen reader announces -->
</div>

<!-- Use aria-busy during loading -->
<div id="content" aria-busy="true">Loading...</div>
<!-- After swap, set aria-busy="false" -->
```

**Focus management after swaps:**

```javascript
document.addEventListener('htmx:afterSwap', function(event) {
    const target = event.detail.target;
    const focusTarget = target.querySelector('h1, h2, h3, [autofocus], input, button');
    if (focusTarget) {
        focusTarget.setAttribute('tabindex', '-1');
        focusTarget.focus();
    }
});
```

**Required checklist for every new page/component:**

| Requirement | Standard |
|-------------|----------|
| Interactive targets | Minimum 24x24 CSS pixels (WCAG 2.5.8) |
| Focus indicators | Minimum 2px perimeter, 3:1 contrast ratio (WCAG 2.4.11) |
| Focus not obscured | Focused element never hidden by sticky headers (WCAG 2.4.12) |
| Heading hierarchy | One `<h1>` per page, no skipped levels |
| Landmarks | `<nav>`, `<main>`, `<aside>`, `<header>`, `<footer>` |
| Keyboard navigation | All interactive elements reachable via Tab/Shift+Tab |
| Skip link | "Skip to main content" as first focusable element |
| Data tables | `<thead>`, `<th scope>` — never tables for layout |
| Modals | `role="dialog"`, `aria-modal="true"`, focus trap, Escape to close |

**ANTI-PATTERN:** Adding HTMX swap targets without `aria-live`. Using `<div onclick>` instead of `<button>`. Relying on color alone to convey information. Skipping heading levels.

---

## 4. Security Standards

### 4.1 CSRF Protection

Every POST, PUT, DELETE endpoint on the console MUST validate a CSRF token. The token is applied globally via `hx-headers` on `<body>`.

**REQUIRED pattern:**

```python
@router.post("/console/agents/{agent_id}/update")
async def update_agent(request: Request, agent_id: UUID, csrf_token: str = Form(None)):
    # Auth check
    redirect = _require_auth(request)
    if redirect:
        return redirect
    # CSRF check
    csrf_error = _check_csrf(request, csrf_token)
    if csrf_error:
        return csrf_error
    # ... proceed
```

**Reference:** `app/api/console.py` — `_check_csrf()` helper, double-submit cookie pattern.

**ANTI-PATTERN:** POST endpoints without CSRF validation. Excluding endpoints "because they don't change data" (any state mutation needs CSRF).

---

### 4.2 Input Validation

Validate all input at system boundaries using Pydantic models. Sanitize HTML content with a proper library.

**REQUIRED pattern:**

```python
# Webhook input validation
from pydantic import BaseModel, field_validator

class InboundMessage(BaseModel):
    from_number: str
    body: str
    media_urls: list[str] = []

    @field_validator("body")
    @classmethod
    def sanitize_body(cls, v: str) -> str:
        return bleach.clean(v, tags=[], strip=True)
```

For user-generated content that will be stored or displayed:

```python
import bleach  # or nh3

sanitized = bleach.clean(raw_html, tags=[], attributes={}, strip=True)
```

**ANTI-PATTERN:** Regex-based HTML sanitization (`<script>` stripping). Trusting webhook payloads without validation. Passing unsanitized user input to templates without auto-escaping.

> **Tech debt:** `console.py` line 847 uses regex for HTML sanitization (audit finding S-6). Must switch to `bleach` or `nh3`.

---

### 4.3 RLS Verification

See [Section 2.3](#23-rls-enforcement). Never bypass RLS outside of the operator console. The console query layer (`console_queries.py`) intentionally skips RLS for cross-tenant visibility — these functions MUST NOT be callable from unauthenticated routes.

> **Tech debt:** No `require_operator_context()` check at the query layer (audit finding S-2). Authorization is only at the route level.

---

### 4.4 Secret Management

**Rules:**
1. All secrets come from environment variables via `app/config.py` `Settings`.
2. Never hardcode secrets, API keys, passwords, or tokens in code.
3. Never commit `.env` files. The `.gitignore` MUST include `.env*`.
4. Default values for secrets MUST be obviously invalid (empty string, `"changeme"`, etc.).
5. Production startup MUST validate that defaults have been replaced (see `validate_production_secrets()`).

**Reference:** `app/config.py` — `CONSOLE_PASSWORD: str = "changeme"` with `validate_production_secrets()` that calls `sys.exit(1)` if defaults are used in production.

**ANTI-PATTERN:** `API_KEY = "sk-ant-..."` anywhere in source code. Logging secrets (even at debug level). Committing `.env` files.

---

### 4.5 Auth Patterns

**Console (operator):** Session-based authentication via signed cookies.

```python
# Auth check on every console route
redirect = _require_auth(request)
if redirect:
    return redirect
```

**Webhooks:** Signature validation for every inbound webhook.

```python
# Twilio — validate signature
from twilio.request_validator import RequestValidator
validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
if not validator.validate(url, params, signature):
    return Response(status_code=401)

# Vapi — validate shared secret
if request.headers.get("x-vapi-secret") != settings.VAPI_WEBHOOK_SECRET:
    return Response(status_code=401)
```

**Rules:**
1. Every webhook endpoint MUST validate the sender's signature/secret.
2. If the secret is not configured in production, the endpoint MUST return 401 (not proceed with a warning).
3. Console auth MUST be checked on every route handler — use the `_require_auth()` pattern.

> **Tech debt:** SendGrid inbound webhook has no signature validation (audit finding S-3). Vapi webhook proceeds without secret when not configured (audit finding S-4).

---

### 4.6 Rate Limiting

All public-facing endpoints and login endpoints MUST have rate limiting.

**REQUIRED pattern:**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/console/login")
@limiter.limit("5/minute")
async def login_submit(request: Request, password: str = Form(...)):
    ...
```

> **Tech debt:** No rate limiting on console login (audit finding S-7). Must add `slowapi` or Redis-backed counter.

---

## 5. Testing Standards

### 5.1 Required Coverage

| Feature Type | Required Tests |
|-------------|---------------|
| API endpoint | Happy path + auth failure + validation error + edge case |
| Database query function | Correct results + empty results + error handling |
| Pipeline stage | Happy path + each branch/classification + malformed input |
| Tool function | Success + failure + permission denied + invalid input |
| Worker | Processing logic + error isolation + idempotency |
| Security feature | Auth bypass attempt + CSRF validation + signature validation |

### 5.2 Async Test Patterns

Use `pytest-asyncio` for async tests. Mark async tests explicitly.

**REQUIRED pattern:**

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_get_conversations_returns_active():
    mock_conn = AsyncMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        {"id": "abc", "status": "active"}
    ]

    with patch("app.services.console_queries.get_async_db_connection") as mock_db:
        mock_db.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_conversations(agent_id=AGENT_ID)

    assert len(result) == 1
    assert result[0]["status"] == "active"
```

**ANTI-PATTERN:** Using `asyncio.run()` inside tests (conflicts with pytest-asyncio). Mixing sync and async tests without proper markers.

---

### 5.3 Mock Patterns

Mock external services at the client boundary, not deep in implementation.

**REQUIRED pattern:**

```python
from unittest.mock import MagicMock, patch

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

def make_mock_response(text="test response", input_tokens=100, output_tokens=50):
    """Factory for mock Anthropic responses."""
    response = MagicMock()
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text
    response.content = [content_block]
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response

@patch("app.services.anthropic_service.anthropic.Anthropic")
def test_classify_returns_parsed_json(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_response(
        text='{"intent": "scheduling", "confidence": 0.95}'
    )

    client = AnthropicClient(api_key="test-key")
    result = client.classify("system prompt", "Can we see houses?", AGENT_ID)
    assert result["intent"] == "scheduling"
```

**Reference:** `tests/test_anthropic_service.py` — exemplary mock patterns with factory functions.

**ANTI-PATTERN:** Mocking too deep (mocking internal functions instead of external boundaries). Not resetting mocks between tests. Using real API keys in tests.

---

### 5.4 Test Naming Conventions

```
test_{function_name}_{scenario}_{expected_result}
```

Examples:
- `test_classify_returns_parsed_json`
- `test_classify_handles_markdown_json`
- `test_process_triggers_skips_locked_rows`
- `test_login_rejects_wrong_password`

Test files mirror source files: `app/services/anthropic_service.py` → `tests/test_anthropic_service.py`

**ANTI-PATTERN:** Vague test names like `test_it_works` or `test_1`. Test files that don't correspond to source files.

> **Tech debt:** No tests for `console_queries.py` (1400+ LOC, audit finding), `dispatcher.py`, or security features.

---

## 6. API Standards

### 6.1 Endpoint Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Console page | `GET /console/{resource}` | `GET /console/conversations` |
| Console action | `POST /console/{resource}/{id}/{action}` | `POST /console/triggers/123/pause` |
| Webhook | `POST /webhooks/{provider}/{event}` | `POST /webhooks/twilio/inbound` |
| API (internal) | `GET /api/{resource}` | `GET /api/agents/{id}/stats` |
| Health | `GET /health` | `GET /health` |

**Rules:**
- Use plural nouns for resources (`/agents`, not `/agent`)
- Use kebab-case for multi-word resources (`/agent-portal`, not `/agentPortal`)
- Actions are verbs as path segments, not query params (`/triggers/123/pause`, not `/triggers/123?action=pause`)

---

### 6.2 Response Format

| Endpoint Type | Response Format |
|--------------|----------------|
| Console pages | `HTMLResponse` via Jinja2 templates |
| HTMX partials | HTML fragments (no `<html>`, `<body>` wrapper) |
| API endpoints | JSON with consistent structure |
| Webhooks | Minimal response (usually empty 200/204) |

**JSON API response format:**

```python
# Success
{"data": {...}, "meta": {"page": 1, "total": 42}}

# Error
{"error": "VALIDATION_ERROR", "message": "Phone must be E.164 format", "details": [...]}
```

---

### 6.3 Pagination

All list endpoints that can return unbounded results MUST be paginated.

**REQUIRED pattern:**

```python
@router.get("/console/conversations")
async def conversations(request: Request, page: int = 1, per_page: int = 25):
    offset = (page - 1) * per_page
    rows = await get_conversations(agent_id, limit=per_page + 1, offset=offset)
    has_next = len(rows) > per_page
    rows = rows[:per_page]
    return _render(request, "console/conversations.html",
        conversations=rows, page=page, has_next=has_next)
```

SQL:
```sql
SELECT ... FROM conversations
WHERE agent_id = %s
ORDER BY last_message_at DESC
LIMIT %s OFFSET %s
```

> **Tech debt:** Several console views lack pagination (audit finding in `console_queries.py`).

**ANTI-PATTERN:** Loading all rows into memory. Using `OFFSET` without `LIMIT`. Not providing page metadata in the response.

---

### 6.4 Error Response Format

All API errors use a consistent JSON structure:

```python
{
    "error": "ERROR_CODE",        # Machine-readable constant
    "message": "Human description", # Human-readable explanation
    "details": []                   # Optional: field-level errors
}
```

HTTP status codes:

| Code | Use |
|------|-----|
| 200 | Success |
| 201 | Created |
| 204 | Deleted (no content) |
| 400 | Validation error |
| 401 | Not authenticated |
| 403 | Forbidden (CSRF, consent, permission) |
| 404 | Not found |
| 429 | Rate limited |
| 500 | Internal server error |

---

## 7. Code Organization

### 7.1 File/Directory Structure

```
app/
├── api/              # Route handlers (thin — delegate to services)
│   ├── console.py
│   ├── webhooks.py
│   ├── health.py
│   └── ...
├── db/               # Database: connection pool, schema, migrations
│   ├── connection.py
│   ├── schema.sql
│   └── migrations/   # Alembic migrations (TODO)
├── models/           # Pydantic models / schemas
│   └── schemas.py
├── pipeline/         # Message processing pipeline
│   ├── handlers.py
│   ├── assembler.py
│   ├── dispatcher.py
│   ├── classifier.py
│   └── structured_logging.py
├── services/         # Business logic and external service wrappers
│   ├── anthropic_service.py
│   ├── console_queries.py
│   ├── rag_service.py
│   └── ...
├── tools/            # LLM tool functions (contacts, listings, etc.)
│   ├── contacts.py
│   ├── listings.py
│   └── ...
├── worker/           # Background workers
│   ├── trigger_worker.py
│   └── daily_scanner.py
├── templates/        # Jinja2 templates
├── static/           # CSS, JS, images
├── config.py         # Settings (pydantic-settings)
└── main.py           # FastAPI app init, middleware, lifespan
```

**Rule:** Route handlers in `api/` are THIN. They handle auth, parse input, call a service, and return a response. Business logic lives in `services/` or `pipeline/`.

---

### 7.2 Naming Conventions

| Thing | Convention | Example |
|-------|-----------|---------|
| Files | `snake_case.py` | `console_queries.py` |
| Functions | `snake_case` | `get_system_pulse()` |
| Async functions | `async_` prefix for async variants of sync functions | `async_get_system_pulse()` |
| Classes | `PascalCase` | `AnthropicClient` |
| Constants | `UPPER_SNAKE_CASE` | `HAIKU_MODEL` |
| Pydantic models | `PascalCase`, noun | `ContactCreate`, `AgentConfig` |
| CSS classes | `kebab-case` | `stat-card`, `data-table` |
| CSS custom properties | `--kebab-case` | `--surface-bg`, `--text-primary` |
| Template files | `snake_case.html`, partials prefixed with `_` | `dashboard.html`, `_toast.html` |
| Test files | `test_{source_file}.py` | `test_anthropic_service.py` |

---

### 7.3 Import Ordering

Follow this order, separated by blank lines:

```python
# 1. Standard library
import logging
import json
from datetime import datetime, timezone
from uuid import UUID

# 2. Third-party packages
from fastapi import APIRouter, Request
from pydantic import BaseModel

# 3. Local application imports
from app.config import get_settings
from app.db.connection import get_async_db_connection
from app.models.schemas import Contact
```

Use `isort` with `profile = "black"` to enforce automatically.

---

### 7.4 Comment / Docstring Standards

```python
def process_inbound_message(
    phone: str,
    body: str,
    agent_id: UUID,
    media_urls: list[str] | None = None,
) -> dict:
    """Process an inbound SMS/RCS message through the full pipeline.

    Resolves the contact, classifies intent, assembles context,
    calls the LLM, executes any tool calls, and dispatches the response.

    Args:
        phone: Sender's phone in E.164 format.
        body: Message text content.
        agent_id: Tenant identifier.
        media_urls: Optional list of media attachment URLs.

    Returns:
        Dict with keys: response_text, tools_used, model_used, tokens_used.

    Raises:
        ConsentBlockedError: If the contact has revoked consent.
    """
```

**Rules:**
1. Every public function has a docstring.
2. Docstrings explain **why** and **what**, not **how** (the code shows how).
3. Inline comments explain **why** something non-obvious is done, not what the code does.
4. Section dividers use `# ============` (see `console.py`, `console_queries.py`).

```python
# GOOD — explains a non-obvious decision
# Use SKIP LOCKED to prevent double-firing when multiple workers run
cur.execute("SELECT ... FOR UPDATE SKIP LOCKED")

# BAD — restates the code
# Execute the SQL query
cur.execute("SELECT ...")
```

---

## 8. Anthropic Claude API Standards

### 8.1 Model Tiering

| Model | Use For | Cost |
|-------|---------|------|
| **Haiku** (`claude-haiku-4-5-20251001`) | Classification, simple extraction, summarization, cheap/fast tasks | $1/$5 per 1M tokens |
| **Sonnet** (`claude-sonnet-4-5-20241022`) | Complex reasoning, multi-step tool use, nuanced conversation responses | $3/$15 per 1M tokens |

**Decision rule:** Start with Haiku. Escalate to Sonnet only when the task requires multi-step reasoning, complex tool orchestration, or nuanced judgment.

**Reference:** `app/services/anthropic_service.py` lines 16-17 — model constants defined centrally.

> **Tech debt:** Model IDs are hardcoded constants (audit finding B-5). Should be configurable via environment variables with these as defaults.

---

### 8.2 Prompt Caching

Use Anthropic's prompt caching for system prompts that are reused across many requests.

**REQUIRED pattern:**

```python
response = client.messages.create(
    model=HAIKU_MODEL,
    max_tokens=200,
    system=[{
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"},
    }],
    messages=messages,
)
```

The `cache_control: ephemeral` header tells Anthropic to cache this system prompt block. Subsequent requests with the same system prompt skip re-processing, reducing latency and cost.

**Reference:** Architecture audit finding 8 — prompt caching already used correctly.

**ANTI-PATTERN:** Passing system prompts without cache_control. Including per-request dynamic data in the cached system prompt block (defeats caching).

---

### 8.3 Streaming

Use streaming for any response that will be displayed to a human in real-time (chat responses, long-form content).

**REQUIRED pattern:**

```python
with client.messages.stream(
    model=SONNET_MODEL,
    max_tokens=1024,
    system=system_prompt,
    messages=messages,
) as stream:
    for text in stream.text_stream:
        yield text  # Send to client via SSE or chunked response
```

For background processing (trigger text generation, summarization), streaming is NOT required — use the standard synchronous call.

---

### 8.4 Cost Tracking

Every LLM call MUST be tracked in the `usage_metrics` table with: agent_id, date, model, input_tokens, output_tokens, cost_cents.

**REQUIRED pattern:**

```python
# After every LLM call
costs = MODEL_COSTS.get(model, MODEL_COSTS[HAIKU_MODEL])
cost_cents = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

logger.info("LLM call completed", extra={
    "agent_id": str(agent_id),
    "model_used": model,
    "tokens_used": input_tokens + output_tokens,
    "cost_cents": cost_cents,
    "latency_ms": latency,
})
```

Persist to database (in dispatcher, not in the client):

```python
conn.execute(
    """INSERT INTO usage_metrics (agent_id, date, model, llm_cost_cents, ...)
       VALUES (%s, CURRENT_DATE, %s, %s, ...)
       ON CONFLICT (agent_id, date) DO UPDATE SET llm_cost_cents = usage_metrics.llm_cost_cents + EXCLUDED.llm_cost_cents""",
    [agent_id, model, cost_cents],
)
```

> **Tech debt:** `AnthropicClient._token_usage` is an in-memory dict that loses data on restart (audit finding C-2). Remove it — rely on DB-persisted metrics only.

---

### 8.5 max_tokens

`max_tokens` MUST be set explicitly on every API call. Never rely on defaults.

**Guidelines:**

| Task | max_tokens |
|------|-----------|
| Classification / intent detection | 200 |
| Short response (SMS reply) | 500 |
| Conversation response | 1024 |
| Summarization | 500 |
| Complex tool orchestration | 2048 |

**ANTI-PATTERN:** Omitting `max_tokens` (uses model default, unpredictable cost). Setting `max_tokens=4096` for a classification task (wastes budget, slow).

---

### 8.6 Request ID Logging

Every Anthropic API call MUST log the request ID from the response headers for debugging and support tickets.

```python
response = client.messages.create(...)
request_id = response._response.headers.get("request-id", "unknown")
logger.info("Anthropic call", extra={
    "anthropic_request_id": request_id,
    "model_used": model,
    "agent_id": str(agent_id),
})
```

---

## 9. Tech Debt Register

Issues flagged in this document where current code violates the standards. These are tracked from the architecture audit and should be addressed per the prioritized schedule in `docs/architecture-audit.md`.

| ID | Standard Violated | Location | Severity | Section |
|----|------------------|----------|----------|---------|
| C-1 | 2.1 Query pattern (no `FOR UPDATE SKIP LOCKED`) | `trigger_worker.py` | Critical | [2.1](#21-query-function-pattern) |
| C-2 | 8.4 Cost tracking (in-memory, loses on restart) | `anthropic_service.py` | High | [8.4](#84-cost-tracking) |
| C-3 | 1.4 Async patterns (sync calls in async context) | `webhooks.py` | High | [1.4](#14-async-patterns) |
| C-4 | 2.1 Query pattern (invalid UPDATE SQL) | `webhooks.py` | High | [2.1](#21-query-function-pattern) |
| S-3 | 4.5 Auth (missing webhook signature validation) | `webhooks.py` (email) | Medium | [4.5](#45-auth-patterns) |
| S-4 | 4.5 Auth (webhook proceeds without secret) | `webhooks.py` (Vapi) | Low | [4.5](#45-auth-patterns) |
| S-6 | 4.2 Input validation (regex HTML sanitization) | `console.py` | Low | [4.2](#42-input-validation) |
| S-7 | 4.6 Rate limiting (none on login) | `console.py` | Low | [4.6](#46-rate-limiting) |
| B-1 | 1.2 Dependency injection (singleton globals) | Multiple services | Medium | [1.2](#12-dependency-injection) |
| B-2 | 1.3 Error handling (bare except) | Multiple files | Medium | [1.3](#13-error-handling) |
| B-3 | 1.5 Pydantic (no return type models) | `console_queries.py` | Low | [1.5](#15-pydantic-v2-patterns) |
| B-5 | 8.1 Model tiering (hardcoded model IDs) | `anthropic_service.py` | Low | [8.1](#81-model-tiering) |
| A-4 | 2.5 Migrations (no Alembic setup) | `app/db/` | Medium | [2.5](#25-migration-patterns) |
| A-5 | 2.1 Query pattern (sync/async duplication) | `console_queries.py` | Low | [2.1](#21-query-function-pattern) |
| P-1 | 2.1 Query pattern (N+1 in agent list) | `console_queries.py` | Medium | [2.1](#21-query-function-pattern) |
| P-5 | 2.6 pgvector (str() for vector param) | `rag_service.py` | Low | [2.6](#26-pgvector-patterns) |

---

*End of engineering standards. Questions, violations, or proposed amendments: file with @eng.*
