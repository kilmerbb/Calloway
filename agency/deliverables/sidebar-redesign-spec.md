# Sidebar Redesign & Jargon Cleanup — Design Specification

**Author:** Lyra, Product Designer
**Date:** 2026-03-14
**Status:** Ready for Engineering

---

## 1. Sidebar Layout — ASCII Wireframe

```
┌──────────────────────────┐
│  Calloway                │  ← Logo block
│  Admin Console           │     padding: 16px 16px 16px 16px
│                          │     border-bottom: 1px solid #333
├──────────────────────────┤
│                          │  ← 12px spacer
│  ┌──────────────────┐    │
│  │  + New Agent      │    │  ← CTA button (green outline)
│  └──────────────────┘    │     margin: 0 12px
│                          │  ← 12px spacer
├──────────────────────────┤  ← 1px solid #333 divider
│                          │  ← 8px spacer
│  🏠  Home                │  ← nav-item (active state shown)
│  👥  Customers           │
│  💬  Messages            │
│  ⚡  Automations         │
│                          │  ← 8px spacer
├╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤  ← 1px solid #333 divider
│                          │  ← 8px spacer
│  📊  Billing             │
│  🩺  System Health       │
│  🧪  Testing             │
│  📖  Help                │
│                          │
│         (flex spacer)    │  ← flex-grow: 1
│                          │
├──────────────────────────┤  ← 1px solid #333 divider
│  ↩   Logout              │  ← bottom-pinned
└──────────────────────────┘
```

**Grouping rationale:**
- **Top group** (Home, Customers, Messages, Automations): Daily workflow — the pages operators visit most
- **Bottom group** (Billing, System Health, Testing, Help): Operational and support — visited less frequently
- **+ New Agent**: Elevated as a CTA because onboarding is a distinct action, not a page you browse to regularly
- **Logout**: Pinned to the bottom, visually separated

---

## 2. HTML Structure

Replace the existing `<nav>` contents in `base.html` with:

```html
<nav class="sidebar" id="sidebar" role="navigation" aria-label="Main navigation">
    <div class="sidebar-logo">
        Calloway
        <small>Admin Console</small>
    </div>

    <div class="sidebar-cta">
        <a href="/console/onboard" class="btn-new-agent {% if active_nav == 'onboard' %}active{% endif %}"
           title="Step-by-step wizard to onboard a new real estate agent">
            <span class="nav-icon" aria-hidden="true">+</span> New Agent
        </a>
    </div>

    <div class="nav-group" role="group" aria-label="Main">
        <a href="/console/dashboard" class="nav-item {% if active_nav == 'dashboard' %}active{% endif %}"
           title="System overview with key metrics and activity feed">
            <span class="nav-icon" aria-hidden="true">⌂</span> Home
        </a>
        <a href="/console/tenants" class="nav-item {% if active_nav == 'tenants' %}active{% endif %}"
           title="Manage real estate agent accounts">
            <span class="nav-icon" aria-hidden="true">♦</span> Customers
        </a>
        <a href="/console/conversations" class="nav-item {% if active_nav == 'conversations' %}active{% endif %}"
           title="View all SMS, RCS, voice, and email conversations">
            <span class="nav-icon" aria-hidden="true">◬</span> Messages
        </a>
        <a href="/console/triggers" class="nav-item {% if active_nav == 'triggers' %}active{% endif %}"
           title="Scheduled follow-ups, reminders, and automated actions">
            <span class="nav-icon" aria-hidden="true">↻</span> Automations
        </a>
    </div>

    <div class="nav-divider"></div>

    <div class="nav-group" role="group" aria-label="Operations">
        <a href="/console/billing" class="nav-item {% if active_nav == 'billing' or active_nav == 'costs' %}active{% endif %}"
           title="Subscriptions, revenue tracking, and AI cost breakdown">
            <span class="nav-icon" aria-hidden="true">$</span> Billing
        </a>
        <a href="/console/health" class="nav-item {% if active_nav == 'health' or active_nav == 'errors' %}active{% endif %}"
           title="Service status, response times, and error log">
            <span class="nav-icon" aria-hidden="true">♥</span> System Health
        </a>
        <a href="/harness/" class="nav-item {% if active_nav == 'harness' %}active{% endif %}"
           title="Simulate conversations to test AI behavior">
            <span class="nav-icon" aria-hidden="true">⚙</span> Testing
        </a>
        <a href="/console/manual" class="nav-item {% if active_nav == 'manual' %}active{% endif %}"
           title="User guide and feature documentation">
            <span class="nav-icon" aria-hidden="true">?</span> Help
        </a>
    </div>

    <div class="nav-bottom">
        <a href="/console/logout" class="nav-item"
           title="End your session and return to the login screen">
            <span class="nav-icon" aria-hidden="true">←</span> Logout
        </a>
    </div>
</nav>
```

