# Empty States, Loading States & Error States -- Design Specification

**Author:** Lyra, Product Designer
**Date:** 2026-03-14
**Status:** Design Complete -- Ready for Engineering

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Part 1: Empty State Audit & Design](#part-1-empty-state-audit--design)
3. [Part 2: Loading State Design](#part-2-loading-state-design)
4. [Part 3: Error State Design](#part-3-error-state-design)
5. [Reusable Components: HTML & CSS](#reusable-components-html--css)
6. [Accessibility Requirements](#accessibility-requirements)
7. [Implementation Checklist](#implementation-checklist)

---

## Design Philosophy

Every screen has four states: **loaded**, **empty**, **loading**, and **error**. The loaded state gets all the attention. The other three determine whether users trust the product.

**Principles:**

- **Empty states are onboarding moments.** They should explain what belongs here and how to get started -- not just say "no data."
- **Loading states preserve layout.** Skeleton screens prevent content shift and signal that something is happening. They match the shape of the data that will appear.
- **Error states are recoverable.** Every error offers a next step: retry, go back, or contact support.
- **Tone is warm and human.** "No conversations yet" not "0 records found." "Something went wrong" not "500 Internal Server Error."
- **Accessibility is non-negotiable.** Skeleton animations respect `prefers-reduced-motion`. Error messages are announced via `aria-live`. Icons have `aria-hidden="true"` with text alternatives always present.

---

## Part 1: Empty State Audit & Design

### 1.1 Dashboard (`dashboard.html`)

#### Needs Attention Sidebar -- No Issues

**Current behavior:** Shows "All clear." in muted text.
**Verdict:** This is a *positive* empty state (no problems found). Current text is too terse.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#10003;` (checkmark) |
| Headline | All systems clear |
| Description | No customers need attention right now. Errors and inactive accounts will surface here automatically. |
| CTA | None |

```html
<div class="empty-state empty-state--positive">
    <div class="empty-state__icon" aria-hidden="true">&#10003;</div>
    <div class="empty-state__headline">All systems clear</div>
    <div class="empty-state__description">No customers need attention right now. Errors and inactive accounts will surface here automatically.</div>
</div>
```

#### Activity Feed -- No Activity

**Current behavior:** Shows "No recent activity." in a feed-item div.
**Verdict:** Adequate text but no visual weight. Feels like broken content.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#9729;` (cloud) |
| Headline | No activity yet |
| Description | Messages will stream here in real time once your customers start texting. The feed refreshes every 15 seconds. |
| CTA | None (auto-refreshes) |

```html
<div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">&#9729;</div>
    <div class="empty-state__headline">No activity yet</div>
    <div class="empty-state__description">Messages will stream here in real time once your customers start texting. The feed refreshes every 15 seconds.</div>
</div>
```

#### Dashboard -- Zero Stat Cards

**Current behavior:** Cards show `0` values. Not technically empty -- they render the number zero.
**Verdict:** Acceptable. Zero is a valid data point for stat cards. No change needed. However, if `pulse` fails entirely, a component-level error should replace the card grid (see Part 3).

---

### 1.2 Customer List (`tenants.html`)

#### No Customers (Empty Table)

**Current behavior:** Shows "No customers found." in a single table cell with muted text.
**Verdict:** Minimal and unhelpful. Doesn't guide the user to create their first customer.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#9830;` (diamond -- matches nav icon) |
| Headline | No customers yet |
| Description | Add your first real estate agent to get started. You can onboard them step-by-step with the setup wizard. |
| CTA | `+ New Customer` (links to `/console/tenants/new`) |

```html
{% if not agents %}
<div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">&#9830;</div>
    <div class="empty-state__headline">No customers yet</div>
    <div class="empty-state__description">Add your first real estate agent to get started. You can onboard them step-by-step with the setup wizard.</div>
    <a href="/console/tenants/new" class="btn btn-primary empty-state__cta">+ New Customer</a>
</div>
{% endif %}
```

**Note:** Replace the current `<tr><td colspan="9">` approach. When the table is empty, hide the entire `<table>` and show this empty state instead.

#### No Search Results (Filtered to Zero)

**Current behavior:** Same "No customers found." message.
**Verdict:** Indistinguishable from "no data at all." Needs a different message.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#128269;` (magnifying glass) |
| Headline | No matches found |
| Description | No customers match your search. Try a different name or market. |
| CTA | `Clear Search` (resets form) |

```html
{% if search and not agents %}
<div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">&#128269;</div>
    <div class="empty-state__headline">No matches found</div>
    <div class="empty-state__description">No customers match "{{ search }}". Try a different name or market.</div>
    <a href="/console/tenants" class="btn btn-outline empty-state__cta">Clear Search</a>
</div>
{% endif %}
```

---

### 1.3 Customer Detail (`tenant_detail.html`)

#### Messages Tab -- No Conversations

**Current behavior:** (via `messages_contacts.html` partial) Shows a centered empty state with envelope icon, title, and description.
**Verdict:** Already well-designed. One improvement: add a CTA button to send a test SMS.

**Designed empty state (enhancement):**

| Element | Content |
|---------|---------|
| Icon | `&#9993;` (envelope -- existing) |
| Headline | No conversations yet |
| Description | Conversations will appear here once contacts start texting. Send a test SMS to verify the connection is working. |
| CTA | `Send Test SMS` (triggers test-sms POST) |

```html
<div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">&#9993;</div>
    <div class="empty-state__headline">No conversations yet</div>
    <div class="empty-state__description">Conversations will appear here once contacts start texting. Send a test SMS to verify the connection is working.</div>
    <form method="post" action="/console/tenants/{{ agent_id }}/test-sms" style="display:inline;">
        <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
        <button type="submit" class="btn btn-primary empty-state__cta">Send Test SMS</button>
    </form>
</div>
```

#### Messages Tab -- No Contact Selected (Thread Area)

**Current behavior:** Shows an envelope icon and "Select a contact to view their conversation."
**Verdict:** Good. Keep as-is. The existing `.thread-empty` class handles this well.

#### Contacts Tab -- No Contacts

**Current behavior:** Shows "No contacts yet." in muted centered text.
**Verdict:** No guidance on how contacts appear. Needs improvement.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#128100;` (person silhouette) |
| Headline | No contacts yet |
| Description | Contacts are created automatically when someone texts this customer's Twilio number. You can also add contacts during onboarding. |
| CTA | None |

```html
<div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">&#128100;</div>
    <div class="empty-state__headline">No contacts yet</div>
    <div class="empty-state__description">Contacts are created automatically when someone texts this customer's Twilio number. You can also add contacts during onboarding.</div>
</div>
```

#### Listings Tab -- No Listings

**Current behavior:** Shows "No listings yet." in muted centered text.
**Verdict:** Same problem -- no guidance.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#127968;` (house) |
| Headline | No listings yet |
| Description | Listings are synced from the agent's MLS feed or can be added manually. Once imported, the AI can answer questions about properties automatically. |
| CTA | None |

```html
<div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">&#127968;</div>
    <div class="empty-state__headline">No listings yet</div>
    <div class="empty-state__description">Listings are synced from the agent's MLS feed or can be added manually. Once imported, the AI can answer questions about properties automatically.</div>
</div>
```

#### Automations Tab -- No Automations

**Current behavior:** Shows "No scheduled automations." in muted centered text.
**Verdict:** Needs context about how automations are created.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#8635;` (refresh arrow) |
| Headline | No scheduled automations |
| Description | Automations are created automatically by the AI -- follow-ups, reminders, review requests, and daily briefings. They will appear here once conversations start flowing. |
| CTA | None |

```html
<div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">&#8635;</div>
    <div class="empty-state__headline">No scheduled automations</div>
    <div class="empty-state__description">Automations are created automatically by the AI -- follow-ups, reminders, review requests, and daily briefings. They will appear here once conversations start flowing.</div>
</div>
```

#### Knowledge Base Tab -- No Items

**Current behavior:** (via `knowledge_base.html` partial) Shows a custom empty state with icon, title, and description.
**Verdict:** Already well-designed. Keep as-is. Uses `.messages-empty` class (should be renamed to `.empty-state` for consistency).

---

### 1.4 Conversations List (`conversations.html`)

#### No Conversations

**Current behavior:** Shows "No conversations found." in a table cell.
**Verdict:** Same problem as customers table.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#9993;` (envelope) |
| Headline | No conversations yet |
| Description | Conversations appear here when contacts text your customers' Twilio numbers. Once messages start flowing, you can search, filter, and drill into any thread. |
| CTA | None |

#### No Conversations After Filtering

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#128269;` (magnifying glass) |
| Headline | No conversations match your filters |
| Description | Try adjusting the customer, channel, or search filters. |
| CTA | `Clear Filters` (links to `/console/conversations`) |

---

### 1.5 Automations List (`triggers.html`)

#### No Automations

**Current behavior:** Shows "No automations found." in a table cell.
**Verdict:** Needs context.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#8635;` (refresh arrow) |
| Headline | No automations found |
| Description | Automations are scheduled by the AI during conversations -- follow-ups, reminders, and review requests. They will appear here once conversations are active. |
| CTA | None |

#### No Automations After Filtering

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#128269;` (magnifying glass) |
| Headline | No automations match your filters |
| Description | Try selecting a different status or customer. |
| CTA | `Clear Filters` (links to `/console/triggers`) |

---

### 1.6 System Health (`health.html`)

#### Errors Tab -- No Errors (Positive Empty State)

**Current behavior:** Shows "No errors found." in muted centered text.
**Verdict:** This is a *good* empty state. Should feel like a win, not like missing data.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#10003;` (checkmark) |
| Headline | No errors in the last 24 hours |
| Description | All integrations and system components are running smoothly. This page auto-refreshes every 30 seconds. |
| CTA | None |
| Modifier class | `empty-state--positive` (green accent) |

```html
<div class="empty-state empty-state--positive">
    <div class="empty-state__icon" aria-hidden="true">&#10003;</div>
    <div class="empty-state__headline">No errors in the last 24 hours</div>
    <div class="empty-state__description">All integrations and system components are running smoothly. This page auto-refreshes every 30 seconds.</div>
</div>
```

---

### 1.7 Billing (`billing.html`)

#### Subscriptions Tab -- No Subscriptions

**Current behavior:** Shows "No subscriptions yet. Create a subscription when onboarding a new agent, or use the Stripe dashboard directly." in centered muted text.
**Verdict:** Already decent. Needs the standard empty-state component for visual consistency.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#36;` (dollar sign) |
| Headline | No subscriptions yet |
| Description | Subscriptions are created when you onboard a new agent. You can also manage them directly in the Stripe dashboard. |
| CTA | `+ New Agent` (links to `/console/onboard`) |

#### AI Costs Tab -- No Cost Data

**Current behavior:** Shows "No cost data yet." in muted text.
**Verdict:** Needs the standard component.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#9889;` (lightning bolt) |
| Headline | No cost data yet |
| Description | AI cost tracking begins automatically once customers start receiving messages. Usage, tokens, and cost breakdowns will appear here within 24 hours of the first conversation. |
| CTA | None |

---

### 1.8 Conversation Detail (`conversation_detail.html`)

#### No Messages in Thread

**Current behavior:** The messages iterate with `{% for m in detail.messages %}` -- if the list is empty, nothing renders in the chat area.
**Verdict:** Silent failure. Needs an explicit empty state.

**Designed empty state:**

| Element | Content |
|---------|---------|
| Icon | `&#9993;` (envelope) |
| Headline | No messages in this conversation |
| Description | This conversation thread is empty. Messages will appear here once the contact and AI start exchanging texts. |
| CTA | None |

#### No Active Automations Sidebar

**Current behavior:** The `{% if detail.triggers %}` block just doesn't render if empty. The sidebar section disappears entirely.
**Verdict:** Acceptable -- the sidebar section only shows when relevant. No change needed.

---

## Part 2: Loading State Design

### 2.1 Skeleton Loaders

Skeleton loaders replace content placeholders while data is being fetched. They must match the approximate shape and size of the data they represent.

#### Skeleton CSS (already partially exists -- extending)

The existing `.skeleton-row` and `@keyframes shimmer` in `style.css` provide a foundation. We need additional skeleton variants.

**New skeleton variants needed:**

| Variant | Use Case | Dimensions |
|---------|----------|------------|
| `.skeleton-row` | Table rows (existing) | Height: 48px, full width |
| `.skeleton-card` | Stat cards | Height: 80px |
| `.skeleton-text` | Single line of text | Height: 14px, width: 60-80% |
| `.skeleton-text--short` | Short text (labels) | Height: 12px, width: 40% |
| `.skeleton-avatar` | Contact avatars | 32px circle |
| `.skeleton-message` | Chat messages | Height: 60px, width: 70% |
| `.skeleton-bar` | Bar chart bars | Varies |

#### Skeleton for Stat Cards (Dashboard, Customer Detail, Billing)

```html
<div class="card-grid">
    <div class="card skeleton-card" aria-hidden="true">
        <div class="skeleton-text--short"></div>
        <div class="skeleton-text" style="width: 50%; height: 24px; margin-top: 8px;"></div>
    </div>
    <div class="card skeleton-card" aria-hidden="true">
        <div class="skeleton-text--short"></div>
        <div class="skeleton-text" style="width: 50%; height: 24px; margin-top: 8px;"></div>
    </div>
    <div class="card skeleton-card" aria-hidden="true">
        <div class="skeleton-text--short"></div>
        <div class="skeleton-text" style="width: 50%; height: 24px; margin-top: 8px;"></div>
    </div>
</div>
```

#### Skeleton for Table Rows (Customers, Conversations, Triggers, Contacts, Listings)

```html
<div class="loading-skeleton" aria-label="Loading data" role="status">
    <span class="sr-only">Loading...</span>
    <div class="skeleton-row"></div>
    <div class="skeleton-row"></div>
    <div class="skeleton-row"></div>
    <div class="skeleton-row"></div>
    <div class="skeleton-row"></div>
</div>
```

#### Skeleton for Conversation Thread

```html
<div class="loading-skeleton" aria-label="Loading conversation" role="status">
    <span class="sr-only">Loading messages...</span>
    <div class="skeleton-message skeleton-message--left"></div>
    <div class="skeleton-message skeleton-message--right"></div>
    <div class="skeleton-message skeleton-message--left"></div>
    <div class="skeleton-message skeleton-message--right"></div>
</div>
```

#### Skeleton for Activity Feed

```html
<div class="loading-skeleton" aria-label="Loading activity feed" role="status">
    <span class="sr-only">Loading recent activity...</span>
    <div class="skeleton-feed-item"></div>
    <div class="skeleton-feed-item"></div>
    <div class="skeleton-feed-item"></div>
    <div class="skeleton-feed-item"></div>
</div>
```

---

### 2.2 Inline Spinners for Button Actions

For buttons that trigger POST actions (Save, Delete, Retry, Run Now, Test SMS), show an inline spinner and disable the button during the request.

**Pattern using HTMX `hx-indicator` + `hx-disabled-elt`:**

```html
<button type="submit" class="btn btn-primary"
        hx-post="/console/tenants/{{ agent.id }}/edit"
        hx-indicator="#save-spinner"
        hx-disabled-elt="this">
    <span class="btn-spinner htmx-indicator" id="save-spinner" aria-hidden="true"></span>
    <span class="btn-label">Save Changes</span>
</button>
```

For non-HTMX forms (standard POST), use a CSS-only approach:

```html
<button type="submit" class="btn btn-primary" onclick="this.classList.add('btn--loading'); this.disabled=true; this.form.submit();">
    <span class="btn-spinner" aria-hidden="true"></span>
    <span class="btn-label">Save Changes</span>
</button>
```

---

### 2.3 HTMX Indicator Patterns

The existing HTMX indicator pattern in `base.html` (the health status dot) and `tenant_detail.html` (refresh button) should be standardized.

**Standard pattern for any HTMX-loaded panel:**

```html
<div hx-get="/console/some-endpoint"
     hx-trigger="load"
     hx-swap="innerHTML"
     hx-indicator="#panel-loading">
    <!-- Loading indicator (shown during request) -->
    <div id="panel-loading" class="htmx-indicator loading-skeleton" role="status">
        <span class="sr-only">Loading...</span>
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
        <div class="skeleton-row"></div>
    </div>
</div>
```

**Standard pattern for refresh buttons:**

```html
<button class="btn btn-outline btn-sm"
        hx-get="/console/some-endpoint"
        hx-target="#target-container"
        hx-swap="innerHTML"
        hx-indicator="#refresh-spinner">
    <span id="refresh-spinner" class="btn-spinner htmx-indicator" aria-hidden="true"></span>
    <span class="btn-label">&#8635; Refresh</span>
</button>
```

---

### 2.4 Page-Level Loading (Full Content Area)

For initial page loads or full tab transitions, the content area should show a full-page skeleton that matches the page layout.

**Dashboard loading skeleton:**

```html
<!-- Stat cards skeleton -->
<div class="card-grid" aria-hidden="true">
    <div class="card skeleton-card"><div class="skeleton-text--short"></div><div class="skeleton-text" style="width:40%;height:24px;margin-top:8px;"></div></div>
    <div class="card skeleton-card"><div class="skeleton-text--short"></div><div class="skeleton-text" style="width:40%;height:24px;margin-top:8px;"></div></div>
    <div class="card skeleton-card"><div class="skeleton-text--short"></div><div class="skeleton-text" style="width:40%;height:24px;margin-top:8px;"></div></div>
    <div class="card skeleton-card"><div class="skeleton-text--short"></div><div class="skeleton-text" style="width:40%;height:24px;margin-top:8px;"></div></div>
    <div class="card skeleton-card"><div class="skeleton-text--short"></div><div class="skeleton-text" style="width:40%;height:24px;margin-top:8px;"></div></div>
</div>
<!-- Activity feed skeleton -->
<div class="loading-skeleton">
    <div class="skeleton-feed-item"></div>
    <div class="skeleton-feed-item"></div>
    <div class="skeleton-feed-item"></div>
</div>
```

---

## Part 3: Error State Design

### 3.1 Inline Errors (Form Validation)

For field-level validation errors on forms (tenant_edit, tenant_new, onboard_wizard).

**Pattern:**

```html
<div class="form-group {% if errors.name %}form-group--error{% endif %}">
    <label for="name">Name <span class="required">*</span></label>
    <input type="text" id="name" name="name" value="{{ agent.name }}"
           {% if errors.name %}aria-invalid="true" aria-describedby="name-error"{% endif %}>
    {% if errors.name %}
    <div class="form-error" id="name-error" role="alert">{{ errors.name }}</div>
    {% endif %}
</div>
```

**Error messages should be specific:**

| Field | Example Error |
|-------|--------------|
| Name | "Name is required." |
| Email | "Please enter a valid email address." |
| Phone | "Phone must be in E.164 format (e.g. +15551234567)." |
| Twilio # | "This Twilio number is already assigned to another customer." |
| Content (KB) | "Document content is required and must be under 50,000 characters." |

---

### 3.2 Page-Level Errors (API Failures)

For when the entire page fails to load (database down, auth error, server error).

**Pattern:**

```html
<div class="error-state" role="alert">
    <div class="error-state__icon" aria-hidden="true">&#9888;</div>
    <div class="error-state__headline">Something went wrong</div>
    <div class="error-state__description">We couldn't load this page. This is usually temporary -- try refreshing.</div>
    <div class="error-state__actions">
        <button class="btn btn-primary" onclick="window.location.reload()">Refresh Page</button>
        <a href="/console/dashboard" class="btn btn-outline">Back to Dashboard</a>
    </div>
    <div class="error-state__detail">
        <details>
            <summary>Technical details</summary>
            <pre>{{ error_detail }}</pre>
        </details>
    </div>
</div>
```

**Specific page-level error variants:**

| Scenario | Headline | Description |
|----------|----------|-------------|
| Database unreachable | Something went wrong | We're having trouble connecting to the database. This is usually temporary. |
| Auth expired | Session expired | Your session has ended. Please log in again. |
| 404 Not Found | Page not found | The page you're looking for doesn't exist or has been moved. |
| Rate limited | Too many requests | Please wait a moment and try again. |
| Maintenance | We'll be right back | Calloway is undergoing scheduled maintenance. |

---

### 3.3 Component-Level Errors

For when a single widget fails while the rest of the page works (e.g., activity feed fails but stat cards load).

**Pattern (HTMX swap target receives error HTML):**

```html
<div class="component-error" role="alert" aria-live="polite">
    <div class="component-error__message">
        <span class="component-error__icon" aria-hidden="true">&#9888;</span>
        Couldn't load this section.
    </div>
    <button class="btn btn-outline btn-sm"
            hx-get="/console/dashboard/activity-feed"
            hx-target="#activity-feed"
            hx-swap="innerHTML">
        Retry
    </button>
</div>
```

**Component-level error for specific widgets:**

| Component | Error Message |
|-----------|---------------|
| Activity Feed | Couldn't load the activity feed. |
| Messages Tab (contact list) | Couldn't load conversations for this customer. |
| Messages Tab (thread) | Couldn't load this conversation thread. |
| Knowledge Base Tab | Couldn't load the knowledge base. |
| Health Status Dot | (silently fails -- shows yellow dot as "unknown") |
| Bar Chart | Couldn't load cost chart data. |

---

### 3.4 Retry Patterns with HTMX

For any HTMX request that fails, the server should return an error partial that includes a retry button pointing to the same endpoint.

**Server-side pattern (FastAPI handler):**

When an HTMX endpoint fails, return a 200 response with error HTML instead of a 500 (so HTMX swaps it in):

```python
@app.get("/console/dashboard/activity-feed")
async def activity_feed(request: Request):
    try:
        activity = await get_recent_activity()
        return templates.TemplateResponse(
            "console/partials/activity_feed.html",
            {"request": request, "activity": activity}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "console/partials/component_error.html",
            {
                "request": request,
                "message": "Couldn't load the activity feed.",
                "retry_url": "/console/dashboard/activity-feed",
                "retry_target": "#activity-feed",
            }
        )
```

**Component error partial (`partials/component_error.html`):**

```html
<div class="component-error" role="alert" aria-live="polite">
    <div class="component-error__message">
        <span class="component-error__icon" aria-hidden="true">&#9888;</span>
        {{ message }}
    </div>
    <button class="btn btn-outline btn-sm"
            hx-get="{{ retry_url }}"
            hx-target="{{ retry_target }}"
            hx-swap="innerHTML">
        Retry
    </button>
</div>
```

---

### 3.5 Toast Notifications for Action Results

For POST actions (save, delete, cancel, retry, test SMS) that succeed or fail, show a toast notification.

**Pattern (append to body via HTMX `hx-swap="afterbegin"` on a toast container):**

```html
<!-- Toast container (in base.html) -->
<div id="toast-container" aria-live="polite" aria-atomic="true"></div>

<!-- Success toast (returned by server) -->
<div class="toast toast--success" role="status">
    <span class="toast__icon" aria-hidden="true">&#10003;</span>
    <span class="toast__message">Changes saved successfully.</span>
</div>

<!-- Error toast (returned by server) -->
<div class="toast toast--error" role="alert">
    <span class="toast__icon" aria-hidden="true">&#9888;</span>
    <span class="toast__message">Failed to save changes. Please try again.</span>
</div>
```

---

## Reusable Components: HTML & CSS

### Complete CSS -- Add to `style.css`

```css
/* ============================================================
   Empty States
   ============================================================ */
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 24px;
    text-align: center;
    gap: 12px;
}

.empty-state__icon {
    font-size: 40px;
    opacity: 0.4;
    line-height: 1;
}

.empty-state__headline {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
}

.empty-state__description {
    font-size: 14px;
    color: var(--text-muted);
    max-width: 360px;
    line-height: 1.5;
}

.empty-state__cta {
    margin-top: 8px;
}

/* Positive empty state (no errors = good news) */
.empty-state--positive .empty-state__icon {
    color: var(--green);
    opacity: 0.7;
}

.empty-state--positive .empty-state__headline {
    color: var(--green);
}

/* Compact empty state (for inline use in table cells, sidebar panels) */
.empty-state--compact {
    padding: 24px 16px;
}

.empty-state--compact .empty-state__icon {
    font-size: 28px;
}

.empty-state--compact .empty-state__headline {
    font-size: 14px;
}

.empty-state--compact .empty-state__description {
    font-size: 13px;
    max-width: 280px;
}

/* ============================================================
   Skeleton Loaders (extending existing)
   ============================================================ */

/* Base skeleton animation -- already exists as .skeleton-row */
/* Adding new skeleton variants */

.skeleton-card {
    min-height: 80px;
}

.skeleton-text {
    height: 14px;
    width: 60%;
    background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-hover) 50%, var(--bg-card) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
}

.skeleton-text--short {
    height: 12px;
    width: 40%;
    background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-hover) 50%, var(--bg-card) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
}

.skeleton-feed-item {
    height: 36px;
    background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-hover) 50%, var(--bg-card) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
    margin-bottom: 6px;
}

.skeleton-message {
    height: 60px;
    width: 70%;
    background: linear-gradient(90deg, var(--bg-card) 25%, var(--bg-hover) 50%, var(--bg-card) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 8px;
    margin-bottom: 8px;
}

.skeleton-message--right {
    margin-left: auto;
    width: 65%;
}

.skeleton-message--left {
    width: 70%;
}

/* ============================================================
   Button Loading State
   ============================================================ */
.btn-spinner {
    display: none;
    width: 14px;
    height: 14px;
    border: 2px solid transparent;
    border-top-color: currentColor;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    vertical-align: middle;
    margin-right: 6px;
}

.btn--loading .btn-spinner,
.htmx-request .btn-spinner.htmx-indicator {
    display: inline-block;
}

.btn--loading .btn-label,
.htmx-request .htmx-indicator ~ .btn-label {
    /* Label stays visible but button is disabled */
}

.btn--loading {
    opacity: 0.7;
    pointer-events: none;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* ============================================================
   Error States
   ============================================================ */

/* Page-level error */
.error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px 24px;
    text-align: center;
    gap: 16px;
}

.error-state__icon {
    font-size: 48px;
    color: var(--yellow);
    line-height: 1;
}

.error-state__headline {
    font-size: 20px;
    font-weight: 600;
    color: var(--text);
}

.error-state__description {
    font-size: 14px;
    color: var(--text-muted);
    max-width: 400px;
    line-height: 1.5;
}

.error-state__actions {
    display: flex;
    gap: 12px;
    margin-top: 8px;
}

.error-state__detail {
    margin-top: 16px;
    font-size: 12px;
    color: var(--text-muted);
}

.error-state__detail pre {
    font-size: 11px;
    padding: 0.5rem;
    background: var(--bg-card);
    border-radius: 4px;
    max-width: 500px;
    overflow-x: auto;
    text-align: left;
    margin-top: 8px;
}

/* Component-level error (inline) */
.component-error {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: 8px;
    gap: 12px;
}

.component-error__message {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: var(--text-muted);
}

.component-error__icon {
    color: var(--red);
    font-size: 16px;
    flex-shrink: 0;
}

/* Form field errors */
.form-group--error input,
.form-group--error select,
.form-group--error textarea {
    border-color: var(--red);
}

.form-group--error input:focus,
.form-group--error select:focus,
.form-group--error textarea:focus {
    border-color: var(--red);
    box-shadow: 0 0 0 2px rgba(233, 20, 41, 0.2);
}

.form-error {
    font-size: 12px;
    color: var(--red);
    margin-top: 4px;
    display: flex;
    align-items: center;
    gap: 4px;
}

.form-error::before {
    content: "!";
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--red);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    flex-shrink: 0;
}

/* ============================================================
   Toast Notifications
   ============================================================ */
#toast-container {
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 50;
    display: flex;
    flex-direction: column;
    gap: 8px;
    pointer-events: none;
}

.toast {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    pointer-events: auto;
    animation: toastIn 0.3s ease, toastOut 0.3s ease 4s forwards;
    max-width: 400px;
}

.toast--success {
    background: rgba(30, 215, 96, 0.15);
    color: var(--green);
    border: 1px solid rgba(30, 215, 96, 0.3);
}

.toast--error {
    background: rgba(239, 68, 68, 0.15);
    color: var(--red);
    border: 1px solid rgba(239, 68, 68, 0.3);
}

.toast--warning {
    background: rgba(255, 164, 43, 0.15);
    color: var(--yellow);
    border: 1px solid rgba(255, 164, 43, 0.3);
}

.toast__icon {
    font-size: 16px;
    flex-shrink: 0;
}

@keyframes toastIn {
    from { opacity: 0; transform: translateX(16px); }
    to { opacity: 1; transform: translateX(0); }
}

@keyframes toastOut {
    from { opacity: 1; transform: translateX(0); }
    to { opacity: 0; transform: translateX(16px); }
}

/* ============================================================
   Reduced Motion: Disable all animations
   ============================================================ */
@media (prefers-reduced-motion: reduce) {
    .skeleton-row,
    .skeleton-text,
    .skeleton-text--short,
    .skeleton-feed-item,
    .skeleton-message,
    .skeleton-card .skeleton-text,
    .skeleton-card .skeleton-text--short {
        animation: none;
        background: var(--bg-hover);
    }

    .btn-spinner {
        animation: none;
        border: 2px solid currentColor;
        opacity: 0.5;
    }

    .toast {
        animation: none;
    }

    .empty-state,
    .error-state,
    .component-error {
        animation: none;
    }
}
```

---

### Reusable Template Partial: Empty State

**File: `app/templates/console/partials/empty_state.html`**

```html
{#
  Reusable empty state component.

  Parameters:
    icon        - HTML entity for the icon (e.g. "&#9993;")
    headline    - Main heading text
    description - Explanatory paragraph
    cta_text    - (optional) Button text
    cta_url     - (optional) Button link URL
    cta_class   - (optional) Button class, defaults to "btn btn-primary"
    positive    - (optional) Boolean -- if true, renders with green accent
    compact     - (optional) Boolean -- if true, renders smaller
#}
<div class="empty-state {% if positive %}empty-state--positive{% endif %} {% if compact %}empty-state--compact{% endif %}"
     role="status">
    {% if icon %}
    <div class="empty-state__icon" aria-hidden="true">{{ icon }}</div>
    {% endif %}
    <div class="empty-state__headline">{{ headline }}</div>
    <div class="empty-state__description">{{ description }}</div>
    {% if cta_text %}
    <a href="{{ cta_url }}" class="{{ cta_class|default('btn btn-primary') }} empty-state__cta">{{ cta_text }}</a>
    {% endif %}
</div>
```

**Usage example:**

```jinja2
{% include "console/partials/empty_state.html" with context %}
{# Where context includes: icon="&#9830;", headline="No customers yet", etc. #}
```

Or inline (since Jinja2 include with variables requires set/call macros):

```jinja2
{% set empty_icon = "&#9830;" %}
{% set empty_headline = "No customers yet" %}
{% set empty_description = "Add your first real estate agent to get started." %}
{% set empty_cta_text = "+ New Customer" %}
{% set empty_cta_url = "/console/tenants/new" %}
{% include "console/partials/empty_state.html" %}
```

Alternatively, implement as a **Jinja2 macro** for cleaner invocation:

**File: `app/templates/console/macros/states.html`**

```html
{% macro empty_state(icon, headline, description, cta_text=None, cta_url=None, cta_class="btn btn-primary", positive=False, compact=False) %}
<div class="empty-state {% if positive %}empty-state--positive{% endif %} {% if compact %}empty-state--compact{% endif %}"
     role="status">
    {% if icon %}
    <div class="empty-state__icon" aria-hidden="true">{{ icon }}</div>
    {% endif %}
    <div class="empty-state__headline">{{ headline }}</div>
    <div class="empty-state__description">{{ description }}</div>
    {% if cta_text and cta_url %}
    <a href="{{ cta_url }}" class="{{ cta_class }} empty-state__cta">{{ cta_text }}</a>
    {% endif %}
</div>
{% endmacro %}

{% macro component_error(message, retry_url, retry_target) %}
<div class="component-error" role="alert" aria-live="polite">
    <div class="component-error__message">
        <span class="component-error__icon" aria-hidden="true">&#9888;</span>
        {{ message }}
    </div>
    <button class="btn btn-outline btn-sm"
            hx-get="{{ retry_url }}"
            hx-target="{{ retry_target }}"
            hx-swap="innerHTML">
        Retry
    </button>
</div>
{% endmacro %}

{% macro error_state(headline="Something went wrong", description="We couldn't load this page. This is usually temporary -- try refreshing.", detail=None) %}
<div class="error-state" role="alert">
    <div class="error-state__icon" aria-hidden="true">&#9888;</div>
    <div class="error-state__headline">{{ headline }}</div>
    <div class="error-state__description">{{ description }}</div>
    <div class="error-state__actions">
        <button class="btn btn-primary" onclick="window.location.reload()">Refresh Page</button>
        <a href="/console/dashboard" class="btn btn-outline">Back to Dashboard</a>
    </div>
    {% if detail %}
    <div class="error-state__detail">
        <details>
            <summary>Technical details</summary>
            <pre>{{ detail }}</pre>
        </details>
    </div>
    {% endif %}
</div>
{% endmacro %}

{% macro loading_skeleton(rows=3, type="row") %}
<div class="loading-skeleton" role="status" aria-label="Loading">
    <span class="sr-only">Loading...</span>
    {% for i in range(rows) %}
        {% if type == "row" %}
        <div class="skeleton-row"></div>
        {% elif type == "feed" %}
        <div class="skeleton-feed-item"></div>
        {% elif type == "message" %}
        <div class="skeleton-message {% if loop.index is odd %}skeleton-message--left{% else %}skeleton-message--right{% endif %}"></div>
        {% endif %}
    {% endfor %}
</div>
{% endmacro %}
```

**Usage in templates:**

```jinja2
{% from "console/macros/states.html" import empty_state, component_error, loading_skeleton %}

{# Empty state #}
{{ empty_state(
    icon="&#9830;",
    headline="No customers yet",
    description="Add your first real estate agent to get started.",
    cta_text="+ New Customer",
    cta_url="/console/tenants/new"
) }}

{# Positive empty state #}
{{ empty_state(
    icon="&#10003;",
    headline="No errors in the last 24 hours",
    description="All systems are running smoothly.",
    positive=True
) }}

{# Loading skeleton #}
{{ loading_skeleton(rows=5, type="row") }}

{# Component error with retry #}
{{ component_error(
    message="Couldn't load the activity feed.",
    retry_url="/console/dashboard/activity-feed",
    retry_target="#activity-feed"
) }}
```

---

## Accessibility Requirements

### Empty States

- All empty states use `role="status"` so screen readers announce them.
- Icons use `aria-hidden="true"` -- the headline and description carry the meaning.
- CTA buttons are standard `<a>` or `<button>` elements with visible text.

### Loading States

- Skeleton containers use `role="status"` and `aria-label="Loading"`.
- A hidden `<span class="sr-only">Loading...</span>` announces the loading state.
- All shimmer animations are disabled when `prefers-reduced-motion: reduce` is active.
- The `aria-busy="true"` attribute should be set on the parent container during HTMX requests.

### Error States

- Page-level errors use `role="alert"` for immediate announcement.
- Component-level errors use `role="alert"` with `aria-live="polite"`.
- Form field errors use `aria-invalid="true"` on the input and `aria-describedby` pointing to the error message.
- Retry buttons are keyboard-focusable and clearly labeled.

### Toast Notifications

- The toast container uses `aria-live="polite"` and `aria-atomic="true"`.
- Toasts auto-dismiss after 4 seconds but should also be dismissible via click.
- Error toasts use `role="alert"` for urgency.

---

## Implementation Checklist

### Phase 1: CSS Foundation

- [ ] Add empty state CSS (`.empty-state`, `.empty-state--positive`, `.empty-state--compact`)
- [ ] Add skeleton loader CSS (`.skeleton-text`, `.skeleton-text--short`, `.skeleton-feed-item`, `.skeleton-message`)
- [ ] Add button spinner CSS (`.btn-spinner`, `.btn--loading`)
- [ ] Add error state CSS (`.error-state`, `.component-error`, `.form-group--error`, `.form-error`)
- [ ] Add toast CSS (`.toast`, `#toast-container`)
- [ ] Add reduced motion overrides

### Phase 2: Jinja2 Macros

- [ ] Create `app/templates/console/macros/states.html` with all four macros
- [ ] Create `app/templates/console/partials/component_error.html`

### Phase 3: Template Updates

- [ ] **Dashboard:** Update activity feed empty state, update "Needs Attention" empty state
- [ ] **Customers (tenants.html):** Replace table empty row with full empty state; add filtered-empty variant
- [ ] **Customer Detail -- Contacts tab:** Replace text with empty state component
- [ ] **Customer Detail -- Listings tab:** Replace text with empty state component
- [ ] **Customer Detail -- Automations tab:** Replace text with empty state component
- [ ] **Customer Detail -- Messages tab:** Add Test SMS CTA to empty state
- [ ] **Conversations:** Replace table empty row with full empty state; add filtered-empty variant
- [ ] **Triggers:** Replace table empty row with full empty state; add filtered-empty variant
- [ ] **System Health -- Errors tab:** Replace muted text with positive empty state
- [ ] **Billing -- Subscriptions:** Wrap existing text in empty state component
- [ ] **Billing -- AI Costs:** Wrap "No cost data yet" in empty state component

### Phase 4: Error Handling

- [ ] Add `component_error.html` partial
- [ ] Update activity feed endpoint to return error partial on failure
- [ ] Update messages tab endpoint to return error partial on failure
- [ ] Update knowledge base tab endpoint to return error partial on failure
- [ ] Add toast container to `base.html`
- [ ] Update POST endpoints to return toast HTML via `HX-Trigger` header

### Phase 5: Migrate Legacy Classes

- [ ] Rename existing `.messages-empty` usage to `.empty-state` for consistency
- [ ] Rename existing `.thread-empty` usage to `.empty-state--compact` where appropriate
- [ ] Ensure backward compatibility during migration

---

*This specification covers every page, component, and interaction in the Calloway admin console. Each state is designed to be helpful, accessible, and buildable with HTMX + Jinja2 + CSS only.*
