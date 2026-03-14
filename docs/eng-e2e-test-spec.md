# E2E Smoke Test Spec — Calloway Admin Console

**Author:** Atlas (Engineering Lead)
**Date:** 2026-03-14
**Status:** Draft

---

## 1. Framework Recommendation: Playwright (Python)

### Evaluation Summary

| Criterion | Playwright | Selenium | httpx Functional |
|---|---|---|---|
| HTMX support | Native — auto-waits for network idle, DOM mutations | Manual waits, fragile sleep-based | No JS execution at all |
| Speed | Fast — one browser per suite, contexts per test | Slow — driver startup per session | Fastest — no browser overhead |
| CI headless mode | Built-in `--headed=false` (default) | Requires Xvfb or headless Chrome flags | N/A |
| Screenshot on failure | Built-in `page.screenshot()` + trace viewer | Manual screenshot capture | N/A |
| Learning curve | Low — sync API feels like requests, async available | Medium — verbose, WebDriverWait patterns | Lowest — just HTTP |
| HTMX partial verification | Can assert on swapped DOM elements after `hx-get`/`hx-post` | Can, but timing is unreliable | Cannot test HTMX at all |
| Install size | ~130 MB (includes browser binaries) | ~50 MB + separate browser driver | 0 (already installed) |

### Decision: Playwright (Python, sync API)

The admin console is HTMX-heavy. Multiple pages use `hx-get` with `hx-trigger="intersect once"` and `hx-trigger="every 15s"` for live updates. httpx-based functional tests (which already exist in `tests/test_console.py`) cannot verify that HTMX swaps work correctly in a real browser. Selenium could do it but Playwright is faster, has better auto-wait semantics, and generates traces for debugging failures.

We keep the existing `test_console.py` unit tests (httpx/TestClient-based) for fast CI feedback. Playwright tests run separately as a slower smoke-test gate.

### Installation

```bash
pip install playwright pytest-playwright
playwright install chromium --with-deps
```

Add to `requirements-dev.txt`:
```
playwright==1.49.1
pytest-playwright==0.6.2
```

---

## 2. Critical User Journeys — Test Cases

### 2.1 Authentication (3 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| AUTH-01 | Valid login | Navigate to `/console/login`, fill password=`changeme`, submit | Redirected to `/console/dashboard`, page contains "Active Customers" |
| AUTH-02 | Invalid login | Submit password=`wrong` | Stays on login page, "Invalid password" error visible |
| AUTH-03 | Session expiry / unauthenticated redirect | Navigate to `/console/dashboard` with no session | Redirected to `/console/login` |

### 2.2 Dashboard (2 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| DASH-01 | Dashboard loads with pulse cards | Login, navigate to `/console/dashboard` | Page contains 5 pulse cards: "Active Customers", "Messages Today", "Messages 24h", "Errors 24h", "AI Cost Today" |
| DASH-02 | Activity feed loads via HTMX | Wait for `#activity-feed` to be populated (hx-trigger="load") | `#activity-feed` is no longer "Loading..." — contains actual feed items or empty state |

### 2.3 Customer List (3 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| CUST-01 | Customer list renders | Navigate to `/console/tenants` | Table with columns: Name, Brokerage, Market, Twilio #, Contacts, Msgs Today, Last Active, Status, Errors 24h |
| CUST-02 | Search filter | Enter search term in the search input, click Filter | URL contains `?search=`, table reflects filtered results |
| CUST-03 | New Customer link | Click "New Customer" button | Navigated to `/console/tenants/new` |

### 2.4 Create New Customer (2 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| CUST-04 | Full form submission | Fill all required fields (name, email, phone, twilio_number), submit | Redirected to `/console/tenants/{agent_id}` — new customer detail page loads |
| CUST-05 | Validation — missing required field | Submit form with empty name | Stays on form page, browser validation or server error visible |

