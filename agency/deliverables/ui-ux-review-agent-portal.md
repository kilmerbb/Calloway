# UI/UX Review: Calloway Agent Portal

**Reviewer:** Lyra, Product Designer
**Date:** 2026-03-11
**Scope:** All agent portal screens (`/agent/*`) -- templates, CSS, route handler
**Files reviewed:** 12 (10 templates, 1 CSS file, 1 route handler)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Design System Specification](#2-current-design-system-specification)
3. [Screen-by-Screen Review](#3-screen-by-screen-review)
4. [Cross-Cutting Issues](#4-cross-cutting-issues)
5. [Prioritized Recommendations](#5-prioritized-recommendations)

---

## 1. Executive Summary

The agent portal is a competently built, mobile-first dashboard with a clean visual foundation. The CSS design tokens (custom properties), typography choices, and card-based layout are well-suited for the target audience of solo real estate agents who will primarily access this on their phones between showings.

However, the implementation has several structural inconsistencies, accessibility gaps, and missing interaction states that would degrade the production experience. The most critical issues are:

- **Two templates (`transactions.html`, `scores.html`) extend the wrong base template** (`base.html` instead of `agent/base.html`), which means they render without the agent portal's header, navigation, or CSS.
- **CSS class naming inconsistencies** between templates (e.g., `chip` vs. `filter-chip`, `stats-grid` vs. `card-grid`).
- **No loading states anywhere** -- HTMX requests have no visual feedback.
- **Duplicate/conflicting CSS rules** at the bottom of the stylesheet override earlier declarations.
- **No approval/rejection actions** on the pending approvals section of the dashboard, despite being the primary supervised-mode workflow.
- **Navigation has 8 items** in the mobile bottom bar, which is too many for comfortable thumb reach on a phone.

The foundation is solid. The issues are fixable without a redesign.

---

## 2. Current Design System Specification

### 2.1 Color Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#f8fafc` | Page background |
| `--bg-card` | `#ffffff` | Card/surface background |
| `--bg-hover` | `#f1f5f9` | Hover state, inbound chat bubble |
| `--border` | `#e2e8f0` | Card borders, dividers |
| `--text` | `#1e293b` | Primary text (slate-800) |
| `--text-muted` | `#64748b` | Secondary text, labels (slate-500) |
| `--accent` | `#2563eb` | Primary brand, links, active nav (blue-600) |
| `--accent-light` | `#eff6ff` | Accent background tint (blue-50) |
| `--green` | `#16a34a` | Success, confirmed status |
| `--green-light` | `#f0fdf4` | Success background tint |
| `--yellow` | `#ca8a04` | Warning, pending, on-hold |
| `--yellow-light` | `#fefce8` | Warning background tint |
| `--red` | `#dc2626` | Error, failed, STOP consent |
| `--red-light` | `#fef2f2` | Error background tint |

**Assessment:** The palette is drawn from the Tailwind CSS color scale (slate, blue, green, yellow, red). This is a strong, accessible foundation. However, `--accent` (#2563eb) on `--accent-light` (#eff6ff) produces a contrast ratio of approximately 4.8:1, which passes AA for normal text but may feel low on small badge text. There is no `stat-blue` class defined, yet it is used in `dashboard.html` for the Active Deals stat card, meaning the stat value for Active Deals gets no color treatment.

### 2.2 Typography

| Element | Font Size | Weight | Line Height | Transform |
|---------|-----------|--------|-------------|-----------|
| Body | 15px | 400 | 1.5 | -- |
| Logo | 18px | 700 | -- | -- |
| Section title | 16px (declared), 1.1rem (overridden at bottom) | 600 | -- | -- |
| Stat value | 28px (desktop), 22px (mobile) | 700 | 1.2 | -- |
| Stat label | 12px | -- | -- | uppercase, 0.5px tracking |
| List name | 14px | 500 | -- | -- |
| List meta/preview | 12-13px | -- | -- | -- |
| Badge | 11px | 600 | -- | -- |
| Chat message | 14px | -- | 1.4 | -- |
| Timestamp | 11px | -- | -- | -- |
| Nav link | 14px | 500 | -- | -- |
| Mobile nav label | 10px | -- | -- | -- |

**Font stack:** `-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif`

**Assessment:** Solid system font stack. The type scale is reasonable but has two `.section-title` declarations (lines 99-106 and 379-383) that conflict -- the second one overrides `font-size` from `16px` to `1.1rem` and drops the `display: flex` / `justify-content: space-between` behavior, which would break the "View all" links on the dashboard.

### 2.3 Spacing System

| Context | Value |
|---------|-------|
| Page padding | 1rem (desktop), 0.75rem (mobile) |
| Card padding | 1rem |
| Section margin-bottom | 1.25rem |
| Card grid gap | 0.75rem |
| List item padding | 0.75rem 1rem |
| List item gap | 0.75rem (between avatar and content) |
| List item margin-bottom | 0.5rem |
| Filter row gap | 0.5rem |
| Max content width | 900px |

**Assessment:** Spacing is consistent and comfortable for mobile. The 900px max-width is appropriate for the content density.

### 2.4 Components

#### Card (`.card`)
- White background, 1px border, 12px border-radius, subtle shadow
- Used as a container for timeline items, chat threads, contact headers

#### Stat Card (`.stat-card`)
- Extends `.card`, centered text
- Color variants: `stat-green`, `stat-yellow`, `stat-red` (no `stat-blue` defined)

#### List Item (`.list-item`)
- Flexbox row: avatar + content + right-aligned metadata
- Hover state with background change
- Used across dashboard, contacts, conversations, triggers

#### Avatar (`.list-avatar`)
- 40px circle, accent-light background, accent text
- Shows first letter of contact name
- No fallback image support

#### Badge (`.badge`)
- Inline pill, 6px radius, 11px bold text
- Variants: green, yellow, red, blue, gray

#### Filter Chip (`.filter-chip`)
- 20px radius pill, border-based
- Active state uses accent-light fill + accent border
- **Bug:** `transactions.html` uses class `chip` instead of `filter-chip`, so those filter buttons are unstyled

#### Search Bar (`.search-bar`)
- Full width, card-style with focus ring
- HTMX-driven with 300ms debounce

#### Chat Bubble (`.chat-msg`)
- 16px border-radius with directional flattening
- Inbound: gray background, outbound: accent blue with white text
- System: yellow-light, centered, italic

#### Timeline Item (`.timeline-item`)
- Flex row with time column (60px min-width) and content
- Separated by bottom borders
- Used for showings

#### Button (`.btn`)
- 10px radius, 15px font
- Variants: `btn-primary` (blue fill), `btn-outline` (border only), `btn-sm`
- Only used on the login page

#### Score Badge (`.score-badge`)
- 36px circle, color-coded by tier (hot=red, warm=amber, cool=blue, cold=gray)
- White text, centered number

#### Tag (`.tag`)
- Tiny pill for deadline labels in transaction cards
- Uses `--surface` variable which is **not defined** in the CSS custom properties, causing fallback to transparent or browser default

### 2.5 Layout Patterns

- **Mobile-first** with `@media (max-width: 768px)` breakpoint
- **Sticky header** (56px height, z-index 20)
- **Fixed bottom nav** on mobile (z-index 20)
- **Desktop:** Horizontal nav in header, no bottom nav
- **Mobile:** Header nav hidden, bottom tab bar shown
- **Content:** Single column, 900px max-width, centered

---

## 3. Screen-by-Screen Review

### 3.1 Login (`login.html`)

**Layout:** Centered form, 400px max-width, vertically offset by 10vh. Clean and minimal.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Good -- brand, subtitle, form fields, submit button follow natural flow | -- |
| Mobile | Good -- max-width constraints work well on small screens | -- |
| Components | Uses form-group, btn-primary consistently | -- |
| Empty/Error States | Error and success messages styled with background color + rounded box | Inline styles on error/message divs should be CSS classes |
| Accessibility | Has `autofocus`, `required`, `inputmode="numeric"`, `maxlength` | Missing `autocomplete="tel"` on phone field; missing `aria-live="polite"` on error/success messages so screen readers do not announce them |
| Flow | Two-step (phone, then code) in single form is slightly confusing | No visual indication that the flow is step-based; both fields are always visible |

**Specific issues:**
1. The form does not visually separate the "request code" step from the "enter code" step. A user might type both phone and code on first visit and get confused.
2. No `<form novalidate>` -- browser native validation will fire before the server-side flow.
3. CSRF token is present -- good.
4. Standalone HTML (does not extend `agent/base.html`) -- appropriate for a login page, but means the login page does not load HTMX (which is fine since it does not use it).

### 3.2 Dashboard (`dashboard.html`)

**Layout:** Stat cards grid -> pending approvals -> upcoming showings -> recent messages -> active listings. Good information hierarchy for a daily command center.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Strong -- "Today" stats at top, action items next, then reference content | "Need Approval" items lack action buttons (approve/reject) |
| Mobile | Card grid goes to 2-column on mobile -- works well | 5 stat cards in a 2-col grid leaves 1 orphan card spanning full width on last row |
| Components | Consistent use of list-item, badge, timeline-item, stat-card | `stat-blue` class used on Active Deals card but never defined in CSS |
| Empty States | Conversations section has an empty state; showings and listings sections use `{% if %}` to hide entirely when empty | Inconsistent: some sections vanish, others show empty state. Vanishing sections make the page feel barren for new users. |
| Loading States | None | No HTMX loading indicators |
| Accessibility | Section titles are `<div>`, not heading elements | Should use `<h2>` for section titles; approval items have no interactive affordance (no buttons, no links) |

**Specific issues:**
1. **Pending approvals have no actions.** The entire supervised-mode approval workflow surfaces draft responses but provides no way to approve, edit, or reject them from this screen. This is the single biggest functional gap in the portal.
2. Inline styles on "View all" badges (`style="text-decoration:none;"`) should be handled in CSS.
3. Listing items have no links -- there is no listing detail page or action available.
4. The pending approvals section shows `draft_response` truncated to 80 chars but does not link to a detail view to see the full draft.

### 3.3 Conversations List (`conversations.html`)

**Layout:** Search bar + conversation list. Simple and effective.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Good -- search prominent, then chronological list | -- |
| Mobile | Full-width search and list items work well | -- |
| Components | Consistent list-item pattern, channel shown as badge | Inline style on `<a>` tags (`style="text-decoration:none; color:inherit;"`) should be a CSS class |
| Empty States | Present and appropriate | -- |
| Loading States | None | HTMX search triggers re-render but no `hx-indicator` is defined; screen flashes without feedback |
| Accessibility | Search input lacks `<label>` element (has placeholder only) | No `aria-label` on search input; conversation items are links but the entire `<a>` wraps a div, which is valid HTML5 but the hit target is the full row -- good for mobile |

**Specific issues:**
1. No unread count badges on conversation items (the dashboard version has them, but the full list view does not).
2. No pagination -- limited to 50 results in the backend. If an agent has 200+ conversations, older ones are inaccessible.
3. Search only filters by contact name, not message body -- may confuse users who search for message content.

### 3.4 Conversation Detail (`conversation_detail.html`)

**Layout:** Back link -> contact header card -> chat thread. Follows native messaging app patterns.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Good -- contact info at top, messages in chronological order | -- |
| Mobile | Chat bubbles at 80% max-width work well | Contact header card uses inline styles for layout instead of CSS class |
| Components | Chat bubbles, delivery status indicators, AI attribution | -- |
| Empty States | Present for no-messages case | -- |
| Accessibility | Delivery status uses only color and unicode symbols | Failed delivery warning symbol is good, but checkmarks are not announced by screen readers; no `aria-label` on delivery status |

**Specific issues:**
1. **No reply/compose functionality.** The agent can view the conversation but cannot send a message from this screen. This is a significant gap -- the agent must leave the portal to respond.
2. **No auto-scroll to bottom.** New conversations open at the top, requiring the agent to scroll down to see the most recent messages.
3. Chat thread has `max-width: 600px` in CSS but is inside a 900px container with no centering, so it left-aligns on desktop. Minor but looks unfinished.
4. Heavy use of inline styles on the contact header card.
5. No real-time updates (polling or WebSocket). If a new message arrives while viewing, the agent must manually refresh.

### 3.5 Contacts (`contacts.html`)

**Layout:** Search -> role filters -> source filters -> contact list + count. Well-structured for browsing and filtering.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Good -- filters narrow progressively, results list, count at bottom | -- |
| Mobile | Filter chips scroll horizontally (overflow-x: auto) -- good | -- |
| Components | Consistent use of filter-chip, list-item, badge | -- |
| Empty States | Present with helpful message | -- |
| Accessibility | No `<label>` on search input | HTMX search has same no-indicator issue as conversations |

**Specific issues:**
1. **Contact items are not clickable/linkable.** There is no contact detail page. Agent cannot view full contact information, edit notes, or see conversation history for a specific contact.
2. Filter combinations are not supported -- clicking "Buyers" then a source filter navigates to `?source=X` which drops the role filter. The filters are mutually exclusive between rows but this is not visually communicated.
3. HTMX search only targets `#contactList`, so filter chips above do not reset when searching. The interaction model between search and filters is unclear.
4. TCPA consent status (`STOP` badge) is shown but there is no way to manage consent from this screen.

### 3.6 Schedule (`schedule.html`)

**Layout:** Status filters -> today's showings timeline -> upcoming showings timeline. Clean temporal organization.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Good -- today first, then future | -- |
| Mobile | Timeline layout works well on narrow screens | -- |
| Components | Consistent timeline-item, filter-chip, badge usage | -- |
| Empty States | Present with helpful message | -- |
| Accessibility | Status badges use color only for meaning | Hold badge includes text "hold" which helps; but confirmed badge relies on green color |

**Specific issues:**
1. **No ability to cancel or reschedule showings.** Read-only view.
2. No past showings -- once a showing passes today, it vanishes. No history view.
3. Hold status shows expiration time, which is useful context.
4. No integration with external calendar (Google Calendar link or .ics download).

### 3.7 Triggers / Reminders (`triggers.html`)

**Layout:** Type filters -> trigger list. Simple and functional.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Adequate -- filters and flat list | -- |
| Mobile | Works well | -- |
| Components | Consistent filter-chip, list-item, badge | Message template preview uses inline style instead of a class |
| Empty States | Present with helpful message | -- |
| Accessibility | Same color-only status issue | -- |

**Specific issues:**
1. **No ability to cancel, snooze, or edit triggers.** Read-only.
2. Completed and pending triggers are mixed in the same list with no visual separation. Could benefit from grouping (upcoming vs. completed).
3. Time format uses 24-hour (`%H:%M`) while the rest of the portal uses 12-hour AM/PM. Inconsistent.
4. No pagination -- limited to 50 results.

### 3.8 Campaigns (`campaigns.html`)

**Layout:** Two sections: Active Campaigns and Active Enrollments. Clear separation of concerns.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Good -- campaigns first, then who is enrolled | Section titles use `<h2>` with class `section-title`, which is correct semantically but different from other pages that use `<div class="section-title">` |
| Mobile | Works well | -- |
| Components | Uses list-item, badge consistently | -- |
| Empty States | Both sections have empty states with actionable messaging | -- |
| Accessibility | Semantically better than other pages due to `<h2>` usage | -- |

**Specific issues:**
1. **No CRUD operations.** Cannot create, edit, pause, or delete campaigns. Cannot enroll or unenroll contacts.
2. Campaign step count is shown but no way to view the steps.
3. Second section title uses inline `style="margin-top: 2rem;"` instead of a CSS class.
4. Duration calculation (`c.steps[-1].day`) would error if steps is empty, though the template guards with `if c.steps`.

### 3.9 Transactions (`transactions.html`)

**CRITICAL BUG: Extends `base.html` instead of `agent/base.html`.** This template will render with the admin console's base layout (or a missing template error), not the agent portal layout. The agent portal's header, navigation, mobile nav bar, and CSS will all be missing.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Good -- filters, then card list | -- |
| Mobile | Would be fine if rendered correctly | **Broken due to wrong base template** |
| Components | Uses `chip` class instead of `filter-chip` | `chip` is not defined in agent CSS; filter buttons will be unstyled |
| Empty States | Minimal -- plain text "No transactions found." without icon or helpful message | Inconsistent with other pages |
| Accessibility | Status colors provide text labels too | -- |

**Specific issues:**
1. **Wrong base template** -- this page is broken in production.
2. CSS class `chip` does not exist in `style.css` -- should be `filter-chip`.
3. Transaction cards use `card-header`, `card-body`, `card-footer` structure that is only partially styled. The `.tag` component references `--surface` variable which is undefined.
4. No links to related contacts or conversations.
5. Empty state lacks the icon + description pattern used elsewhere.

### 3.10 Scores (`scores.html`)

**CRITICAL BUG: Extends `base.html` instead of `agent/base.html`.** Same broken-rendering issue as transactions.

| Aspect | Assessment | Issues |
|--------|------------|--------|
| Hierarchy | Good -- tier summary stats, then scored contact list | -- |
| Mobile | Stats grid collapses to 2-column -- would work if rendered correctly | **Broken due to wrong base template** |
| Components | Uses `stats-grid` (defined in agent CSS), `score-badge`, card pattern | -- |
| Empty States | Minimal -- "No contacts to score." without icon | -- |
| Accessibility | Score badges use color + number | Tier badge uses color alone without the word "hot"/"warm" in the badge itself (the separate text badge does have it) |

**Specific issues:**
1. **Wrong base template** -- this page is broken in production.
2. Inline computation of tier counts (`contacts | selectattr('tier', 'equalto', 'hot') | list | length`) in the template. This filtering runs 4 times over the full contact list. Should be computed in the route handler.
3. No explanation of what the score means or how it is calculated. A new agent would not understand the numbers.
4. Empty state is bare compared to other pages.

---

## 4. Cross-Cutting Issues

### 4.1 Broken Templates (Severity: Critical)

`transactions.html` and `scores.html` extend `base.html` instead of `agent/base.html`. These two pages will either:
- Render with the admin console layout (wrong navigation, wrong context)
- Error out if `base.html` expects different template variables

**Fix:** Change line 1 of both files from `{% extends "base.html" %}` to `{% extends "agent/base.html" %}`.

### 4.2 No Loading States (Severity: High)

The portal uses HTMX for search on conversations and contacts, but there is no `hx-indicator` attribute or `.htmx-indicator` CSS class anywhere. Users get no feedback that their search is being processed. On slow connections, this will feel broken.

**Fix:** Add a loading spinner component and wire it with `hx-indicator`.

### 4.3 No Write Operations (Severity: High)

The entire portal is read-only. An agent can view their data but cannot:
- Approve or reject pending messages (the primary supervised-mode action)
- Reply to conversations
- Cancel or reschedule showings
- Create or manage contacts
- Manage campaigns or enrollments
- Cancel triggers

For a "command center," this severely limits utility. The agent must fall back to other tools (admin console, phone) for any action.

### 4.4 Duplicate CSS Declarations (Severity: Medium)

The CSS file has duplicate rules:
- `.section-title` is defined at line 99 (with `display: flex`, `font-size: 16px`) and again at line 379 (with `font-size: 1.1rem`, no flex). The second declaration wins for shared properties, breaking the "View all" link alignment on the dashboard.
- `.empty-state` is defined at line 236 (with `padding: 3rem 1rem`) and again at line 384 (with `padding: 2rem 1rem`). The second wins, reducing whitespace.

**Fix:** Remove the duplicate declarations at the bottom of the file (lines 379-388) or consolidate them.

### 4.5 Inconsistent Class Naming (Severity: Medium)

| Template | Uses | Should Use |
|----------|------|------------|
| `transactions.html` | `.chip` | `.filter-chip` |
| `scores.html` | `.stats-grid` | `.card-grid` or keep `.stats-grid` (it is defined) |
| `dashboard.html` | `.stat-blue` | Not defined; needs to be added to CSS |
| Multiple | Inline styles for flex layout | Dedicated CSS classes |

### 4.6 Navigation Overload (Severity: Medium)

The mobile bottom nav bar has 8 items: Home, Contacts, Messages, Schedule, Deals, Reminders, Scores, Campaigns. Standard mobile practice is 4-5 items max. At 8, each item gets very narrow, labels may truncate, and icons are too small for comfortable tapping (well below the 48px minimum touch target recommended by WCAG 2.1).

**Fix:** Reduce to 5 primary nav items (Home, Contacts, Messages, Schedule, Deals) and move Reminders, Scores, and Campaigns to a "More" menu or into sub-navigation accessible from the dashboard.

### 4.7 Accessibility Gaps (Severity: Medium)

| Issue | Location | Fix |
|-------|----------|-----|
| Section titles use `<div>` not `<h2>` | Dashboard, schedule, all list pages | Use semantic headings |
| Search inputs lack `<label>` | Conversations, contacts | Add `<label>` (can be visually hidden) or `aria-label` |
| Duplicate `aria-label="Main navigation"` on both header and mobile nav | base.html | Differentiate: "Desktop navigation" and "Mobile navigation" |
| No skip-to-content link | base.html | Add `<a href="#main-content" class="sr-only">Skip to content</a>` |
| Error/success messages not announced | login.html | Add `role="alert"` or `aria-live="polite"` |
| Color-only status indicators | Multiple | Already partially mitigated by text labels in badges, but some rely on color alone |
| No focus ring styles defined | CSS | Browsers provide default, but a custom `:focus-visible` style would be more consistent |
| Missing `autocomplete="tel"` | login.html phone input | Add attribute for autofill support |

### 4.8 Missing Pagination (Severity: Low)

Backend queries use `LIMIT 50` on conversations, triggers, and transactions. There is no "Load more" or pagination UI. For agents with high volume, older data is inaccessible.

### 4.9 Inline Styles (Severity: Low)

Multiple templates use inline `style` attributes for layout, spacing, and sizing. This creates maintenance burden and makes the design system harder to evolve. Notable offenders:
- `conversation_detail.html`: Contact header card layout is entirely inline-styled
- `dashboard.html`: "View all" links with `style="text-decoration:none;"`
- `campaigns.html`: Section spacing with `style="margin-top: 2rem;"`
- `login.html`: Error/success message styling
- `contacts.html`: Source filter row with `style="margin-top:0;"`

### 4.10 Missing `stat-blue` Class (Severity: Low)

`dashboard.html` uses `stat-blue` on the Active Deals stat card, but the CSS only defines `stat-green`, `stat-yellow`, and `stat-red`. The blue stat value falls back to the default dark text color, making it visually inconsistent with the other colored stat cards.

### 4.11 Undefined CSS Variable (Severity: Low)

The `.tag` component (used in transaction card footers for deadline labels) references `--surface` as its background color, but `--surface` is never defined in the `:root` custom properties. This causes the tags to render with a transparent or browser-default background.

---

## 5. Prioritized Recommendations

### P0 -- Fix Before Ship (Broken Functionality)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 1 | **Fix base template inheritance** in `transactions.html` and `scores.html` (change `base.html` to `agent/base.html`) | 5 min | These pages are completely broken |
| 2 | **Fix CSS class mismatch** in `transactions.html` (`chip` to `filter-chip`) | 2 min | Filter buttons are unstyled/invisible |
| 3 | **Remove duplicate CSS rules** for `.section-title` and `.empty-state` at bottom of stylesheet (lines 379-388) | 5 min | Conflicting declarations break dashboard layout |
| 4 | **Add `stat-blue` CSS class** (`.stat-blue .stat-value { color: var(--accent); }`) | 1 min | Active Deals stat shows no color treatment |
| 5 | **Define `--surface` CSS variable** or replace `.tag` background with an existing token | 1 min | Transaction deadline tags have no visible background |

### P1 -- High Priority (Core UX Gaps)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 6 | **Add approve/reject actions to pending approvals** on dashboard | Medium | This is the primary agent action in supervised mode; currently impossible from the portal |
| 7 | **Add HTMX loading indicators** to search bars (add `hx-indicator` and `.htmx-indicator` CSS) | Small | Users get no feedback during search; feels broken on slow connections |
| 8 | **Add reply/compose to conversation detail** | Medium | Agents cannot respond to messages from the portal |
| 9 | **Reduce mobile nav to 5 items** + "More" overflow | Small | 8 items is too many; small tap targets, label truncation |
| 10 | **Add accessible labels** to search inputs, differentiate nav landmarks, add skip-to-content link | Small | Screen reader users cannot navigate effectively |

### P2 -- Medium Priority (Polish and Consistency)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 11 | **Use semantic headings** (`<h2>`) for section titles across all pages | Small | Improves accessibility and document outline |
| 12 | **Extract inline styles to CSS classes** across all templates | Small | Maintainability; enables design system evolution |
| 13 | **Standardize empty states** -- all pages should use icon + descriptive message pattern | Small | Transactions and scores have bare empty states |
| 14 | **Make contact list items clickable** -- link to a contact detail view | Medium | Agents need to view/manage individual contacts |
| 15 | **Standardize time format** -- triggers use 24-hour, rest uses 12-hour AM/PM | Small | Inconsistency confuses users |
| 16 | **Add empty-state sections** for showings and listings on dashboard instead of hiding them | Small | New agents see a nearly blank dashboard, which is disorienting |
| 17 | **Move template-level computation** (score tier counting in `scores.html`) to route handler | Small | Performance and separation of concerns |
| 18 | **Add `role="alert"` to login error/success messages** | Small | Screen reader announcement |
| 19 | **Add unread badges to conversation list** (present on dashboard but missing from full list) | Small | Consistency between views |
| 20 | **Center chat thread on desktop** (add `margin: 0 auto` to `.chat-thread`) | Small | Currently left-aligned inside 900px container |

### P3 -- Nice to Have (Future Enhancements)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 21 | **Add pagination or infinite scroll** to conversations, contacts, triggers, transactions | Medium | Agents with 50+ items lose access to older data |
| 22 | **Add auto-scroll to bottom** of conversation detail | Small | Natural chat behavior |
| 23 | **Add real-time updates** to conversation detail (HTMX polling or SSE) | Medium | Messages arrive but agent must manually refresh |
| 24 | **Add campaign CRUD** | Large | Campaigns are view-only; agents cannot create or manage them |
| 25 | **Add showing cancellation/rescheduling** | Medium | Schedule is read-only |
| 26 | **Add score explanation tooltip** on scores page | Small | Agents do not understand what the number means |
| 27 | **Support combined filters** on contacts (role + source simultaneously) | Small | Currently clicking one filter row resets the other |
| 28 | **Add conversation filters** (All / Unread / SMS / Voice) | Small | No way to filter conversations by channel or read status |
| 29 | **Add date group headers to upcoming showings** in schedule | Small | Multiple showings on different dates run together with no separation |
| 30 | **Replace HTML entity icons** in mobile nav with SVG icon set for cross-browser consistency | Medium | Current entities render differently across platforms |

---

## Appendix: Component Inventory

| Component | CSS Class | Used In | Notes |
|-----------|-----------|---------|-------|
| Card | `.card` | dashboard, schedule, conversation_detail, scores, transactions | Core container |
| Stat Card | `.stat-card` | dashboard | Missing `stat-blue` variant |
| List Item | `.list-item` | dashboard, conversations, contacts, triggers, campaigns | Primary list pattern |
| Avatar | `.list-avatar` | dashboard, conversations, contacts, conversation_detail | First-letter only |
| Badge | `.badge` + variant | all pages | 5 color variants |
| Filter Chip | `.filter-chip` | contacts, schedule, triggers | NOT used in transactions (uses `chip`) |
| Search Bar | `.search-bar` | conversations, contacts | HTMX-driven, no loading indicator |
| Chat Bubble | `.chat-msg` + variant | conversation_detail | 3 variants: inbound, outbound, system |
| Timeline | `.timeline-item` | dashboard, schedule | For showing events |
| Button | `.btn` + variant | login only | Not used elsewhere in portal |
| Score Badge | `.score-badge` + tier | scores | 4 tier colors |
| Tag | `.tag` | transactions | Uses undefined `--surface` var |
| Empty State | `.empty-state` | all pages | Inconsistent format (some have icons, some do not); duplicate CSS rule |
| Section Title | `.section-title` | all pages | Duplicate CSS rules with conflicting values |
| Card List | `.card-list` | campaigns, transactions, scores | Vertical stack layout |
| Stats Grid | `.stats-grid` | scores | 4-column, collapses to 2 on mobile |

---

*End of review.*
