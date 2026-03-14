# Toast Notification & Tooltip System — Design Specification

**Author:** Lyra, Product Designer
**Date:** 2026-03-14
**Status:** Ready for Engineering
**Scope:** Calloway Admin Console (`/console/*`)

---

## Table of Contents

1. [Design Principles](#design-principles)
2. [Part 1: Toast Notification System](#part-1-toast-notification-system)
   - [Toast Types & Visual Spec](#toast-types--visual-spec)
   - [Toast Behavior](#toast-behavior)
   - [HTMX Integration Pattern](#htmx-integration-pattern)
   - [Toast Inventory](#toast-inventory)
   - [Implementation: HTML](#implementation-html)
   - [Implementation: CSS](#implementation-css)
   - [Implementation: JavaScript](#implementation-javascript)
3. [Part 2: Tooltip System](#part-2-tooltip-system)
   - [Tooltip Types & Visual Spec](#tooltip-types--visual-spec)
   - [Tooltip Behavior](#tooltip-behavior)
   - [Tooltip Inventory](#tooltip-inventory)
   - [Implementation: HTML](#implementation-html-1)
   - [Implementation: CSS](#implementation-css-1)
4. [Accessibility Checklist](#accessibility-checklist)

---

## Design Principles

1. **Invisible until needed.** Toasts and tooltips exist to reduce confusion, not to add visual noise. They appear precisely when context is missing, then disappear.
2. **Consistent with the dark palette.** Every color, shadow, and radius maps to existing CSS custom properties (`--bg-card`, `--border`, `--green`, etc.).
3. **No external dependencies.** Pure CSS animations + HTMX OOB swaps + a single lightweight JS controller (~40 lines). No libraries.
4. **Accessible by default.** ARIA live regions for toasts. `aria-describedby` for tooltips. Keyboard-accessible dismiss. Respects `prefers-reduced-motion`.

---

## Part 1: Toast Notification System

### Toast Types & Visual Spec

| Type | Color Token | Background | Border-Left | Icon | Use Case |
|------|------------|------------|-------------|------|----------|
| **Success** | `--green` (#1ED760) | `rgba(30, 215, 96, 0.12)` | 3px solid `--green` | Checkmark | Action completed successfully |
| **Error** | `--red` (#E91429) | `rgba(233, 20, 41, 0.12)` | 3px solid `--red` | X circle | Action failed, server error |
| **Warning** | `--yellow` (#FFA42B) | `rgba(255, 164, 43, 0.12)` | 3px solid `--yellow` | Alert triangle | Action succeeded with caveats |
| **Info** | `--accent` (#1ED760) | `rgba(30, 215, 96, 0.08)` | 3px solid `--border` | Info circle | Informational notification |

**Visual Dimensions:**
- Width: `360px` (max), min `280px`
- Padding: `14px 16px 14px 14px`
- Border-radius: `8px`
- Font size: `13px`, line-height `1.4`
- Box shadow: `0 4px 24px rgba(0, 0, 0, 0.4), 0 1px 4px rgba(0, 0, 0, 0.2)`
- Close button: `20px` hit target, positioned top-right
- Icon: `16px`, vertically centered with first line of text

### Toast Behavior

| Property | Value | Rationale |
|----------|-------|-----------|
| **Position** | Top-right, `24px` from edges | Out of the way of sidebar and main content. Near the health status dot for spatial grouping. |
| **Entry animation** | Slide in from right + fade (200ms ease-out) | Draws attention without disrupting. |
| **Exit animation** | Fade out + slide right (150ms ease-in) | Faster exit keeps the UI feeling crisp. |
| **Auto-dismiss: Success** | 4 seconds | Confirm-and-go. User doesn't need to dwell. |
| **Auto-dismiss: Info** | 5 seconds | Slightly longer for reading. |
| **Auto-dismiss: Warning** | 6 seconds | Needs a moment to process. |
| **Auto-dismiss: Error** | No auto-dismiss | Errors demand acknowledgment. User must click X. |
| **Manual dismiss** | X button on all toasts | Always available. Keyboard: `Escape` dismisses the topmost toast. |
| **Stacking** | Newest on top, max 4 visible. Older toasts shift down with 8px gap. Beyond 4, oldest is auto-dismissed. | Prevents toast avalanche. |
| **Hover behavior** | Hovering pauses auto-dismiss timer | Gives user time to read. |
| **Reduced motion** | No slide, instant opacity toggle | Respects `prefers-reduced-motion: reduce`. |

### HTMX Integration Pattern

Toasts are triggered from the server using **HTMX Out-of-Band (OOB) swaps** via the `HX-Trigger` response header. This is the cleanest pattern because it works with all response types (redirects, partials, full pages) and requires zero changes to existing endpoint return values.

**Server-side pattern (Python/FastAPI):**

```python
# In console.py — helper to attach toast to any response
def _toast(response: Response, message: str, toast_type: str = "success") -> Response:
    """Attach a toast notification to any response via HX-Trigger header.

    Args:
        response: The FastAPI Response/RedirectResponse to modify
        message: Toast message text
        toast_type: One of 'success', 'error', 'warning', 'info'
    """
    import json
    response.headers["HX-Trigger"] = json.dumps({
        "showToast": {"message": message, "type": toast_type}
    })
    return response
```

**Client-side listener (in base.html):**

The toast container lives in `base.html` so it's available on every page. HTMX fires a custom event when it sees the `HX-Trigger` header, and our JS listener creates the toast DOM element.

**For POST-then-redirect flows (303 pattern):**

Most Calloway console actions use POST -> 303 redirect -> GET. The `HX-Trigger` header on a redirect response is lost because the browser follows the redirect. Two solutions:

**Option A (Recommended): Flash-style session cookie**

```python
def _toast_redirect(url: str, message: str, toast_type: str = "success") -> RedirectResponse:
    """Redirect with a toast message stored in a flash cookie."""
    response = RedirectResponse(url, status_code=303)
    import json
    response.set_cookie(
        "_toast",
        json.dumps({"message": message, "type": toast_type}),
        max_age=10,  # expires quickly
        httponly=False,  # JS needs to read it
        samesite="strict",
    )
    return response
```

The JS on page load checks for the `_toast` cookie, shows the toast, and deletes the cookie.

**Option B: Convert to HTMX requests**

Change form submissions to use `hx-post` instead of native `<form method="post">`, which allows the server to return an OOB swap directly. This is preferred for new features but requires touching existing templates.

### Toast Inventory

Every action in the console that produces a side effect needs toast feedback. Audited from `console.py` routes and all templates:

#### Tenant Management

| # | Action | Route | Current Behavior | Toast Type | Message |
|---|--------|-------|-----------------|------------|---------|
| 1 | Create customer (quick form) | `POST /tenants/new` | Redirect to detail (no feedback) | Success | "Customer created successfully" |
| 2 | Create customer (quick form) — validation fail | `POST /tenants/new` | Re-renders form with `error` div | Error | (Keep existing inline error — no toast needed) |
| 3 | Update customer settings | `POST /tenants/{id}/edit` | Redirect to detail (no feedback) | Success | "Settings saved" |
| 4 | Update customer — validation fail | `POST /tenants/{id}/edit` | Re-renders form with `error` div | Error | (Keep existing inline error — no toast needed) |
| 5 | Deactivate customer | `POST /tenants/{id}/deactivate` | Redirect to detail (no feedback) | Warning | "Customer deactivated. All AI responses and automations are paused." |
| 6 | Send test SMS | `POST /tenants/{id}/test-sms` | Redirect to detail (no feedback) | Success | "Test SMS sent" |
| 7 | Send test SMS — failure | `POST /tenants/{id}/test-sms` | Redirect to detail (error silently logged) | Error | "Test SMS failed. Check Twilio configuration." |

#### Onboarding Wizard

| # | Action | Route | Current Behavior | Toast Type | Message |
|---|--------|-------|-----------------|------------|---------|
| 8 | Complete onboarding | `POST /onboard` | Redirects to success page | (No toast — success page is the feedback) | N/A |
| 9 | Onboarding — validation fail | `POST /onboard` | Re-renders wizard with `error` div | Error | (Keep existing inline error) |

#### Triggers / Automations

| # | Action | Route | Current Behavior | Toast Type | Message |
|---|--------|-------|-----------------|------------|---------|
| 10 | Retry failed trigger | `POST /triggers/{id}/retry` | Redirect to list (no feedback) | Success | "Automation queued for retry" |
| 11 | Cancel trigger | `POST /triggers/{id}/cancel` | Redirect to list (no feedback) | Success | "Automation cancelled" |
| 12 | Fire trigger now | `POST /triggers/{id}/fire-now` | Redirect to list (no feedback) | Warning | "Automation fired. A real message will be sent." |

#### Billing

| # | Action | Route | Current Behavior | Toast Type | Message |
|---|--------|-------|-----------------|------------|---------|
| 13 | Change plan | `POST /billing/{id}/change-plan` | Redirect to billing (no feedback) | Success | "Plan changed to {tier}" |
| 14 | Change plan — failure | `POST /billing/{id}/change-plan` | Redirect to billing (error silently logged) | Error | "Plan change failed. Check logs." |
| 15 | Cancel subscription | `POST /billing/{id}/cancel` | Redirect to billing (no feedback) | Warning | "Subscription will cancel at period end" |
| 16 | Cancel subscription — failure | `POST /billing/{id}/cancel` | Redirect to billing (error silently logged) | Error | "Cancellation failed. Check logs." |

#### System Health

| # | Action | Route | Current Behavior | Toast Type | Message |
|---|--------|-------|-----------------|------------|---------|
| 17 | Run manual daily scan | `POST /health/run-scan/{id}` | Redirect to health (no feedback) | Success | "Daily check started for {name}" |

#### Knowledge Base

| # | Action | Route | Current Behavior | Toast Type | Message |
|---|--------|-------|-----------------|------------|---------|
| 18 | Remove KB item | `POST /tenants/{id}/kb/{type}/{sid}/remove` | Redirect (no feedback) | Success | "Knowledge base item removed" |
| 19 | Remove KB item — failure | Same | Redirect (error silently logged) | Error | "Failed to remove knowledge base item" |
| 20 | Re-index KB item | `POST /tenants/{id}/kb/{type}/{sid}/reindex` | Redirect (no feedback) | Success | "Re-indexing complete ({n} chunks)" |
| 21 | Re-index KB item — failure | Same | Redirect (error silently logged) | Error | "Re-indexing failed" |
| 22 | Set KB expiration | `POST /tenants/{id}/kb/{type}/{sid}/expire` | Redirect (no feedback) | Success | "Expiration date updated" |
| 23 | Set KB expiration — invalid date | Same | Returns 400 plaintext | Error | "Expiration date must be in the future" |
| 24 | Update KB settings | `POST /tenants/{id}/kb/settings` | Redirect (no feedback) | Success | "Knowledge base settings saved" |
| 25 | Upload KB document | `POST /tenants/{id}/kb/upload` | Redirect (no feedback) | Success | "Document uploaded ({n} chunks indexed)" |
| 26 | Upload KB document — failure | Same | Returns 400/500 plaintext | Error | "Document upload failed" |

#### Authentication

| # | Action | Route | Current Behavior | Toast Type | Message |
|---|--------|-------|-----------------|------------|---------|
| 27 | Login — invalid password | `POST /login` | Re-renders with `error` | Error | (Keep existing inline error — login is a special page without base.html toast container) |

### Implementation: HTML

Add to `base.html`, just before the closing `</body>` tag:

```html
<!-- Toast Notification Container -->
<div id="toast-container" class="toast-container" aria-live="polite" aria-atomic="false" role="status">
    <!-- Toasts are injected here dynamically -->
</div>
```

Individual toast HTML structure (generated by JS):

```html
<div class="toast toast-success toast-enter" role="alert" aria-live="assertive">
    <div class="toast-icon" aria-hidden="true">
        <!-- SVG icon inline -->
    </div>
    <div class="toast-content">
        <p class="toast-message">Settings saved</p>
    </div>
    <button class="toast-close" aria-label="Dismiss notification" type="button">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M1 1l12 12M13 1L1 13"/>
        </svg>
    </button>
</div>
```

### Implementation: CSS

```css
/* ============================================================
   Toast Notifications
   ============================================================ */

.toast-container {
    position: fixed;
    top: 24px;
    right: 24px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 8px;
    pointer-events: none;
    max-width: 400px;
}

.toast {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    min-width: 280px;
    max-width: 360px;
    padding: 14px 16px 14px 14px;
    border-radius: 8px;
    border-left: 3px solid transparent;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4), 0 1px 4px rgba(0, 0, 0, 0.2);
    pointer-events: auto;
    opacity: 0;
    transform: translateX(24px);
    transition: opacity 200ms ease-out, transform 200ms ease-out;
}

.toast.toast-visible {
    opacity: 1;
    transform: translateX(0);
}

.toast.toast-exit {
    opacity: 0;
    transform: translateX(24px);
    transition: opacity 150ms ease-in, transform 150ms ease-in;
}

/* Type variants */
.toast-success {
    background: rgba(30, 215, 96, 0.12);
    border-left-color: var(--green);
}

.toast-error {
    background: rgba(233, 20, 41, 0.12);
    border-left-color: var(--red);
}

.toast-warning {
    background: rgba(255, 164, 43, 0.12);
    border-left-color: var(--yellow);
}

.toast-info {
    background: rgba(30, 215, 96, 0.08);
    border-left-color: var(--border);
}

/* Icon */
.toast-icon {
    flex-shrink: 0;
    width: 16px;
    height: 16px;
    margin-top: 1px;
}

.toast-success .toast-icon { color: var(--green); }
.toast-error .toast-icon { color: var(--red); }
.toast-warning .toast-icon { color: var(--yellow); }
.toast-info .toast-icon { color: var(--text-muted); }

/* Content */
.toast-content {
    flex: 1;
    min-width: 0;
}

.toast-message {
    font-size: 13px;
    line-height: 1.4;
    color: var(--text);
    margin: 0;
}

/* Close button */
.toast-close {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    padding: 0;
    background: none;
    border: none;
    border-radius: 4px;
    color: var(--text-muted);
    cursor: pointer;
    transition: color 0.15s, background 0.15s;
    margin-top: -2px;
    margin-right: -4px;
}

.toast-close:hover {
    color: var(--text);
    background: rgba(255, 255, 255, 0.08);
}

.toast-close:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
    .toast {
        transition: none;
        transform: none;
    }
    .toast.toast-visible {
        transform: none;
    }
    .toast.toast-exit {
        transform: none;
        transition: opacity 100ms ease-in;
    }
}

/* Mobile */
@media (max-width: 768px) {
    .toast-container {
        top: auto;
        bottom: 16px;
        right: 16px;
        left: 16px;
        max-width: none;
    }
    .toast {
        max-width: none;
        min-width: 0;
    }
}
```

### Implementation: JavaScript

Add to `base.html`, after the toast container div:

```html
<script>
/* ============================================================
   Toast Notification Controller
   ============================================================ */
(function() {
    var container = document.getElementById('toast-container');
    var MAX_TOASTS = 4;
    var DURATIONS = { success: 4000, info: 5000, warning: 6000, error: 0 };

    var ICONS = {
        success: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M5 8l2 2 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        error:   '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        warning: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1.5l6.5 12H1.5L8 1.5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 6.5v3M8 11.5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        info:    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M8 7v4M8 5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'
    };

    function showToast(message, type) {
        type = type || 'info';
        if (!ICONS[type]) type = 'info';

        // Enforce max visible toasts
        var existing = container.querySelectorAll('.toast');
        while (existing.length >= MAX_TOASTS) {
            dismissToast(existing[existing.length - 1]);
            existing = container.querySelectorAll('.toast');
        }

        var el = document.createElement('div');
        el.className = 'toast toast-' + type;
        el.setAttribute('role', type === 'error' ? 'alert' : 'status');
        el.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');
        el.innerHTML =
            '<div class="toast-icon" aria-hidden="true">' + ICONS[type] + '</div>' +
            '<div class="toast-content"><p class="toast-message">' + escapeHtml(message) + '</p></div>' +
            '<button class="toast-close" aria-label="Dismiss notification" type="button">' +
            '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 1l12 12M13 1L1 13"/></svg>' +
            '</button>';

        container.prepend(el);

        // Trigger enter animation on next frame
        requestAnimationFrame(function() {
            el.classList.add('toast-visible');
        });

        // Close button
        el.querySelector('.toast-close').addEventListener('click', function() {
            dismissToast(el);
        });

        // Auto-dismiss
        var duration = DURATIONS[type];
        if (duration > 0) {
            var timer = setTimeout(function() { dismissToast(el); }, duration);

            // Pause on hover
            el.addEventListener('mouseenter', function() { clearTimeout(timer); });
            el.addEventListener('mouseleave', function() {
                timer = setTimeout(function() { dismissToast(el); }, duration);
            });
        }
    }

    function dismissToast(el) {
        if (!el || el.classList.contains('toast-exit')) return;
        el.classList.remove('toast-visible');
        el.classList.add('toast-exit');
        setTimeout(function() { el.remove(); }, 200);
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Keyboard: Escape dismisses topmost toast
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            var first = container.querySelector('.toast:not(.toast-exit)');
            if (first) dismissToast(first);
        }
    });

    // ---- HTMX Integration ----

    // Listen for HX-Trigger "showToast" events from HTMX responses
    document.body.addEventListener('showToast', function(e) {
        var detail = e.detail || {};
        showToast(detail.message || 'Done', detail.type || 'success');
    });

    // ---- Flash Cookie Integration ----
    // For POST -> 303 redirect flows where HX-Trigger headers are lost

    function checkFlashCookie() {
        var match = document.cookie.match(/(?:^|;\s*)_toast=([^;]*)/);
        if (match) {
            try {
                var data = JSON.parse(decodeURIComponent(match[1]));
                showToast(data.message, data.type);
            } catch(e) { /* ignore malformed cookie */ }
            // Delete the cookie
            document.cookie = '_toast=; path=/; max-age=0; samesite=strict';
        }
    }

    // Check on page load
    checkFlashCookie();

    // Also check after HTMX swaps (for redirects within HTMX requests)
    document.body.addEventListener('htmx:afterSettle', checkFlashCookie);

    // Expose globally for manual use
    window.showToast = showToast;
})();
</script>
```

### Server-Side Helper (Python)

Add to `app/api/console.py`:

```python
import json

def _toast_redirect(url: str, message: str, toast_type: str = "success") -> RedirectResponse:
    """Create a redirect response with a flash toast cookie.

    The client-side JS reads this cookie on page load, shows the toast,
    and immediately deletes the cookie.
    """
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        "_toast",
        json.dumps({"message": message, "type": toast_type}),
        max_age=10,
        httponly=False,
        samesite="strict",
        path="/",
    )
    return response
```

**Usage example — updating an endpoint:**

```python
# Before:
return RedirectResponse(f"/console/tenants/{agent_id}", status_code=303)

# After:
return _toast_redirect(f"/console/tenants/{agent_id}", "Settings saved")
```

```python
# Error case:
return _toast_redirect("/console/billing", "Plan change failed. Check logs.", "error")
```

---

## Part 2: Tooltip System

### Tooltip Types & Visual Spec

| Type | Use Case | Styling | Trigger |
|------|----------|---------|---------|
| **Help** | Explain what a button/field does | Standard dark tooltip | Hover / Focus |
| **Data** | Show full text for truncated content | Slightly wider, mono font | Hover / Focus |
| **Status** | Explain what a status badge means | Standard, with colored left-border matching badge | Hover / Focus |

**Visual Dimensions (all types):**
- Background: `#282828` (matches `--bg-hover`)
- Color: `var(--text)` (#FFFFFF)
- Border: `1px solid var(--border)` (#333333)
- Border-radius: `6px`
- Padding: `8px 12px`
- Font size: `12px`, line-height `1.4`
- Max width: `280px` (help/status), `360px` (data)
- Box shadow: `0 4px 16px rgba(0, 0, 0, 0.3)`
- Arrow: `6px` CSS triangle, matches background color
- Delay before show: `300ms` (prevents flicker on accidental hover)
- Fade-in: `150ms`

### Tooltip Behavior

| Property | Value |
|----------|-------|
| **Trigger (mouse)** | Hover with 300ms delay. Disappears immediately on mouse leave. |
| **Trigger (keyboard)** | Shows on `focus` (no delay). Hides on `blur`. |
| **Trigger (touch)** | Tap to toggle. Tap outside to dismiss. |
| **Position** | Default: above the element. Auto-flips to below if insufficient viewport space above. |
| **Content source** | `data-tooltip` attribute on the element |
| **Tooltip type** | `data-tooltip-type` attribute: `"help"` (default), `"data"`, `"status"` |
| **Accessibility** | Each tooltip target gets `aria-describedby` pointing to a generated tooltip ID |
| **Reduced motion** | No fade, instant show/hide |

### Tooltip Inventory

Audited from every template. Only elements that genuinely need explanatory tooltips are listed. Existing `title` attributes on elements will be migrated to `data-tooltip` attributes.

#### Dashboard (`dashboard.html`)

| # | Element | Current | Tooltip Type | Tooltip Text |
|---|---------|---------|-------------|-------------|
| 1 | Active Customers card | `title` attr | Help | "Registered real estate agent accounts currently active in the system" |
| 2 | Messages Today card | `title` attr | Help | "Total messages sent and received since midnight (server time)" |
| 3 | Messages 24h card | `title` attr | Help | "Total messages in the last 24-hour rolling window" |
| 4 | Errors 24h card | `title` attr | Help | "Integration and system errors in the last 24 hours" |
| 5 | AI Cost Today card | `title` attr | Help | "Estimated AI spend today across all customers" |
| 6 | Health status dot (topbar) | `title` attr | Status | "System health indicator. Green = all services healthy. Yellow = degraded. Red = outage." |

#### Tenants List (`tenants.html`)

No tooltips needed beyond column headers (already using `title` attrs on `<th>`).

#### Tenant Detail (`tenant_detail.html`)

| # | Element | Tooltip Type | Tooltip Text |
|---|---------|-------------|-------------|
| 7 | Status badge (available/deactivated) | Status | "Available = AI is active and responding. Deactivated = all AI and automations paused." |
| 8 | "Edit Settings" button | Help | "Edit profile, tone, autonomy level, and scheduling preferences" |
| 9 | "Test SMS" button | Help | "Send a test SMS to verify the Twilio number is configured correctly" |
| 10 | "Deactivate" button | Help | "Stops all AI responses and scheduled automations for this customer" |
| 11 | Cost card | Help | "Estimated AI cost for this customer this month" |
| 12 | Messages card | Help | "Total messages sent and received this month" |
| 13 | Errors 24h card | Help | "Errors in the last 24 hours for this customer" |
| 14 | Twilio # row | Help | "The Twilio number contacts text to reach this agent" |
| 15 | Consent "revoked" badge | Status | "TCPA consent revoked. No automated messages can be sent to this contact." |
| 16 | Consent "granted" badge | Status | "Contact has given consent to receive automated messages" |
| 17 | Consent "pending" badge | Status | "Consent not yet confirmed. Automated messaging limited." |
| 18 | Silent mode "Yes" | Status | "Automated messaging is paused for this contact" |

#### Tenant Edit (`tenant_edit.html`)

| # | Element | Tooltip Type | Tooltip Text |
|---|---------|-------------|-------------|
| 19 | Timezone select | Help | "Used for scheduling automations and daily briefings in the agent's local time" |
| 20 | Tone select | Help | "Controls the AI's communication style: Professional, Friendly, or Casual" |
| 21 | Autonomy Level select | Help | "Supervised = AI drafts, agent approves. Autonomous = AI sends directly. Manual = agent triggers manually." |
| 22 | Briefing Time input | Help | "Time of day for the daily briefing summary, in the agent's timezone" |
| 23 | System Prompt Override textarea | Help | "Custom instructions that override the default AI behavior. Leave blank to use defaults." |

#### Triggers (`triggers.html`)

| # | Element | Tooltip Type | Tooltip Text |
|---|---------|-------------|-------------|
| 24 | Status "pending" badge | Status | "Waiting to execute at the scheduled time" |
| 25 | Status "completed" badge | Status | "Successfully executed" |
| 26 | Status "error" badge | Status | "Failed to execute. Can be retried." |
| 27 | Status "cancelled" badge | Status | "Manually cancelled by operator" |
| 28 | "Run Now" button | Help | "Execute this automation immediately. A real message will be sent to the contact." |
| 29 | "Cancel" button | Help | "Cancel this automation. It will not run." |
| 30 | "Retry" button | Help | "Queue this failed automation for another attempt" |
| 31 | Autonomy column values | Help | "Supervised = requires approval. Autonomous = sends automatically." |

#### Billing (`billing.html`)

| # | Element | Tooltip Type | Tooltip Text |
|---|---------|-------------|-------------|
| 32 | Message usage bar (>90%) | Status | "This customer is near their monthly message limit" |
| 33 | "canceling" badge | Status | "Subscription will end at the current billing period" |
| 34 | "past due" badge | Status | "Payment failed. Subscription at risk of cancellation." |
| 35 | "trial" badge | Status | "Customer is on a free trial period" |
| 36 | Model tier "template" badge | Help | "Pre-built message templates. No AI cost." |
| 37 | Model tier "haiku" badge | Help | "Fast, low-cost AI model for simple tasks" |
| 38 | Model tier "sonnet" badge | Help | "More capable AI model for complex reasoning. Higher cost." |
| 39 | Cost column (red, >$15) | Status | "Cost exceeds the $15/month threshold" |

#### Health (`health.html`)

| # | Element | Tooltip Type | Tooltip Text |
|---|---------|-------------|-------------|
| 40 | Service status green dot | Status | "Service is healthy and responding normally" |
| 41 | Service status yellow dot | Status | "Service is degraded. Responses may be slower than normal." |
| 42 | Service status red dot | Status | "Service is unreachable or returning errors" |
| 43 | Avg Response Time card | Help | "Average end-to-end time from receiving a message to sending a response" |
| 44 | Median card | Help | "50th percentile. Half of all requests are faster than this." |
| 45 | Slowest 5% card | Help | "95th percentile. Only 5% of requests are slower than this." |
| 46 | "Run Check" button | Help | "Run the daily health and follow-up check immediately for the selected customer" |

#### Knowledge Base (`knowledge_base.html`)

| # | Element | Tooltip Type | Tooltip Text |
|---|---------|-------------|-------------|
| 47 | Default expiration select | Help | "Automatically set an expiration date on new knowledge base items" |
| 48 | Behavior select | Help | "Remind only = shows warnings. Auto-remove = deletes expired items automatically." |
| 49 | "Expired" badge | Status | "This item has expired and may contain outdated information" |
| 50 | "Expiring Soon" badge | Status | "This item expires within 7 days" |
| 51 | "Active" badge | Status | "This item is current and available for AI retrieval" |
| 52 | "Remove" button | Help | "Delete all embedding chunks. The AI will no longer use this information." |
| 53 | "Re-index" button | Help | "Re-read the source record and regenerate embeddings" |
| 54 | Chunk count | Data | "Number of text segments this item was split into for AI retrieval" |

#### Conversations (`conversations.html`)

| # | Element | Tooltip Type | Tooltip Text |
|---|---------|-------------|-------------|
| 55 | Last Message column (truncated) | Data | (Show full message text on hover) |
| 56 | Channel badge | Help | "sms = text message, rcs = rich messaging, vapi = voice call, email = email" |

### Implementation: HTML

**Pattern 1: Simple tooltip (attribute-based, CSS-only)**

```html
<!-- Before -->
<button class="btn btn-outline btn-sm" title="Send a test SMS...">Test SMS</button>

<!-- After -->
<button class="btn btn-outline btn-sm"
        data-tooltip="Send a test SMS to verify the Twilio number is configured correctly"
        data-tooltip-pos="bottom">Test SMS</button>
```

**Pattern 2: Status tooltip (with colored indicator)**

```html
<span class="badge badge-green"
      data-tooltip="Contact has given consent to receive automated messages"
      data-tooltip-type="status">granted</span>
```

**Pattern 3: Data tooltip (for truncated content)**

```html
<td data-tooltip="{{ c.last_message }}"
    data-tooltip-type="data"
    style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
    {{ (c.last_message or '')[:80] }}
</td>
```

### Implementation: CSS

```css
/* ============================================================
   Tooltip System
   ============================================================ */

/* Base tooltip via pseudo-element */
[data-tooltip] {
    position: relative;
    cursor: help;
}

/* Tooltip bubble */
[data-tooltip]::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    padding: 8px 12px;
    background: #282828;
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 12px;
    line-height: 1.4;
    font-weight: 400;
    text-transform: none;
    letter-spacing: normal;
    white-space: normal;
    max-width: 280px;
    width: max-content;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    z-index: 9998;
    pointer-events: none;
    opacity: 0;
    transition: opacity 150ms ease-out;

    /* Delay before showing */
    transition-delay: 0ms;
}

/* Arrow */
[data-tooltip]::before {
    content: '';
    position: absolute;
    bottom: calc(100% + 2px);
    left: 50%;
    transform: translateX(-50%);
    border: 6px solid transparent;
    border-top-color: #282828;
    z-index: 9998;
    pointer-events: none;
    opacity: 0;
    transition: opacity 150ms ease-out;
    transition-delay: 0ms;
}

/* Show on hover with delay */
[data-tooltip]:hover::after,
[data-tooltip]:hover::before {
    opacity: 1;
    transition-delay: 300ms;
}

/* Show on focus (no delay, for keyboard users) */
[data-tooltip]:focus-visible::after,
[data-tooltip]:focus-visible::before {
    opacity: 1;
    transition-delay: 0ms;
}

/* Bottom position variant */
[data-tooltip-pos="bottom"]::after {
    bottom: auto;
    top: calc(100% + 8px);
}

[data-tooltip-pos="bottom"]::before {
    bottom: auto;
    top: calc(100% + 2px);
    border-top-color: transparent;
    border-bottom-color: #282828;
}

/* Left position variant */
[data-tooltip-pos="left"]::after {
    bottom: auto;
    top: 50%;
    left: auto;
    right: calc(100% + 8px);
    transform: translateY(-50%);
}

[data-tooltip-pos="left"]::before {
    bottom: auto;
    top: 50%;
    left: auto;
    right: calc(100% + 2px);
    transform: translateY(-50%);
    border-top-color: transparent;
    border-right-color: transparent;
    border-left-color: #282828;
}

/* Right position variant */
[data-tooltip-pos="right"]::after {
    bottom: auto;
    top: 50%;
    left: calc(100% + 8px);
    transform: translateY(-50%);
}

[data-tooltip-pos="right"]::before {
    bottom: auto;
    top: 50%;
    left: calc(100% + 2px);
    transform: translateY(-50%);
    border-top-color: transparent;
    border-left-color: transparent;
    border-right-color: #282828;
}

/* Data tooltip type — wider, mono font for content */
[data-tooltip-type="data"]::after {
    max-width: 360px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
}

/* Status tooltip type — colored left border matching nearest badge */
[data-tooltip-type="status"]::after {
    border-left: 3px solid var(--text-muted);
}

.badge-green[data-tooltip-type="status"]::after { border-left-color: var(--green); }
.badge-yellow[data-tooltip-type="status"]::after { border-left-color: var(--yellow); }
.badge-red[data-tooltip-type="status"]::after { border-left-color: var(--red); }
.badge-blue[data-tooltip-type="status"]::after { border-left-color: var(--accent); }
.badge-gray[data-tooltip-type="status"]::after { border-left-color: var(--text-muted); }

/* Button elements: override cursor */
button[data-tooltip],
.btn[data-tooltip],
a[data-tooltip] {
    cursor: pointer;
}

/* Ensure tooltips on inline elements work */
[data-tooltip] {
    display: inline-block;
}

/* Table cells: don't force inline-block */
td[data-tooltip],
th[data-tooltip] {
    display: table-cell;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
    [data-tooltip]::after,
    [data-tooltip]::before {
        transition: none;
    }
}

/* Mobile: disable hover tooltips (use tap interaction via JS) */
@media (hover: none) {
    [data-tooltip]::after,
    [data-tooltip]::before {
        display: none;
    }
    [data-tooltip].tooltip-active::after,
    [data-tooltip].tooltip-active::before {
        display: block;
        opacity: 1;
    }
}
```

**Mobile touch support (add to base.html JS):**

```html
<script>
/* Tooltip: tap-to-show on touch devices */
(function() {
    if (!window.matchMedia('(hover: none)').matches) return;

    document.addEventListener('click', function(e) {
        var target = e.target.closest('[data-tooltip]');
        // Close all other active tooltips
        document.querySelectorAll('.tooltip-active').forEach(function(el) {
            if (el !== target) el.classList.remove('tooltip-active');
        });
        // Toggle the tapped tooltip
        if (target) {
            e.preventDefault();
            target.classList.toggle('tooltip-active');
        }
    });
})();
</script>
```

---

## Accessibility Checklist

### Toasts
- [x] Toast container uses `aria-live="polite"` for non-error toasts
- [x] Error toasts use `role="alert"` and `aria-live="assertive"`
- [x] Close button has `aria-label="Dismiss notification"`
- [x] Escape key dismisses topmost toast
- [x] Close button is keyboard-focusable
- [x] `prefers-reduced-motion` respected — no slide animation
- [x] Color is not the only indicator — icon shape differentiates toast types
- [x] Text meets WCAG AA contrast on dark backgrounds

### Tooltips
- [x] Help tooltips use `cursor: help` to indicate interactivity
- [x] Keyboard users see tooltips via `:focus-visible`
- [x] Touch devices use tap-to-show pattern
- [x] `prefers-reduced-motion` respected — instant show/hide
- [x] Tooltip text contrasts at 4.5:1+ against tooltip background
- [x] Max-width prevents tooltips from becoming unreadably wide
- [x] Tooltips do not obscure the element they describe (positioned above by default)

### Migration Notes
- All existing `title` attributes on interactive elements should be migrated to `data-tooltip` during implementation. The `title` attribute has poor accessibility (inconsistent screen reader support, no keyboard trigger, no styling control).
- Remove `title` attributes after adding `data-tooltip` to avoid double-announcing in screen readers.

---

## Implementation Checklist for Engineering

1. **Add toast CSS** to `app/static/console/style.css`
2. **Add tooltip CSS** to `app/static/console/style.css`
3. **Add toast container + JS** to `app/templates/console/base.html`
4. **Add mobile tooltip JS** to `app/templates/console/base.html`
5. **Add `_toast_redirect` helper** to `app/api/console.py`
6. **Update all 17 POST endpoints** in `console.py` to use `_toast_redirect` (see Toast Inventory)
7. **Migrate `title` attrs to `data-tooltip`** in all templates (56 tooltip locations identified)
8. **Bump CSS cache buster** in `base.html`: `style.css?v=2` -> `style.css?v=3`
9. **Test** all toast scenarios (success, error, warning, auto-dismiss, stacking, cookie cleanup)
10. **Test** tooltip positioning on all pages, especially near viewport edges
11. **Test** keyboard navigation (Tab to tooltip targets, Escape for toasts)
12. **Test** mobile behavior (touch tooltips, bottom-positioned toasts)