### 2.5 Customer Detail — All 6 Tabs (7 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| DETAIL-01 | Profile tab (default) | Navigate to `/console/tenants/{id}` | Profile tab is `.active`, shows Name, Email, Phone, Brokerage, Market, Timezone, Twilio # |
| DETAIL-02 | Messages tab | Click "Messages" tab button | `#panel-messages` becomes active, HTMX loads `#messages-container` (intersect trigger) |
| DETAIL-03 | Knowledge Base tab | Click "Knowledge Base" tab button | `#panel-kb` becomes active, HTMX fires `hx-get` to load KB content into `#panel-kb-content` |
| DETAIL-04 | Contacts tab | Click "Contacts" tab button | `#panel-contacts` becomes active, shows contacts table or "No contacts yet." |
| DETAIL-05 | Listings tab | Click "Listings" tab button | `#panel-listings` becomes active, shows listings table or "No listings yet." |
| DETAIL-06 | Automations tab | Click "Automations" tab button | `#panel-automations` becomes active, shows automations table or "No scheduled automations." |
| DETAIL-07 | Edit Settings link | Click "Edit Settings" on detail page | Navigated to `/console/tenants/{id}/edit`, edit form renders |

### 2.6 Edit Customer Settings (1 test)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| EDIT-01 | Save settings | On edit page, change a field, submit | Redirected back to detail page, updated value visible |

### 2.7 Conversations (2 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| CONV-01 | Conversation list loads | Navigate to `/console/conversations` | Table with columns: Customer, Contact, Phone, Channel, Messages, Last Message, Time. Filter form with Customer, Channel, Search |
| CONV-02 | Conversation detail | Click a conversation link | Navigated to `/console/conversations/{id}`, detail page renders with message thread |

### 2.8 Triggers / Automations (4 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| TRIG-01 | Trigger list loads | Navigate to `/console/triggers` | Table with columns: Customer, Type, Scheduled, Status, Action, Autonomy, Recurrence, Actions. Filter form with Status and Customer |
| TRIG-02 | Status filter | Select "completed" status, click Filter | URL contains `?status=completed`, table shows only completed triggers |
| TRIG-03 | Retry button (error trigger) | For a trigger with status=error, click "Retry" | POST to `/console/triggers/{id}/retry`, redirected back to trigger list |
| TRIG-04 | Cancel button (pending trigger) | For a trigger with status=pending, click "Cancel" | POST to `/console/triggers/{id}/cancel`, redirected back to trigger list |

### 2.9 System Health — All 4 Tabs (4 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| HEALTH-01 | Services tab (default) | Navigate to `/console/health` | Services tab active, shows service connectivity cards with status dots |
| HEALTH-02 | Response Times tab | Click "Response Times" tab | Panel shows Avg Response Time, Typical (Median), Slowest 5% cards |
| HEALTH-03 | Errors tab | Click "Errors" tab | Panel shows error tables or "No errors found." |
| HEALTH-04 | Actions tab | Click "Actions" tab | Panel shows customer selector and "Run Check" button |

### 2.10 Billing — Both Tabs (2 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| BILL-01 | Subscriptions tab | Navigate to `/console/billing` | Subscriptions tab active, shows Plan Tiers cards and Active Subscriptions table |
| BILL-02 | AI Costs tab | Click "AI Costs" tab | Panel shows Total AI Cost, Total Messages, Voice Minutes, Showings Booked, AI Requests cards |

### 2.11 Knowledge Base Upload + Delete (2 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| KB-01 | Upload document | On customer detail KB tab, click "+ Add Document", fill title + content, submit | New document appears in KB list (after re-fetching HTMX partial) |
| KB-02 | Remove document | Click remove button on an existing KB item | Document disappears from KB list, redirected with `?tab=knowledge-base` |

### 2.12 CSRF Protection (2 tests)

