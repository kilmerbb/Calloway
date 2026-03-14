# Calloway Console — Responsive Design Specification

**Author:** Lyra, Product Designer
**Date:** 2026-03-14
**Status:** Ready for Engineering
**Scope:** Full responsive treatment for the admin console (`/console/*`)

---

## Table of Contents

1. [Audit of Current State](#1-audit-of-current-state)
2. [Breakpoint System](#2-breakpoint-system)
3. [Sidebar & Navigation](#3-sidebar--navigation)
4. [Stat Cards](#4-stat-cards)
5. [Data Tables](#5-data-tables)
6. [Tab Bars](#6-tab-bars)
7. [Forms & Inputs](#7-forms--inputs)
8. [Detail Grids & Two-Column Layouts](#8-detail-grids--two-column-layouts)
9. [Chat & Message Threads](#9-chat--message-threads)
10. [Messages Layout (Contact List + Thread)](#10-messages-layout-contact-list--thread)
11. [Bar Charts](#11-bar-charts)
12. [Modals & Dropdowns](#12-modals--dropdowns)
13. [Onboarding Wizard](#13-onboarding-wizard)
14. [Login Page](#14-login-page)
15. [Manual / Help Page](#15-manual--help-page)
16. [Knowledge Base Tab](#16-knowledge-base-tab)
17. [Touch Target Requirements](#17-touch-target-requirements)
18. [Page-by-Page Layout Summary](#18-page-by-page-layout-summary)
19. [Full CSS Implementation](#19-full-css-implementation)

---

## 1. Audit of Current State

### What Already Exists

The console already has a partial responsive foundation:

| Check | Status | Notes |
|-------|--------|-------|
| Viewport meta tag | Present | `<meta name="viewport" content="width=device-width, initial-scale=1.0">` in both `base.html` and `login.html` |
| Mobile hamburger toggle | Present | `.mobile-menu-toggle` button with animated bars, hidden by default, shown at 768px |
| Sidebar overlay | Present | `.sidebar-overlay` element with click-to-close behavior |
| Sidebar slide-in | Present | Sidebar translates off-screen at 768px, slides in via `.open` class |
| Close-on-nav-click | Present | JS closes sidebar when any nav link is tapped |
| Media query (768px) | Present | Single breakpoint handles sidebar, card-grid (2-col), detail-grid (1-col), form-row (stacked), tab-bar (scroll), profile-two-col (1-col), messages-layout (stacked) |
| `prefers-reduced-motion` | Present | Disables transitions and animations |
| `overflow-x: auto` on tables | Partial | Used on Contacts, Listings, and Automations tables within `tenant_detail.html`, but NOT on the main Tenants, Conversations, Triggers, Costs, Billing, Errors, or Health tables |
| Table font-size reduction | Present | Tables shrink to 12px with tighter padding at 768px |

### What Is Missing

| Gap | Impact | Priority |
|-----|--------|----------|
| **No tablet breakpoint (768-1023px)** | iPad users see the mobile hamburger layout OR the full desktop sidebar with cramped content | Critical |
| **No `overflow-x: auto` on most tables** | Tables overflow the viewport on any screen narrower than ~1100px; horizontal content is clipped | Critical |
| **Buttons and tap targets are too small** | `.btn-sm` is `padding: 0.25rem 0.5rem` = ~28px tall. Action buttons in table cells (Retry, Run Now, Cancel) are undersized for touch | High |
| **Card-grid jumps from auto-fit to 2-col** | At 768px the card-grid forces `repeat(2, 1fr)` but there is no 1-col fallback for very narrow screens (<400px) | Medium |
| **No column hiding on tables** | 9-column Tenants table and 8-column Triggers table show every column on mobile, making rows extremely wide even with scroll | Medium |
| **Filter bars can overflow** | `.filters` uses `flex-wrap: wrap` which helps, but individual filter inputs have no `min-width` constraint and can become too narrow to use | Medium |
| **Wizard dot targets are 8px** | The navigation dots in the onboarding wizard are 8px diameter, well below the 44px touch target minimum | Medium |
| **Bar chart does not resize** | The `.bar-chart` has a fixed `height: 120px` and bars have `min-width: 12px`; 30 bars at 12px + 3px gap = 450px minimum, which overflows on narrow screens | Low |
| **`<details>` dropdown in Billing table** | The "Change Plan" dropdown uses `position: absolute; right: 0` which can overflow on narrow screens | Medium |
| **Topbar `padding-left: 3.5rem` only at 768px** | If we add a tablet breakpoint, the topbar needs adjustment there too | Low |

---

## 2. Breakpoint System

Three breakpoints, mobile-first augmented with max-width overrides to preserve the existing desktop layout:

| Token | Range | Target Devices | Sidebar Behavior |
|-------|-------|----------------|------------------|
| **Mobile** | < 768px | Phones (iPhone, Pixel) | Hidden; hamburger menu with overlay |
| **Tablet** | 768px - 1023px | iPad Mini, iPad, Android tablets | Collapsed rail (icons only, 60px wide) |
| **Desktop** | >= 1024px | Laptops, desktops | Full sidebar (220px) |

```css
/* Tablet: collapsed sidebar rail */
@media (min-width: 768px) and (max-width: 1023px) { ... }

/* Mobile: hamburger menu */
@media (max-width: 767px) { ... }
```

**Why a collapsed rail for tablet instead of hamburger?**
Operators demoing on an iPad need persistent navigation awareness. A rail with recognizable icons lets them tap through pages without opening and closing a drawer. It also preserves the "dashboard feel" that distinguishes a SaaS console from a mobile app.

---

## 3. Sidebar & Navigation

### Desktop (>= 1024px)
No changes. Full 220px sidebar with labels, icons, and logo text.

### Tablet (768px - 1023px)
**Collapsed icon rail:**
- Width shrinks from 220px to 60px
- Logo text hides; only the "C" initial or a small icon remains
- Nav item labels hide; only `.nav-icon` is visible
- `.btn-new-agent` collapses to show only the "+" icon
- `.nav-bottom` logout shows only the arrow icon
- Tooltip on hover shows the label (CSS `title` attribute already present)
- `--sidebar-w` is overridden to `60px`
- `.main-content` margin adjusts to `60px`

### Mobile (< 767px)
No changes to existing behavior. Hamburger + overlay + slide-in sidebar at full 220px width.

```css
/* ---- Tablet: Collapsed Sidebar Rail ---- */
@media (min-width: 768px) and (max-width: 1023px) {
    :root {
        --sidebar-w: 60px;
    }

    .sidebar {
        width: 60px;
        overflow: visible;
    }

    .sidebar-logo {
        padding: 16px 8px;
        text-align: center;
        font-size: 18px;
    }

    .sidebar-logo small {
        display: none;
    }

    .sidebar-cta {
        padding: 12px 8px 0;
    }

    .btn-new-agent {
        padding: 10px 0;
        font-size: 0;       /* Hide text */
    }

    .btn-new-agent .nav-icon {
        font-size: 18px;
    }

    .nav-item {
        justify-content: center;
        padding: 10px 0;
        font-size: 0;       /* Hide text */
        border-right: none;
    }

    .nav-item .nav-icon {
        font-size: 18px;
        width: auto;
    }

    /* Hamburger stays hidden on tablet */
    .mobile-menu-toggle {
        display: none;
    }
}

/* ---- Mobile: Hamburger Drawer ---- */
@media (max-width: 767px) {
    .mobile-menu-toggle {
        display: flex;
    }

    .sidebar {
        transform: translateX(-100%);
        transition: transform 0.2s;
        position: fixed;
        z-index: 20;
        width: 220px;
    }

    .sidebar.open {
        transform: translateX(0);
    }

    .main-content {
        margin-left: 0;
    }

    .topbar {
        padding-left: 3.5rem;
    }
}
```

---

## 4. Stat Cards

`.card-grid` currently uses `repeat(auto-fit, minmax(180px, 1fr))` which is already flexible.

### Desktop
No changes. Cards flow into as many columns as fit (typically 4-5 for the dashboard's 5 cards).

### Tablet
Reduce minimum card width so 3 cards fit comfortably in the narrower content area:
```css
@media (min-width: 768px) and (max-width: 1023px) {
    .card-grid {
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    }
}
```

### Mobile
Stack to 2 columns, with a 1-column fallback for very narrow screens:
```css
@media (max-width: 767px) {
    .card-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 400px) {
    .card-grid {
        grid-template-columns: 1fr;
    }
}
```

---

## 5. Data Tables

This is the highest-impact responsive change. The console has **10 distinct tables** across pages:

| Page | Table | Columns | Overflow Wrapper? |
|------|-------|---------|-------------------|
| Tenants | Agent list | 9 | No |
| Tenant Detail > Contacts | Contact list | 9 | Yes |
| Tenant Detail > Listings | Listing list | 7 | Yes |
| Tenant Detail > Automations | Automation list | 6 | Yes |
| Conversations | Conversation list | 7 | No |
| Triggers | Trigger list | 8 | No |
| Costs / Billing AI Costs | Per-agent costs | 7 | No |
| Costs / Billing AI Costs | Model tier | 3 | No |
| Health > Errors | Tool errors | 5 | No |
| Health > Errors | System errors | 5 | No |
| Billing > Subscriptions | Subscription list | 7 | No |

### Strategy: Horizontal Scroll with Column Priority

For all tables, wrap in a scrollable container. On tablet and mobile, hide low-priority columns using data attributes.

**Step 1: Add `overflow-x: auto` wrapper to all tables lacking one.**

Every `<table>` that is not already inside an `overflow-x: auto` wrapper needs one. This is a template change (add `<div style="overflow-x: auto;">` or a `.table-scroll` wrapper class).

```css
.table-scroll {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}
```

**Step 2: Column priority hiding.**

Add `data-priority` classes to `<th>` and `<td>` elements:

| Priority | Behavior | Example Columns |
|----------|----------|-----------------|
| `col-essential` | Always visible | Name, Status, primary action |
| `col-tablet` | Hidden below 768px | Brokerage, Market, Msgs Today |
| `col-desktop` | Hidden below 1024px | Twilio #, Tokens, Voice Min, Cost/Message |

```css
@media (max-width: 1023px) {
    .col-desktop {
        display: none;
    }
}

@media (max-width: 767px) {
    .col-tablet {
        display: none;
    }
}
```

**Column priority assignments per table:**

**Tenants table (9 cols):**
| Column | Priority |
|--------|----------|
| Name | essential |
| Brokerage | desktop |
| Market | tablet |
| Twilio # | desktop |
| Contacts | tablet |
| Msgs Today | tablet |
| Last Active | tablet |
| Status | essential |
| Errors 24h | essential |

**Conversations table (7 cols):**
| Column | Priority |
|--------|----------|
| Customer | essential |
| Contact | essential |
| Phone | desktop |
| Channel | tablet |
| Messages | tablet |
| Last Message | tablet |
| Time | essential |

**Triggers table (8 cols):**
| Column | Priority |
|--------|----------|
| Customer | essential |
| Type | essential |
| Scheduled | essential |
| Status | essential |
| Action | tablet |
| Autonomy | desktop |
| Recurrence | desktop |
| Actions | essential |

**Per-Agent Costs table (7 cols):**
| Column | Priority |
|--------|----------|
| Customer | essential |
| Messages | essential |
| AI Requests | tablet |
| Tokens | desktop |
| Cost | essential |
| Voice Min | desktop |
| Cost/Message | desktop |

**Subscriptions table (7 cols):**
| Column | Priority |
|--------|----------|
| Customer | essential |
| Plan | essential |
| Status | essential |
| Messages Used | tablet |
| Monthly Revenue | essential |
| Period Ends | tablet |
| Actions | essential |

**Step 3: Tighten table styling on mobile.**

```css
@media (max-width: 767px) {
    table {
        font-size: 13px;
    }

    th, td {
        padding: 0.5rem 0.5rem;
    }

    /* Prevent text wrapping on key columns */
    td:first-child {
        white-space: nowrap;
    }
}
```

---

## 6. Tab Bars

### Desktop
No changes. Horizontal tabs with bottom border indicators.

### Tablet
No changes needed; tabs fit comfortably. The tenant detail page has 6 tabs that total roughly 600px, which fits within the ~960px - 60px sidebar = ~900px content area.

### Mobile
Already handled: `overflow-x: auto` with `white-space: nowrap` and `-webkit-overflow-scrolling: touch`. Tabs scroll horizontally.

**Enhancement: Add scroll fade indicators.**

```css
@media (max-width: 767px) {
    .tab-bar {
        overflow-x: auto;
        white-space: nowrap;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;  /* Firefox */
        position: relative;
    }

    .tab-bar::-webkit-scrollbar {
        display: none;
    }

    .tab-btn {
        flex-shrink: 0;
        padding: 10px 16px;   /* Slightly reduce horizontal padding */
    }
}
```

---

## 7. Forms & Inputs

### Desktop
No changes. Current styling works well.

### Tablet
Minimal changes. `.form-row` stays side-by-side since there is enough width.

```css
@media (min-width: 768px) and (max-width: 1023px) {
    /* Forms in the edit page are max-width: 600px, fits fine */
    /* Wizard container is max-width: 800px, still fits */
}
```

### Mobile
Already handled: `.form-row` stacks to `flex-direction: column`.

**Additional fixes:**

```css
@media (max-width: 767px) {
    .form-row {
        flex-direction: column;
        gap: 0;
    }

    /* Ensure inputs have minimum height for touch */
    input[type="text"],
    input[type="email"],
    input[type="password"],
    input[type="tel"],
    input[type="time"],
    select,
    textarea {
        min-height: 44px;
        font-size: 16px;  /* Prevents iOS zoom on focus */
    }

    /* Filter bars: stack vertically */
    .filters {
        flex-direction: column;
        align-items: stretch;
    }

    .filters .form-group {
        width: 100%;
    }

    .filters .btn {
        width: 100%;
        text-align: center;
    }
}
```

**Critical: `font-size: 16px` on inputs.** iOS Safari zooms the page when focusing an input with font-size below 16px. The current `14px` triggers this. On mobile, inputs must be 16px.

---

## 8. Detail Grids & Two-Column Layouts

### `.detail-grid` (Dashboard, Conversation Detail)
- **Desktop:** `2fr 1fr` (content + sidebar)
- **Tablet:** `1fr 1fr` (equal columns, since the sidebar content is important)
- **Mobile:** `1fr` (stacked, already handled)

### `.profile-two-col` (Tenant Detail > Profile)
- **Desktop:** `1fr 1fr`
- **Tablet:** `1fr 1fr` (still fits)
- **Mobile:** `1fr` (already handled)

```css
@media (min-width: 768px) and (max-width: 1023px) {
    .detail-grid {
        grid-template-columns: 1fr 1fr;
        gap: 1rem;
    }
}
```

---

## 9. Chat & Message Threads

### `.chat-thread` / Conversation Detail

- **Desktop:** `max-width: 700px` (current)
- **Tablet:** `max-width: 100%` (use full available width)
- **Mobile:** `max-width: 100%`; chat bubbles expand to 95% width

```css
@media (max-width: 1023px) {
    .chat-thread {
        max-width: 100%;
    }
}

@media (max-width: 767px) {
    .chat-msg {
        max-width: 95%;
    }

    .chat-meta {
        font-size: 10px;
    }
}
```

---

## 10. Messages Layout (Contact List + Thread)

### Desktop
`grid-template-columns: 280px 1fr` (current).

### Tablet
Narrower contact list:
```css
@media (min-width: 768px) and (max-width: 1023px) {
    .messages-layout {
        grid-template-columns: 220px 1fr;
    }
}
```

### Mobile
Already handled: single column with contact list stacked above thread, max-height 300px on contact list.

---

## 11. Bar Charts

The `.bar-chart` (30 bars * 15px = 450px) can overflow on narrow screens.

```css
.bar-chart {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}

@media (max-width: 767px) {
    .bar-chart {
        height: 80px;  /* Reduce height on mobile */
    }

    .bar {
        min-width: 8px;
    }
}
```

---

## 12. Modals & Dropdowns

### Billing "Change Plan" Dropdown

Currently uses `position: absolute; right: 0` inside a `<details>` element. On mobile this can overflow.

```css
@media (max-width: 767px) {
    /* Make billing action dropdown full-width overlay */
    .tab-panel details[style*="position:relative"] > div {
        position: fixed;
        inset: auto 0 0 0;
        z-index: 50;
        border-radius: 12px 12px 0 0;
        max-width: 100%;
        padding: 1rem;
    }
}
```

**Recommendation for engineering:** Extract the inline styles on the billing dropdown to a CSS class (e.g., `.dropdown-panel`) to make it targetable by media queries. The inline `style` attributes make responsive overrides difficult.

---

## 13. Onboarding Wizard

### Desktop
No changes. `max-width: 800px` works well.

### Tablet
Already fits. 800px < tablet content width (~960px - 60px = 900px). No changes.

### Mobile
Already handled: `wizard-container` goes to `max-width: 100%`.

**Additional fixes:**

```css
@media (max-width: 767px) {
    /* Wizard navigation dots: increase touch target */
    .wizard-dots .dot {
        width: 24px;
        height: 24px;
        border-radius: 50%;
    }

    .wizard-dots .dot.active {
        width: 32px;
        border-radius: 12px;
    }

    /* Wizard nav buttons: full touch target height */
    .wizard-nav .btn {
        min-height: 44px;
        padding: 0.5rem 1.25rem;
    }

    /* Option cards: increase tap area */
    .option-card {
        padding: 1rem;
        min-height: 44px;
    }

    /* Checkbox items: increase tap area */
    .checkbox-item {
        padding: 0.75rem;
        min-height: 44px;
    }
}
```

---

## 14. Login Page

The `.login-container` already works well on mobile with `max-width: 360px; margin: 15vh auto`. On very small screens, add horizontal padding:

```css
@media (max-width: 400px) {
    .login-container {
        margin: 10vh 1rem;
    }
}
```

---

## 15. Manual / Help Page

The `.manual` class uses `max-width: 800px` which is fine. On mobile, tables within the manual need scroll wrappers:

```css
@media (max-width: 767px) {
    .manual {
        font-size: 14px;
        line-height: 1.6;
    }

    .manual h1 {
        font-size: 22px;
    }

    .manual h2 {
        font-size: 18px;
    }

    .manual table {
        display: block;
        overflow-x: auto;
    }
}
```

---

## 16. Knowledge Base Tab

The KB components (`.kb-summary-bar`, `.kb-settings-row`, `.kb-item`) already use `flex-wrap: wrap` which makes them responsive.

**Mobile enhancement:**
```css
@media (max-width: 767px) {
    .kb-settings-row {
        flex-direction: column;
        align-items: flex-start;
    }

    .kb-item-actions {
        justify-content: flex-start;
    }

    .kb-item-header {
        flex-direction: column;
        align-items: flex-start;
    }
}
```

Already handled in the existing 768px media query. No additional work needed.

---

## 17. Touch Target Requirements

Per WCAG 2.5.8 (Target Size), all interactive elements must meet a 44x44px minimum touch target on mobile and tablet.

### Elements Requiring Attention

| Element | Current Size | Fix |
|---------|-------------|-----|
| `.btn-sm` | ~28px tall | Increase to `min-height: 44px` on touch devices |
| `.wizard-dots .dot` | 8x8px | Increase to 24x24px with padding |
| `.tab-btn` | ~38px tall (10px padding + 14px font + 10px padding) | Increase padding to `12px 20px` = 42px, acceptable |
| `.nav-item` | ~36px tall (8px + 14px*1.5 + 8px) | Increase to `padding: 12px 16px` on tablet |
| Table action buttons | ~28px | Increase to `min-height: 44px` on touch |
| `.contact-item` | ~60px tall | Already sufficient |
| `.option-card` | ~50px+ | Already sufficient |
| Status filter `<select>` in Automations tab | ~28px | Increase to `min-height: 44px` |

```css
@media (max-width: 1023px) {
    /* All buttons meet touch target minimum */
    .btn {
        min-height: 44px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }

    .btn-sm {
        min-height: 36px;
        padding: 0.375rem 0.75rem;
    }

    /* Nav items meet touch target */
    .nav-item {
        min-height: 44px;
    }
}
```

---

## 18. Page-by-Page Layout Summary

### Dashboard (`/console/dashboard`)

| Breakpoint | Card Grid | Activity + Attention | Notes |
|------------|-----------|---------------------|-------|
| Desktop | 5 cards in auto-fit row | 2fr + 1fr side by side | Current behavior |
| Tablet | 3 cards top row, 2 below | 1fr + 1fr side by side | Slightly narrower cards |
| Mobile | 2 columns (5th card wraps) | Stacked (activity then attention) | Already handled |

### Customers (`/console/tenants`)

| Breakpoint | Table | Filters | Notes |
|------------|-------|---------|-------|
| Desktop | All 9 columns | Inline | Current behavior |
| Tablet | Hide Brokerage, Twilio # | Inline | 6 visible columns |
| Mobile | Hide Market, Contacts, Msgs Today, Last Active too | Stacked filters | 3-4 visible columns + scroll |

### Customer Detail (`/console/tenants/:id`)

| Breakpoint | Tab Bar | Profile Tab | Messages Tab | Tables |
|------------|---------|-------------|--------------|--------|
| Desktop | Horizontal | 2-col (profile + config) | 280px list + thread | Full columns |
| Tablet | Horizontal | 2-col (still fits) | 220px list + thread | Reduced columns |
| Mobile | Horizontal scroll | Stacked | Stacked (list 300px max-h + thread) | Reduced + scroll |

### Conversations (`/console/conversations`)

| Breakpoint | Table | Filters |
|------------|-------|---------|
| Desktop | All 7 columns | Inline row |
| Tablet | Hide Phone | Inline row |
| Mobile | Hide Channel, Messages, Last Message | Stacked filters |

### Conversation Detail (`/console/conversations/:id`)

| Breakpoint | Layout | Chat Width |
|------------|--------|------------|
| Desktop | 2fr + 1fr | 700px max |
| Tablet | 1fr + 1fr | 100% |
| Mobile | Stacked | 100%, bubbles 95% |

### Automations (`/console/triggers`)

| Breakpoint | Table | Filters |
|------------|-------|---------|
| Desktop | All 8 columns | Inline |
| Tablet | Hide Autonomy, Recurrence | Inline |
| Mobile | Hide Action too; action buttons stack | Stacked |

### Billing (`/console/billing`)

| Breakpoint | Tab Bar | Plan Cards | Subscriptions Table |
|------------|---------|------------|-------------------|
| Desktop | Horizontal | Auto-fit row | All 7 columns |
| Tablet | Horizontal | Auto-fit (3 across) | Hide Messages Used, Period Ends |
| Mobile | Scroll | 1 column | Hide Plan; dropdown becomes bottom sheet |

### System Health (`/console/health`)

| Breakpoint | Tab Bar | Service Cards | Error Tables |
|------------|---------|---------------|-------------|
| Desktop | Horizontal | Auto-fit row | Full columns |
| Tablet | Horizontal | Auto-fit (3+) | Full columns |
| Mobile | Scroll | 2 columns | Scrollable |

### Onboarding Wizard (`/console/onboard`)

| Breakpoint | Container | Form Rows | Nav Dots |
|------------|-----------|-----------|----------|
| Desktop | 800px max-width | Side by side | 8px dots |
| Tablet | 800px (fits in 900px content) | Side by side | 8px dots |
| Mobile | 100% width | Stacked | 24px dots (touch-friendly) |

---

## 19. Full CSS Implementation

Below is the complete CSS to append to the end of `/app/static/console/style.css`, replacing the existing `@media (max-width: 768px)` block.

```css
/* ============================================================
   RESPONSIVE DESIGN SYSTEM
   Breakpoints: Mobile (<768px) | Tablet (768-1023px) | Desktop (1024px+)
   ============================================================ */

/* -- Utility: Table scroll wrapper -- */
.table-scroll {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}

/* -- Column priority classes -- */
/* Applied to both <th> and <td> elements */
/* .col-essential — always visible (no class needed, default) */
/* .col-tablet — hidden on mobile */
/* .col-desktop — hidden on mobile and tablet */

/* ============================================================
   TABLET (768px - 1023px): Collapsed sidebar rail
   ============================================================ */
@media (min-width: 768px) and (max-width: 1023px) {

    /* --- Sidebar: Icon Rail --- */
    :root {
        --sidebar-w: 60px;
    }

    .sidebar {
        width: 60px;
    }

    .sidebar-logo {
        padding: 16px 8px;
        text-align: center;
        font-size: 18px;
        letter-spacing: 0;
    }

    .sidebar-logo small {
        display: none;
    }

    .sidebar-cta {
        padding: 12px 8px 0;
    }

    .btn-new-agent {
        padding: 10px 0;
        font-size: 0;
        gap: 0;
    }

    .btn-new-agent .nav-icon {
        font-size: 18px;
    }

    .nav-item {
        justify-content: center;
        padding: 12px 0;
        font-size: 0;
        border-right: none;
        min-height: 44px;
    }

    .nav-item .nav-icon {
        font-size: 18px;
        width: auto;
    }

    .nav-item.active {
        border-right: none;
        border-left: 2px solid var(--accent);
    }

    /* Hamburger stays hidden on tablet */
    .mobile-menu-toggle {
        display: none;
    }

    /* --- Layout adjustments --- */
    .main-content {
        margin-left: 60px;
    }

    /* --- Cards --- */
    .card-grid {
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    }

    /* --- Detail grid: equal columns --- */
    .detail-grid {
        grid-template-columns: 1fr 1fr;
        gap: 1rem;
    }

    /* --- Chat thread: full width --- */
    .chat-thread {
        max-width: 100%;
    }

    /* --- Messages layout: narrower contact list --- */
    .messages-layout {
        grid-template-columns: 220px 1fr;
    }

    /* --- Column hiding: desktop-only columns --- */
    .col-desktop {
        display: none;
    }

    /* --- Touch targets --- */
    .btn {
        min-height: 40px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }

    .btn-sm {
        min-height: 36px;
        padding: 0.375rem 0.75rem;
    }
}

/* ============================================================
   MOBILE (< 768px): Hamburger menu, stacked layouts
   ============================================================ */
@media (max-width: 767px) {

    /* --- Sidebar: Off-canvas drawer --- */
    .mobile-menu-toggle {
        display: flex;
    }

    .sidebar {
        transform: translateX(-100%);
        transition: transform 0.2s;
        position: fixed;
        z-index: 20;
        width: 220px;
    }

    .sidebar.open {
        transform: translateX(0);
    }

    .main-content {
        margin-left: 0;
    }

    .topbar {
        padding-left: 3.5rem;
    }

    .topbar h1 {
        font-size: 16px;
    }

    .content {
        padding: 1rem;
    }

    /* --- Cards: 2-col, with 1-col fallback --- */
    .card-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: 0.75rem;
    }

    .card {
        padding: 0.75rem;
    }

    .card-value {
        font-size: 20px;
    }

    /* --- Detail grid: stacked --- */
    .detail-grid {
        grid-template-columns: 1fr;
    }

    /* --- Profile: stacked --- */
    .profile-two-col {
        grid-template-columns: 1fr;
    }

    /* --- Tables --- */
    table {
        font-size: 13px;
    }

    th, td {
        padding: 0.5rem 0.5rem;
    }

    .col-desktop,
    .col-tablet {
        display: none;
    }

    /* --- Tab bar: horizontal scroll --- */
    .tab-bar {
        overflow-x: auto;
        white-space: nowrap;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
    }

    .tab-bar::-webkit-scrollbar {
        display: none;
    }

    .tab-btn {
        flex-shrink: 0;
        padding: 10px 16px;
    }

    /* --- Forms --- */
    .form-row {
        flex-direction: column;
        gap: 0;
    }

    input[type="text"],
    input[type="email"],
    input[type="password"],
    input[type="tel"],
    input[type="time"],
    input[type="date"],
    select,
    textarea {
        min-height: 44px;
        font-size: 16px;  /* Prevents iOS auto-zoom */
    }

    .filters {
        flex-direction: column;
        align-items: stretch;
    }

    .filters .form-group {
        width: 100%;
    }

    .filters .btn {
        width: 100%;
        text-align: center;
        min-height: 44px;
    }

    /* --- Messages layout: stacked --- */
    .messages-layout {
        grid-template-columns: 1fr;
        max-height: none;
    }

    .messages-contact-list {
        border-right: none;
        border-bottom: 1px solid var(--border);
        max-height: 300px;
    }

    /* --- Chat --- */
    .chat-thread {
        max-width: 100%;
    }

    .chat-msg {
        max-width: 95%;
    }

    .chat-meta {
        font-size: 10px;
    }

    /* --- Bar chart --- */
    .bar-chart {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        height: 80px;
    }

    .bar {
        min-width: 8px;
    }

    /* --- Wizard --- */
    .wizard-container {
        max-width: 100%;
    }

    .wizard-dots .dot {
        width: 24px;
        height: 24px;
        border-radius: 50%;
    }

    .wizard-dots .dot.active {
        width: 32px;
        border-radius: 12px;
    }

    .wizard-nav .btn {
        min-height: 44px;
    }

    .option-card {
        padding: 1rem;
    }

    .checkbox-item {
        padding: 0.75rem;
    }

    /* --- Touch targets --- */
    .btn {
        min-height: 44px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }

    .btn-sm {
        min-height: 36px;
        padding: 0.375rem 0.75rem;
        font-size: 13px;
    }

    .nav-item {
        min-height: 44px;
    }

    /* --- KB components --- */
    .kb-settings-row {
        flex-direction: column;
        align-items: flex-start;
    }

    .kb-item-actions {
        justify-content: flex-start;
    }

    /* --- Section titles --- */
    .section-title {
        font-size: 15px;
    }

    /* --- Manual page --- */
    .manual h1 { font-size: 22px; }
    .manual h2 { font-size: 18px; }
    .manual h3 { font-size: 15px; }

    .manual table {
        display: block;
        overflow-x: auto;
    }
}

/* --- Very narrow screens (< 400px) --- */
@media (max-width: 400px) {
    .card-grid {
        grid-template-columns: 1fr;
    }

    .login-container {
        margin: 10vh 1rem;
    }

    .topbar h1 {
        font-size: 14px;
    }
}
```

---

## Template Changes Required

The CSS above handles layout, but the following template changes are needed for column-hiding to work:

### 1. Add `.table-scroll` Wrappers

Wrap all `<table>` elements that lack an `overflow-x: auto` container in a `<div class="table-scroll">`:

**Files to update:**
- `tenants.html` — Wrap the agents table
- `conversations.html` — Wrap the conversations table
- `triggers.html` — Wrap the triggers table
- `costs.html` — Wrap both tables (model tier + per-agent)
- `billing.html` — Wrap subscriptions table, model tier table, per-agent cost table
- `health.html` — Wrap both error tables
- `errors.html` — Wrap both error tables

### 2. Add Column Priority Classes

Add `class="col-tablet"` or `class="col-desktop"` to appropriate `<th>` and `<td>` elements as specified in Section 5.

### 3. Extract Inline Styles to CSS Classes

Several templates use inline `style` attributes for layout (flex containers, button groups, etc.). These should be extracted to named classes so media queries can target them. Priority extractions:

- **Tenant detail header** (`display: flex; justify-content: space-between`) — Extract to `.page-header-actions`
- **Billing dropdown** (`position: absolute; right: 0; ...`) — Extract to `.dropdown-panel`
- **Tenant detail card-grid override** (`grid-template-columns: repeat(3, 1fr); max-width: 600px`) — Extract to `.card-grid--compact`

### 4. Add Sidebar Label Abbreviation for Tablet Rail

Update `base.html` to wrap nav item text in a `<span class="nav-label">` so the tablet rail can hide text via CSS:

```html
<!-- Before -->
<span class="nav-icon" aria-hidden="true">...</span> Home

<!-- After -->
<span class="nav-icon" aria-hidden="true">...</span>
<span class="nav-label">Home</span>
```

Then in CSS:
```css
@media (min-width: 768px) and (max-width: 1023px) {
    .nav-label {
        display: none;
    }
}
```

This is cleaner than `font-size: 0` and maintains accessibility (screen readers still read the text).

---

## Implementation Priority

| Phase | Work | Effort | Impact |
|-------|------|--------|--------|
| **Phase 1** | Replace existing 768px media query with new breakpoint system; add table scroll wrappers | Small | High — fixes all table overflow issues |
| **Phase 2** | Add tablet sidebar rail + `.nav-label` spans | Medium | High — proper iPad experience |
| **Phase 3** | Add column priority classes to all tables | Medium | Medium — cleaner mobile table views |
| **Phase 4** | Touch target sizing + iOS zoom fix (`font-size: 16px`) | Small | High — usability on all touch devices |
| **Phase 5** | Extract inline styles to CSS classes; wizard dot sizing | Small | Medium — polish |

---

## Testing Checklist

- [ ] Chrome DevTools responsive mode: 375px (iPhone SE), 390px (iPhone 14), 768px (iPad Mini), 810px (iPad), 1024px (iPad Pro landscape), 1280px (laptop)
- [ ] Safari on real iPad (if available) — test sidebar rail tap targets, table scroll, form zoom
- [ ] Tab through all interactive elements with keyboard at each breakpoint
- [ ] Verify sidebar overlay dismisses on touch outside (mobile)
- [ ] Verify all forms submit correctly on mobile (no clipped buttons)
- [ ] Verify onboarding wizard completes end-to-end on mobile
- [ ] Verify bar chart scrolls horizontally on narrow screens
- [ ] Verify billing "Change Plan" dropdown is usable on mobile
- [ ] Verify `prefers-reduced-motion` still disables animations
- [ ] Lighthouse mobile audit score > 90 for Performance and Accessibility