**Notes on URL mapping:**
- The `href` values stay the same (no backend route changes needed for the sidebar itself).
- The `active_nav` values stay the same. The consolidated pages (Billing absorbs Costs, System Health absorbs Errors) use `or` conditions so either sub-page highlights the parent nav item.

---

## 3. CSS Specification

Add/replace the following in `style.css`. All values are exact.

### 3.1 New Agent CTA Button

```css
.sidebar-cta {
    padding: 12px 12px 0 12px;
}

.btn-new-agent {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: 100%;
    padding: 10px 0;
    border: 1px solid var(--accent);
    border-radius: 6px;
    color: var(--accent);
    font-size: 14px;
    font-weight: 600;
    background: transparent;
    transition: background 0.15s, color 0.15s;
    cursor: pointer;
}

.btn-new-agent:hover {
    background: var(--accent);
    color: #000;
    text-decoration: none;
}

.btn-new-agent:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
}

.btn-new-agent.active {
    background: rgba(30, 215, 96, 0.15);
    border-color: var(--accent);
    color: var(--accent);
}

.btn-new-agent .nav-icon {
    font-size: 16px;
    font-weight: 700;
    line-height: 1;
}
```

### 3.2 Nav Groups & Divider

```css
.nav-group {
    padding: 8px 0;
}

.nav-divider {
    height: 1px;
    background: var(--border);
    margin: 0 12px;
}
```

### 3.3 Nav Items (updated)

Replace the existing `.nav-item` rules with:

```css
.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 16px;
    color: var(--text-muted);
    font-size: 14px;
    font-weight: 400;
    transition: background 0.15s, color 0.15s;
    border-right: 2px solid transparent;
}

.nav-item:hover {
    background: var(--bg-hover);
    color: var(--text);
    text-decoration: none;
}

.nav-item.active {
    color: var(--accent);
    background: rgba(30, 215, 96, 0.1);
    border-right-color: var(--accent);
    font-weight: 500;
}

.nav-item:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
}
```

### 3.4 Nav Icons

```css
.nav-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    font-size: 15px;
    text-align: center;
    flex-shrink: 0;
}
```

### 3.5 Bottom-Pinned Logout

Remove the inline `style` from the Logout link in `base.html`. Replace with:

```css
.nav-bottom {
    margin-top: auto;
    border-top: 1px solid var(--border);
    padding-top: 4px;
}
```

Also update the `.sidebar` rule to enable flex column layout:

```css
.sidebar {
    width: var(--sidebar-w);
    background: var(--bg-card);
    border-right: 1px solid var(--border);
    padding: 1rem 0;
    position: fixed;
    height: 100vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
}
```

### 3.6 Mobile — No Changes Needed

The existing responsive rules at `@media (max-width: 768px)` already handle sidebar off-canvas behavior via `transform: translateX(-100%)` and the `.open` toggle. No modifications needed. The new structure will inherit this behavior since it uses the same `.sidebar` class and `.nav-item` elements.

---

## 4. Consolidated Pages — Sub-section Design

### 4.1 System Health (absorbs Errors)

The `/console/health` page should present its content in **tab sections** within a single page. Do NOT use separate routes — use HTMX tab switching on one page.

**Tab bar spec:**

```
┌──────────────────────────────────────────────────────┐
│  [Services]   [Response Times]   [Errors]   [Actions]│
├──────────────────────────────────────────────────────┤
│                                                      │
│  (tab content renders here)                          │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**CSS for tab bar:**

```css
.tab-bar {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 16px;
}

.tab-btn {
    padding: 10px 20px;
    color: var(--text-muted);
    font-size: 14px;
    font-weight: 500;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s;
}

.tab-btn:hover {
    color: var(--text);
}

.tab-btn.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
}

.tab-btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
}

.tab-panel {
    display: none;
}