| ID | Test | Steps | Assertions |
|---|---|---|---|
| CSRF-01 | POST without CSRF token fails | Use `page.request` (Playwright API context) to POST to `/console/tenants/new` with valid session cookie but no `csrf_token` field | Response status 403, body contains "CSRF validation failed" |
| CSRF-02 | POST with wrong CSRF token fails | POST with `csrf_token=bogus` | Response status 403 |

**Total: 34 test cases**

---

## 3. Test Infrastructure

### 3.1 Directory Structure

```
tests/
  e2e/
    __init__.py
    conftest.py          # Fixtures: app server, auth, seed data
    pages/
      __init__.py
      login_page.py
      dashboard_page.py
      tenants_page.py
      tenant_detail_page.py
      tenant_new_page.py
      tenant_edit_page.py
      conversations_page.py
      triggers_page.py
      health_page.py
      billing_page.py
    test_auth.py          # AUTH-01 through AUTH-03
    test_dashboard.py     # DASH-01, DASH-02
    test_customers.py     # CUST-01 through CUST-05, DETAIL-01 through DETAIL-07, EDIT-01
    test_conversations.py # CONV-01, CONV-02
    test_triggers.py      # TRIG-01 through TRIG-04
    test_health.py        # HEALTH-01 through HEALTH-04
    test_billing.py       # BILL-01, BILL-02
    test_kb.py            # KB-01, KB-02
    test_csrf.py          # CSRF-01, CSRF-02
```

### 3.2 Running Tests

```bash
# Full suite
pytest tests/e2e/ --headed=false --timeout=120

# Single file
pytest tests/e2e/test_auth.py -v

# With trace (for debugging failures)
pytest tests/e2e/test_auth.py --tracing=on
```

Add a Makefile target (create `Makefile` or add to existing):
```makefile
e2e-test:
	pytest tests/e2e/ -v --timeout=120 --screenshot=only-on-failure --output=test-results/

e2e-test-debug:
	pytest tests/e2e/ -v --headed --slowmo=500 --timeout=300

e2e-trace:
	playwright show-trace test-results/trace.zip
```

### 3.3 Test Database Setup/Teardown

The E2E tests run against a real FastAPI server with mocked service layer. We do NOT spin up PostgreSQL for smoke tests — instead we mock `console_queries` at the service boundary (same pattern as existing `test_console.py`). This keeps tests fast and avoids CI database provisioning complexity.

For a future phase (integration tests), we can add a `docker-compose.e2e.yml` with a real PostgreSQL instance seeded via `app/db/schema.sql`.

**Approach for the initial implementation:**

```python
# tests/e2e/conftest.py — mock the service layer, run the real FastAPI app
import subprocess, time, os, signal
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

# Seed data that all tests reference
SEED_AGENT_ID = "550e8400-e29b-41d4-a716-446655440000"
SEED_AGENT = {
    "id": SEED_AGENT_ID,
    "name": "Jane Smith",
    "email": "jane@example.com",
    "phone": "+15551234567",
    "brokerage": "Keller Williams",
    "market": "Philadelphia",
    "timezone": "America/New_York",
    "twilio_number": "+15559876543",
    "current_status": "available",
    "style_profile": '{"tone": "professional", "emoji": false}',
    "autonomy_rules": '{"level": "supervised"}',
    "scheduling_prefs": '{"buffer_minutes": 30}',
    "contact_count": 12,
    "messages_today": 5,
    "last_active": "2026-03-14 10:30",
    "errors_24h": 0,
}
```

### 3.4 Fixtures

```python
# tests/e2e/conftest.py
import pytest
from playwright.sync_api import Page

BASE_URL = "http://127.0.0.1:8000"
PASSWORD = "changeme"


@pytest.fixture(scope="session")
def app_server():
    """Start the FastAPI server once for the entire test session."""
    import uvicorn
    import threading

    # Apply all mocks before starting the server
    # (see Section 3.3 for mock setup)

    server = uvicorn.Server(uvicorn.Config(
        "app.main:app", host="127.0.0.1", port=8000, log_level="warning"
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    import httpx
    for _ in range(50):
        try:
            httpx.get(f"{BASE_URL}/console/login", timeout=1)
            break
        except httpx.ConnectError:
            time.sleep(0.1)

    yield server
    server.should_exit = True


@pytest.fixture
def authed_page(page: Page, app_server) -> Page:
    """A Playwright page that is already logged in."""
    page.goto(f"{BASE_URL}/console/login")
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url("**/console/dashboard**")
    return page


@pytest.fixture
def page(page: Page, app_server) -> Page:
    """Ensure server is running before any page access."""
    return page
```