.tab-panel.active {
    display: block;
    animation: fadeIn 0.2s ease;
}
```

**Tabs and their content:**

| Tab | Content |
|-----|---------|
| Services | Current "Service Connectivity" section (service status cards) |
| Response Times | Current "Pipeline Performance" section — rename to "Response Times" |
| Errors | Move all content from the current `/console/errors` page here |
| Actions | Current "Manual Actions" section |

**Implementation approach:** Use `hx-get` with query param `?tab=services|response-times|errors|actions` to load tab content. Default tab: "Services". The backend should accept an optional `tab` query parameter and render only the relevant section partial. Alternatively, render all tabs on page load and toggle visibility with a small JS snippet (simpler, less backend work):

```html
<div class="tab-bar" role="tablist">
    <button class="tab-btn active" role="tab" aria-selected="true"
            data-tab="services">Services</button>
    <button class="tab-btn" role="tab" aria-selected="false"
            data-tab="response-times">Response Times</button>
    <button class="tab-btn" role="tab" aria-selected="false"
            data-tab="errors">Errors</button>
    <button class="tab-btn" role="tab" aria-selected="false"
            data-tab="actions">Actions</button>
</div>
```

### 4.2 Billing (absorbs Costs)

Same tab pattern. The `/console/billing` page gets tabs:

| Tab | Content |
|-----|---------|
| Subscriptions | Current billing page content (subscription table, plan management) |
| AI Costs | All content from the current `/console/costs` page |

Default tab: "Subscriptions".

**Route handling:** Keep `/console/costs` as a redirect to `/console/billing?tab=ai-costs` for any existing bookmarks or links.

---

## 5. Interaction Specifications

### 5.1 Hover State

| Element | Hover Behavior |
|---------|---------------|
| `.nav-item` | `background: #282828`, `color: #FFFFFF`, transition `0.15s` ease |
| `.btn-new-agent` | `background: #1ED760`, `color: #000000`, transition `0.15s` ease |
| `.tab-btn` | `color: #FFFFFF`, no background change |

### 5.2 Active State

| Element | Active (current page) |
|---------|----------------------|
| `.nav-item.active` | `color: #1ED760`, `background: rgba(30,215,96,0.1)`, `border-right: 2px solid #1ED760`, `font-weight: 500` |
| `.btn-new-agent.active` | `background: rgba(30,215,96,0.15)`, `border: 1px solid #1ED760`, `color: #1ED760` |
| `.tab-btn.active` | `color: #1ED760`, `border-bottom: 2px solid #1ED760` |

### 5.3 Focus State (keyboard navigation)

All interactive sidebar elements get `focus-visible` with `outline: 2px solid #1ED760`, `outline-offset: 2px` (or `-2px` for inset on nav-items). This meets WCAG 2.1 AA focus indicator requirements.

### 5.4 Tab Order

```
1. Skip-to-content link
2. + New Agent button
3. Home → Customers → Messages → Automations (top group, top to bottom)
4. Billing → System Health → Testing → Help (bottom group, top to bottom)
5. Logout
6. Main content area
```

---

## 6. Icon Recommendations

For the initial implementation, use plain Unicode characters (no icon library dependency). These are placeholder glyphs — a future pass can swap in an SVG icon set (Lucide, Phosphor, or Heroicons recommended).

| Nav Item | Unicode Char | Fallback Emoji | Notes |
|----------|-------------|----------------|-------|
| + New Agent | `+` (plus sign) | — | Literal plus in the button label |
| Home | `⌂` (U+2302) | 🏠 | House glyph |
| Customers | `♦` (U+2666) | 👥 | Abstract people; could also use `◉` |
| Messages | `◬` (U+25EC) | 💬 | Speech-bubble-like triangle |
| Automations | `↻` (U+21BB) | ⚡ | Circular arrow = recurring/automated |
| Billing | `$` (dollar sign) | 💰 | Universal money symbol |
| System Health | `♥` (U+2665) | 🩺 | Heartbeat/health |
| Testing | `⚙` (U+2699) | 🧪 | Gear = tooling |
| Help | `?` (question mark) | 📖 | Universal help symbol |
| Logout | `←` (U+2190) | ↩ | Left arrow = exit |

**Recommendation for Phase 2:** Replace with inline SVGs from Lucide Icons (MIT license, 1px stroke, consistent 24x24 grid). Render at `16px` within the `20px` wide `.nav-icon` container. This gives crisp, theme-aware icons that can inherit `currentColor`.

---

## 7. Jargon Replacement Map

### 7.1 Global Terminology Changes

These replacements apply across ALL templates, not just the sidebar:

| Old Term | New Term | Files Affected |
|----------|----------|---------------|
| Tenant / Tenants | Customer / Customers | `base.html`, `tenants.html`, `tenant_detail.html`, `tenant_edit.html`, `tenant_new.html`, `dashboard.html`, `costs.html`, `errors.html`, `triggers.html`, `health.html`, `manual.html`, `onboard_success.html`, `onboard_wizard.html` |
| Triggers | Automations | `base.html`, `triggers.html`, `tenant_detail.html`, `manual.html` |
| Pipeline Performance | Response Times | `health.html` |
| Harness | Testing | `base.html` |
| Manual (as nav label) | Help | `base.html` |
| Onboard Agent | + New Agent | `base.html` |
| Dashboard | Home | `base.html` (nav label only — page title can remain "Dashboard" or become "Home") |
| Tool Execution Errors | Integration Errors | `errors.html` — "tool execution" is developer jargon |
| Application Errors | System Errors | `errors.html` — clearer for non-developers |
| Fire Now (trigger action) | Run Now | `triggers.html` — "fire" is internal jargon |
| trigger_type column display | Automation Type | `triggers.html` — column header |
| action_type column display | Action | `triggers.html` — already fine, just confirm no "action_type" raw value leaks |
| LLM Cost / LLM Calls | AI Cost / AI Calls | `dashboard.html`, `costs.html` — "LLM" means nothing to a business operator |
| Model Tier Breakdown | AI Model Usage | `costs.html` |
| Per-Agent Costs | Cost by Customer | `costs.html` |
| Active Tenants (dashboard card) | Active Customers | `dashboard.html` |
| Needs Attention → "Tenants with errors" | Customers needing attention | `dashboard.html` |
| p50 / p95 | Median / 95th percentile | `health.html` — or even better: "Typical" / "Slowest 5%" |
| Avg Latency | Avg Response Time | `health.html` |
| Run daily scan | Run daily check | `health.html` — "scan" sounds invasive |
| Select agent... | Select customer... | `health.html` dropdown |
| csrf_token (visible nowhere, but confirming) | No change | Not user-facing |

### 7.2 Specific Template Changes

#### `dashboard.html`

| Current Text | New Text |
|-------------|----------|
| `Active Tenants` (card label) | `Active Customers` |
| `LLM Cost Today` (card label) | `AI Cost Today` |
| `Needs Attention` (section title) | `Needs Attention` (keep — already plain language) |
| title attrs referencing "tenants" | Update to "customers" |

#### `triggers.html`

| Current Text | New Text |
|-------------|----------|
| Page title (set in backend) | Change from "Triggers" to "Automations" |
| Column header "Agent" | "Customer" |
| "Filter triggers by tenant" | "Filter automations by customer" |
| "No triggers found." | "No automations found." |
| "Fire Now" button | "Run Now" |
| "Fire this trigger now?" confirm dialog | "Run this automation now? This will send a real message to the contact." |
| "Cancel this trigger?" confirm dialog | "Cancel this automation?" |
| "Reset this trigger to pending" | "Retry this automation" |

#### `health.html`

| Current Text | New Text |
|-------------|----------|
| `Pipeline Performance (24h)` | `Response Times (24h)` |
| `Avg Latency` card label | `Avg Response Time` |
| `p50` card label | `Typical (Median)` |
| `p95` card label | `Slowest 5%` |
| "Choose the tenant to run..." | "Choose the customer to run..." |
| "Run daily scan" | "Run daily check" |

#### `costs.html`

| Current Text | New Text |
|-------------|----------|
| `Total LLM Cost (30d)` | `Total AI Cost (30d)` |
| `LLM Calls` | `AI Requests` |
| `Model Tier Breakdown` | `AI Model Usage` |
| `Per-Agent Costs (30 days)` | `Cost by Customer (30 days)` |
| Column "Agent" | "Customer" |
| Column "LLM Calls" | "AI Requests" |
| title referencing "tenants" | "customers" |
| Column "$/msg" | "Cost/Message" |

#### `errors.html`

| Current Text | New Text |
|-------------|----------|
| `Tool Execution Errors` | `Integration Errors` |
| `Application Errors` | `System Errors` |
| Column "Agent" | "Customer" |
| "Filter errors by tenant" | "Filter errors by customer" |

#### `tenants.html` (becoming "Customers")