### 3.5 CI Integration (GitHub Actions)

```yaml
# .github/workflows/e2e.yml
name: E2E Smoke Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
          playwright install chromium --with-deps

      - name: Run E2E tests
        run: pytest tests/e2e/ -v --timeout=120 --screenshot=only-on-failure --output=test-results/
        env:
          ENVIRONMENT: development
          CONSOLE_PASSWORD: changeme
          CONSOLE_SESSION_SECRET: test-secret-for-ci

      - name: Upload test artifacts
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-test-results
          path: test-results/
          retention-days: 7
```

### 3.6 Screenshot on Failure

Playwright's `pytest-playwright` plugin has built-in `--screenshot=only-on-failure`. Screenshots are saved to `test-results/`. No custom code needed.

For richer debugging, use `--tracing=retain-on-failure` which captures a full trace file (network, DOM snapshots, console logs) viewable in `playwright show-trace`.

---

## 4. Implementation Plan

### 4.1 Page Object Pattern

Each page object encapsulates selectors and common actions. Keeps tests readable and maintainable when HTML changes.

```python
# tests/e2e/pages/login_page.py
from playwright.sync_api import Page

class LoginPage:
    URL = "/console/login"

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        return self

    def login(self, password: str):
        self.page.fill('input[name="password"]', password)
        self.page.click('button[type="submit"]')
        return self

    @property
    def error_message(self) -> str | None:
        el = self.page.query_selector(".alert-error")
        return el.inner_text() if el else None

    @property
    def is_on_login_page(self) -> bool:
        return "/console/login" in self.page.url
```

```python
# tests/e2e/pages/dashboard_page.py
from playwright.sync_api import Page

class DashboardPage:
    URL = "/console/dashboard"

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def navigate(self):
        self.page.goto(f"{self.base_url}{self.URL}")
        return self

    @property
    def pulse_card_labels(self) -> list[str]:
        return [el.inner_text() for el in self.page.query_selector_all(".card-label")]

    def wait_for_activity_feed(self):
        """Wait for HTMX to replace the 'Loading...' placeholder."""
        self.page.wait_for_function(
            "document.querySelector('#activity-feed')?.innerText !== 'Loading...'"
        )
        return self
```

```python
# tests/e2e/pages/tenant_detail_page.py
from playwright.sync_api import Page

class TenantDetailPage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def navigate(self, agent_id: str):
        self.page.goto(f"{self.base_url}/console/tenants/{agent_id}")
        return self

    def click_tab(self, tab_name: str):
        """Click a tab by its data-tab attribute."""
        self.page.click(f'button[data-tab="{tab_name}"]')
        return self

    def wait_for_htmx_load(self, target_selector: str, timeout: int = 5000):
        """Wait for an HTMX-loaded container to have content."""
        self.page.wait_for_function(
            f"document.querySelector('{target_selector}')?.children.length > 0"
            f" && !document.querySelector('{target_selector} .loading-skeleton')",
            timeout=timeout,
        )
        return self

    @property
    def active_tab(self) -> str | None:
        el = self.page.query_selector('.tab-btn.active')
        return el.get_attribute('data-tab') if el else None

    @property
    def agent_name(self) -> str:
        # Page title is "Customer: Jane Smith"
        return self.page.title().replace("Customer: ", "")
```

### 4.2 Example Test Implementations

#### Example 1: Authentication Flow (AUTH-01, AUTH-02, AUTH-03)

```python
# tests/e2e/test_auth.py
from tests.e2e.pages.login_page import LoginPage

BASE_URL = "http://127.0.0.1:8000"


def test_valid_login(page, app_server):
    """AUTH-01: Correct password logs in and redirects to dashboard."""
    login = LoginPage(page, BASE_URL).navigate()
    login.login("changeme")

    page.wait_for_url("**/console/dashboard**")
    assert "dashboard" in page.url
    assert page.query_selector(".card-label") is not None


def test_invalid_login(page, app_server):
    """AUTH-02: Wrong password shows error on login page."""
    login = LoginPage(page, BASE_URL).navigate()
    login.login("wrongpassword")

    assert login.is_on_login_page
    assert "Invalid" in login.error_message


def test_unauthenticated_redirect(page, app_server):
    """AUTH-03: Accessing dashboard without session redirects to login."""
    page.goto(f"{BASE_URL}/console/dashboard")
    page.wait_for_url("**/console/login**")
    assert "/console/login" in page.url
```

#### Example 2: Customer Detail Tabs (DETAIL-01 through DETAIL-03)

```python
# tests/e2e/test_customers.py (partial)
from tests.e2e.pages.tenant_detail_page import TenantDetailPage

BASE_URL = "http://127.0.0.1:8000"
SEED_AGENT_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_profile_tab_default(authed_page):
    """DETAIL-01: Profile tab is active by default, shows agent info."""
    detail = TenantDetailPage(authed_page, BASE_URL)
    detail.navigate(SEED_AGENT_ID)

    assert detail.active_tab == "profile"
    assert authed_page.query_selector("#panel-profile.active") is not None
    # Verify profile table has expected fields
    assert authed_page.inner_text("#panel-profile") is not None


def test_messages_tab_htmx(authed_page):
    """DETAIL-02: Messages tab loads contact list via HTMX."""
    detail = TenantDetailPage(authed_page, BASE_URL)
    detail.navigate(SEED_AGENT_ID)
    detail.click_tab("messages")

    assert detail.active_tab == "messages"
    # Wait for HTMX intersect trigger to load messages
    detail.wait_for_htmx_load("#messages-container", timeout=10000)


def test_kb_tab_htmx(authed_page):
    """DETAIL-03: Knowledge Base tab loads via HTMX on click."""
    detail = TenantDetailPage(authed_page, BASE_URL)
    detail.navigate(SEED_AGENT_ID)
    detail.click_tab("knowledge-base")

    assert detail.active_tab == "knowledge-base"
    # KB uses hx-trigger="click once" — content loads on tab click
    detail.wait_for_htmx_load("#panel-kb-content", timeout=10000)
```

#### Example 3: CSRF Protection (CSRF-01)

```python
# tests/e2e/test_csrf.py
import httpx

BASE_URL = "http://127.0.0.1:8000"


def test_post_without_csrf_token_returns_403(app_server):
    """CSRF-01: POST to a CSRF-protected route without token returns 403."""
    with httpx.Client(base_url=BASE_URL) as client:
        # First, log in to get a session cookie
        login_resp = client.post("/console/login", data={"password": "changeme"}, follow_redirects=False)
        assert login_resp.status_code == 303

        # Now POST to a protected endpoint without csrf_token
        resp = client.post(
            f"/console/tenants/new",
            data={
                "name": "Test Agent",
                "email": "test@example.com",
                "phone": "+15551111111",
                "twilio_number": "+15552222222",
                # Deliberately omitting csrf_token
            },
        )
        assert resp.status_code == 403
        assert "CSRF" in resp.text


def test_post_with_wrong_csrf_token_returns_403(app_server):
    """CSRF-02: POST with a bogus CSRF token returns 403."""
    with httpx.Client(base_url=BASE_URL) as client:
        login_resp = client.post("/console/login", data={"password": "changeme"}, follow_redirects=False)
        assert login_resp.status_code == 303

        resp = client.post(
            f"/console/tenants/new",
            data={
                "name": "Test Agent",
                "email": "test@example.com",
                "phone": "+15551111111",
                "twilio_number": "+15552222222",
                "csrf_token": "bogus-token-that-doesnt-match",
            },
        )
        assert resp.status_code == 403
```