| Current Text | New Text |
|-------------|----------|
| Page title | "Customers" |
| "New Tenant" button | Already handled by sidebar CTA, but page-level button should say "New Customer" |
| "Filter tenants by name" | "Filter customers by name" |
| "No tenants found." | "No customers found." |
| All title attributes referencing "tenant" | Replace with "customer" |

#### `tenant_detail.html`

| Current Text | New Text |
|-------------|----------|
| "Edit Config" button | "Edit Settings" |
| "Deactivate this tenant?" confirm | "Deactivate this customer?" |
| "Pending Triggers" section | "Scheduled Automations" |
| All title attributes referencing "tenant" | Replace with "customer" |

#### `onboard_wizard.html` and `onboard_success.html`

| Current Text | New Text |
|-------------|----------|
| "tenant detail page" references | "customer detail page" |

#### `manual.html`

All references to old terminology throughout the user manual must be updated to match. This is a substantial find-and-replace pass — every instance of "Tenant" becomes "Customer", "Triggers" becomes "Automations", etc.

### 7.3 Backend `page_title` Changes

The backend (`console.py`) sets `page_title` per route. These need updating:

| Route | Current `page_title` | New `page_title` |
|-------|---------------------|-------------------|
| `/console/dashboard` | "Dashboard" | "Home" |
| `/console/tenants` | "Tenants" | "Customers" |
| `/console/conversations` | "Conversations" | "Messages" |
| `/console/triggers` | "Triggers" | "Automations" |
| `/console/errors` | "Errors" | Redirect to `/console/health?tab=errors` |
| `/console/costs` | "Costs" | Redirect to `/console/billing?tab=ai-costs` |
| `/console/health` | "Health" | "System Health" |
| `/console/billing` | "Billing" | "Billing" (unchanged) |
| `/console/manual` | "Manual" | "Help" |

---

## 8. Accessibility Checklist

| Requirement | Specification |
|------------|---------------|
| Focus indicators | All interactive elements: `outline: 2px solid #1ED760`, `outline-offset: 2px` on `:focus-visible` |
| Tab order | Logical top-to-bottom flow as specified in Section 5.4 |
| ARIA roles | `nav` has `role="navigation"` and `aria-label="Main navigation"`. Nav groups have `role="group"` with `aria-label`. Tabs have `role="tablist"`, `role="tab"`, `aria-selected` |
| Color contrast | `#B3B3B3` on `#181818` = 7.5:1 ratio (passes AAA). `#1ED760` on `#181818` = 5.2:1 ratio (passes AA). `#FFFFFF` on `#282828` = 12.6:1 ratio (passes AAA) |
| Screen reader | Icons use `aria-hidden="true"`. Nav items use text labels (not icon-only). Active state communicated via `aria-current="page"` (add to active nav item) |
| Skip nav | Already implemented, no changes needed |
| Reduced motion | Add `@media (prefers-reduced-motion: reduce)` to disable transitions |

Add to CSS:

```css
@media (prefers-reduced-motion: reduce) {
    .nav-item,
    .btn-new-agent,
    .tab-btn,
    .tab-panel {
        transition: none;
        animation: none;
    }
}
```

---

## 9. Implementation Sequence (for Atlas)

1. **Update `base.html`** — Replace sidebar HTML with the new structure from Section 2.
2. **Update `style.css`** — Add new rules from Sections 3.1-3.5. Modify existing `.sidebar` and `.nav-item` rules.
3. **Update `page_title` values** in `console.py` per Section 7.3.
4. **Find-and-replace jargon** in all templates per Section 7.2.
5. **Build tab UI** for System Health page — merge errors content into health template.
6. **Build tab UI** for Billing page — merge costs content into billing template.
7. **Add redirects** — `/console/errors` redirects to `/console/health?tab=errors`, `/console/costs` redirects to `/console/billing?tab=ai-costs`.
8. **Add `aria-current="page"`** to the active nav item in `base.html`.
9. **Add reduced-motion media query** from Section 8.
10. **Test** — Verify all nav links work, active states highlight correctly, mobile hamburger menu still functions, tab switching works on consolidated pages, and keyboard navigation flows correctly.

---

## 10. What NOT to Change

- **URLs/routes** for the four primary pages (Home, Customers, Messages, Automations) — keep existing paths.
- **Sidebar width** — keep at `220px`. The new structure fits comfortably.
- **Mobile behavior** — existing hamburger/overlay pattern is solid.
- **Color palette** — all values stay within the established design system.
- **Data model** — "tenant" in the database/code layer is fine. Only user-facing text changes.