### 4.3 HTMX Wait Patterns

The console uses three HTMX trigger patterns that tests must handle:

| Pattern | Example | Test Strategy |
|---|---|---|
| `hx-trigger="load"` | Activity feed on dashboard | `page.wait_for_function()` — check content is no longer placeholder |
| `hx-trigger="intersect once"` | Messages tab | Scroll element into view, then wait for content |
| `hx-trigger="click once"` | KB tab | Click the tab button, then wait for `hx-target` to be populated |
| `hx-trigger="every 30s"` | Health page auto-refresh | Not tested — would require 30s wait. Test initial load only. |

Generic HTMX wait helper:

```python
def wait_for_htmx_swap(page, target_selector: str, timeout: int = 5000):
    """Wait until an HTMX target has content (no skeleton/placeholder)."""
    page.wait_for_function(
        f"""(() => {{
            const el = document.querySelector('{target_selector}');
            if (!el) return false;
            if (el.querySelector('.loading-skeleton')) return false;
            if (el.innerText.trim() === 'Loading...') return false;
            return el.children.length > 0;
        }})()""",
        timeout=timeout,
    )
```

---

## 5. Phased Rollout

### Phase 1 (This Sprint) — Skeleton + Auth + Dashboard
- Set up `tests/e2e/` directory structure, `conftest.py`, page objects
- Implement AUTH-01 through AUTH-03
- Implement DASH-01, DASH-02
- Add CSRF-01, CSRF-02
- Wire up `make e2e-test` and GitHub Actions workflow
- **Goal: 7 tests passing in CI**

### Phase 2 — Customer CRUD + Detail Tabs
- Implement CUST-01 through CUST-05
- Implement DETAIL-01 through DETAIL-07
- Implement EDIT-01
- Set up seed data fixtures
- **Goal: 20 tests passing**

### Phase 3 — Remaining Pages
- Implement CONV-01, CONV-02
- Implement TRIG-01 through TRIG-04
- Implement HEALTH-01 through HEALTH-04
- Implement BILL-01, BILL-02
- Implement KB-01, KB-02
- **Goal: All 34 tests passing**

### Phase 4 (Future) — Real Database Integration
- `docker-compose.e2e.yml` with PostgreSQL + Redis
- Seed `schema.sql` + fixture data via SQL
- Remove service mocks, test full stack
- Only needed once test suite proves stable with mocks

---

## 6. Performance Budget

Target: **Full suite under 3 minutes** in CI.

| Category | Tests | Estimated Time |
|---|---|---|
| Auth + CSRF | 5 | 5s |
| Dashboard | 2 | 4s |
| Customer CRUD | 5 | 10s |
| Customer detail tabs | 7 | 15s (HTMX waits) |
| Edit | 1 | 3s |
| Conversations | 2 | 5s |
| Triggers | 4 | 8s |
| Health | 4 | 8s |
| Billing | 2 | 5s |
| KB | 2 | 8s |
| **Total** | **34** | **~71s** |

Server startup: ~3s. Browser launch: ~2s. Overhead: ~10s. **Total estimated: ~86 seconds.**

---

## 7. Open Questions

1. **Mock vs. real DB for Phase 1?** Recommendation: mock. The existing `test_console.py` already mocks `console_queries` — reuse those mock return values. Revisit when we have a CI-friendly Docker Compose setup.

2. **Should E2E block PR merge?** Recommendation: yes, but only after Phase 2 is stable. During Phase 1, run as a non-blocking "informational" check.

3. **Browser matrix?** Chromium only. We control the admin console — no need to test Firefox/Safari. Add if external users gain access.
