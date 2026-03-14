# Calloway Admin Console — UX Audit

**Auditor:** Lyra, Product Designer
**Date:** 2026-03-14
**Scope:** All `/console` templates, static CSS/JS, and backend route logic
**Standard:** Consumer-grade SaaS admin console (Stripe Dashboard, Linear, Vercel)

---

## 1. Executive Summary

### Overall UX Grade: **B-**

The console is functional and shows strong foundational thinking — the Spotify-inspired dark theme is cohesive, the sidebar overhaul is clean, the onboarding wizard is genuinely excellent, and the recent Messages tab redesign with the split-pane contact list is solid interaction design. Accessibility basics are in place (skip-nav, ARIA roles, focus-visible, reduced-motion media query). Tooltips on nearly every element show care for discoverability.

However, the console is not yet consumer-grade. There are significant gaps in action feedback, loading states, error handling, and several visual inconsistencies that create a "developer tool" feel rather than a polished product. An investor walking through this during a demo would notice the rough edges.

### Top 5 Issues

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 1 | **No toast/notification system for action feedback** — Deactivate, Test SMS, Retry, Cancel, Run Now, plan changes, KB operations all redirect with zero confirmation that the action succeeded or failed | Critical | Users perform destructive actions with no feedback loop |
| 2 | **Template filename mismatch — partial templates will 404** — `console.py` references `partials/tenant_messages_tab.html`, `partials/tenant_messages_thread.html`, and `partials/tenant_kb_tab.html` but actual files are `messages_contacts.html`, `messages_thread.html`, `knowledge_base.html` | Critical | Messages tab and Knowledge Base tab will fail to render |
| 3 | **No pagination on any table** — Customers, Conversations, Automations, Errors all load unbounded result sets in a single HTML table | Major | Will degrade badly at 100+ agents or 1000+ conversations |
| 4 | **Inline styles everywhere** — Over 100 instances of `style="..."` across templates, making visual consistency fragile and maintenance painful | Major | Prevents systematic design token adoption |
| 5 | **No success/error feedback after form submissions** — New Customer, Edit Customer, Onboard Wizard, KB upload, billing plan changes silently redirect on success | Major | Users don't know if their action worked |

---

## 2. Page-by-Page Audit

### 2.1 Login (`login.html`)

**What works well:**
- Clean, centered card layout
- Autofocus on password field
- Error state displayed via `.alert-error`
- CSRF token present

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Minor | No "show password" toggle — single field with no visual indicator of what was typed | Add an eye icon toggle button |
| Minor | No branding beyond "Calloway" text — no logo, no tagline | Add a small logo or icon above the title |
| Polish | Submit button says "Sign In" but no loading state while authenticating | Add `hx-indicator` or disable button on submit |
| Polish | No "Forgot password?" help text explaining that `CONSOLE_PASSWORD` is an env var | Add a subtle hint for operators who may not know where the password lives |

### 2.2 Dashboard (`dashboard.html`)

**What works well:**
- Pulse cards are clean with good metric selection
- Activity feed auto-refreshes (15s)
- "Needs Attention" panel is operationally useful
- Error count turns red when > 0
- "All clear" empty state for attention panel

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | Activity feed "Loading..." text is plain — no skeleton loader on initial load | Add `.loading-skeleton` pattern matching what Messages tab uses |
| Minor | No click-through from pulse cards — "Messages Today" and "Errors 24h" should link to Messages and Health pages | Wrap cards in `<a>` tags to their respective pages |
| Minor | "Needs Attention" section uses inline styles (`style="margin-bottom: 1rem;"`, `style="color: var(--red);"`) instead of classes | Extract to CSS classes `.attention-errors`, `.attention-inactive` |
| Minor | Activity feed items have no max-height or scroll — with 20 items, the feed could push "Needs Attention" out of viewport | Add `max-height` and `overflow-y: auto` to the feed container |
| Polish | No relative timestamps ("2 min ago") — only absolute timestamps | Use relative time for items within the last hour |
| Polish | "All clear." empty state is minimal — no icon, no positive reinforcement | Add a checkmark icon and "All systems running smoothly" |

### 2.3 Customers List (`tenants.html`)

**What works well:**
- Search filter works
- Status badges are clear and well-colored
- "New Customer" CTA is prominent
- Empty state for no results exists

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | No pagination — all agents rendered in one table | Add server-side pagination with page controls |
| Major | Table is not sortable — no click-to-sort on columns | Add sortable column headers (at minimum: Name, Messages Today, Last Active, Errors) |
| Minor | Search form requires a separate "Filter" button click — no instant search | Add `hx-trigger="keyup changed delay:300ms"` for live filtering |
| Minor | Twilio number column takes up space at font-size 12px but isn't very useful at a glance | Consider hiding this column by default or moving it to a detail view |
| Minor | "No customers found" empty state is barebones — just text in a table cell | Show a proper empty state illustration with CTA to create first customer |
| Polish | Status logic is fragile — checks `a.last_active.isoformat is defined` which is a Jinja2 hack | Move status computation to the backend (`console.py`) |

### 2.4 Customer Detail (`tenant_detail.html`)

**What works well:**
- 6-tab layout with keyboard navigation (arrow keys, Home/End)
- URL hash syncing for deep linking
- ARIA roles and `aria-controls` properly wired
- Profile two-column layout is clean
- Expandable config sections via `<details>` are appropriate
- Messages tab has skeleton loaders
- Contact and Listings tables have proper empty states
- Automations have a client-side status filter

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Critical | "Test SMS" and "Deactivate" give no feedback — redirect to same page with no success/error message | Add flash message or toast notification system |
| Major | Raw Agent Record dumps the entire Python object as a string — not formatted JSON | Use `{{ agent | tojson(indent=2) }}` for pretty-printed JSON |
| Major | Contacts table has 9 columns — overflows on anything less than a wide desktop | Add horizontal scroll wrapper (already done for Listings) and consider a more compact layout |
| Minor | Tab bar uses text-only Unicode icons — "Profile", "Messages", "Knowledge Base" etc. have no visual icons | Add small SVG icons to each tab for faster scanning |
| Minor | Profile table uses raw HTML `<table>` for key-value pairs — semantically this should be a `<dl>` | Refactor to description list or use a `.key-value` component |
| Minor | KB "Add Document" form validation happens server-side only (400 response) — user sees a raw error page | Add client-side required validation and display errors inline |
| Minor | KB form action URL is `/console/tenants/{{ agent.id }}/knowledge-base/add` but the backend route is `/console/tenants/{agent_id}/kb/upload` — potential mismatch | Verify URL routing; this looks like a bug |
| Polish | Automations count in section title shows `detail.pending_triggers|length` but "pending" is misleading if the filter shows all statuses | Dynamically update the count based on the active filter |
| Polish | Configuration `<pre>` blocks use inline `style="font-size:12px; padding:0.5rem;"` | Extract to a `.config-pre` class |

### 2.5 Customer Edit (`tenant_edit.html`)

**What works well:**
- Error display via `.alert-error`
- CSRF protection
- Cancel link goes back to detail page
- Timezone dropdown with human-readable names

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | No unsaved changes warning — navigating away loses all edits | Add `beforeunload` listener when form is dirty |
| Major | Labels say "Agent Profile" — should say "Customer Profile" per jargon cleanup | Rename section title |
| Minor | No success feedback after save — redirects silently | Add flash message "Settings saved successfully" |
| Minor | Only 4 timezone options — no support for Hawaii, Alaska, or non-US timezones | Expand timezone list or use a searchable dropdown |
| Minor | System Prompt Override textarea has no character count or size guidance | Add a character counter and guidance text |
| Polish | "Save Changes" button has no loading state | Disable on submit and show spinner |

### 2.6 New Customer (`tenant_new.html`)

**What works well:**
- Required fields marked with *
- E.164 format placeholder on phone fields
- Error display present

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | Also says "Agent Profile" instead of "Customer Profile" | Fix jargon |
| Minor | Buffer Minutes field is `type="text"` — should be `type="number"` or a `<select>` | Use a select dropdown matching the wizard's pattern |
| Minor | No field hints (unlike the wizard which has `.form-hint` on every field) | Add hints explaining each field |
| Minor | No inline validation — phone format isn't validated client-side | Add pattern attribute for E.164 validation |
| Polish | Form is basic compared to the onboarding wizard — for a quick add this is fine, but the two experiences feel disconnected | Consider deprecating this form in favor of the wizard |

### 2.7 Onboarding Wizard (`onboard_wizard.html` + `onboard_success.html`)

**What works well:**
- Excellent 7-step wizard with progress bar and dot navigation
- Step validation before advancing
- Option cards for tone/autonomy/after-hours are best-in-class interaction design
- Review summary on Step 7 is comprehensive
- Dynamic listing/client management (add/remove)
- `fadeIn` animation on step transition
- XSS prevention with `escapeHtml()`
- Success page with checklist and next steps
- Error on required field highlights border red with 2s timeout

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Minor | Back navigation via browser history doesn't work (wizard state is JS-only) | Add `popstate` handler or use URL hash for step state |
| Minor | Dot navigation only allows going backward, not forward (even if steps were completed) — this is actually correct UX, but there is no visual affordance explaining why | Add `cursor: not-allowed` or tooltip on future dots |
| Minor | Error state on wizard submission uses the same page reload — if validation fails, all wizard state is lost | Preserve form data on error (pre-fill from submitted values) |
| Minor | Listing Price field is `type="text"` — no numeric validation | Add input masking or `pattern` attribute |
| Polish | "Create Agent Instance" button — should say "Create Customer" per jargon cleanup | Fix label |
| Polish | Client entry uses `.listing-header` class — copy-paste artifact | Rename to `.entry-header` or `.item-header` |

### 2.8 Conversations List (`conversations.html`)

**What works well:**
- Three filters (Customer, Channel, Search) cover main use cases
- Message preview truncated at 80 chars with ellipsis
- Empty state present

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | No pagination — `limit=100` in backend but no page controls | Add pagination |
| Minor | "Last Message" column truncation uses inline `style="max-width:300px"` | Move to CSS class |
| Minor | No unread/new message indicator | Add visual distinction for conversations with recent inbound messages |
| Polish | Channel filter options are lowercase ("sms", "rcs") — should be display-formatted | Show "SMS", "RCS", "Voice", "Email" |

### 2.9 Conversation Detail (`conversation_detail.html`)

**What works well:**
- Chat thread layout with client/AI/system message differentiation
- Metadata on each message (model, tokens, intent, feedback score)
- Inline tool execution expandable blocks
- Sidebar with contact info and active automations

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | No pagination or "load more" — all messages loaded at once | Add pagination or infinite scroll |
| Major | Tool execution display logic is broken — the nested loop with `loop.first` and `loop.index` check doesn't correctly interleave tool calls between messages | Refactor to pre-process message+tool interleaving in the backend |
| Minor | No "back to conversations" breadcrumb | Add a breadcrumb or back arrow |
| Minor | Chat bubbles are left-aligned for AI too — AI messages should right-align (they have `margin-left: auto` but within a flex container this may not work) | Verify visual alignment and add `display: flex; flex-direction: column;` to `.chat-thread` |
| Polish | Feedback score display is raw number with no context — "feedback: 4" means nothing to the operator | Add a label like "Quality: 4/5" or use star icons |

### 2.10 Automations (`triggers.html`)

**What works well:**
- Status and customer filters
- Action buttons (Retry, Run Now, Cancel) are context-appropriate
- Confirmation dialogs before destructive actions
- Status badges are well-differentiated

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | No pagination | Add pagination |
| Major | "Run Now" confirmation says "sends a real message" — this is good, but there is no post-action feedback | Add success/error flash message |
| Minor | "Actions" column can contain 3 buttons for pending triggers — column gets wide | Consider a dropdown or kebab menu for actions |
| Minor | No timestamp format for when the automation was actually executed | Add "Executed At" column for completed triggers |
| Polish | Trigger type values like `follow_up`, `review_request` use snake_case — not human-friendly | Format with `{{ t.trigger_type | replace('_', ' ') | title }}` |

### 2.11 Costs (`costs.html`)

**Note:** This page now redirects to `/console/billing?tab=ai-costs`, so the standalone template is likely unused. However, it's still in the codebase and the routing exists.

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Minor | Dead template — duplicates content now in billing.html AI Costs tab | Remove `costs.html` template to avoid confusion |

### 2.12 Billing (`billing.html`)

**What works well:**
- Two-tab layout (Subscriptions + AI Costs) is good consolidation
- Plan tier cards with feature lists
- Message usage progress bars with color thresholds (green/yellow/red)
- Revenue summary cards
- "Change Plan" dropdown using `<details>` is clever
- Cost-per-customer table with $15 threshold highlighting

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | Plan change and cancellation give zero feedback — silent redirect | Add flash message |
| Major | "Change Plan" dropdown closes when clicking inside it (native `<details>` behavior on some browsers) | Use a proper modal or dropdown component |
| Minor | AI Costs tab is a complete duplicate of the old `costs.html` content — DRY violation | Extract to a shared partial |
| Minor | Bar chart has no x-axis labels — only tooltip on hover reveals the date | Add at least first/last date labels, or every 7th day |
| Minor | Bar chart has no y-axis labels — no scale reference | Add a y-axis with dollar amounts |
| Minor | Subscriptions table has no pagination | Add pagination for 50+ subscribers |
| Polish | "Cancel Subscription" button is within the "Change Plan" details dropdown — feels buried and also makes it easy to accidentally cancel | Move cancel to a separate, more deliberate flow |
| Polish | Revenue Summary uses complex Jinja2 filters inline — hard to read and maintain | Compute in backend and pass as template variables |

### 2.13 System Health (`health.html`)

**What works well:**
- Auto-refresh every 30 seconds with HTMX
- 4-tab layout is comprehensive (Services, Response Times, Errors, Actions)
- Status dots with text labels for accessibility
- Service connectivity cards with color coding
- Response time percentiles (avg, p50, p95) are operationally useful
- Error tables with expandable details

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Major | Auto-refresh replaces the entire `.content` div — if user has an error `<details>` expanded, it closes on refresh | Use more targeted HTMX swaps or preserve open state |
| Major | "Run Check" action gives no feedback | Add success message |
| Minor | Services tab shows colored dots but no uptime history or trend | Add a simple uptime indicator (e.g., "Last 24h: 99.8%") |
| Minor | Response Times has only 3 cards — page feels sparse | Add a simple latency trend chart (like the cost bar chart) |
| Minor | Error tables have no pagination | Add pagination |
| Minor | "Actions" tab has only one action — feels empty | Add more operational actions (clear error log, force health check, etc.) |
| Polish | Tab switching uses server-side `active_tab` query param for Errors tab filter state, but client-side JS for tab display — inconsistent | Standardize on one approach |

### 2.14 Errors (`errors.html`)

**Note:** This page redirects to `/console/health?tab=errors`. Template exists but is redundant.

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Minor | Dead template — duplicates the Errors tab in health.html | Remove to avoid confusion |

### 2.15 Help / Manual (`manual.html`)

**What works well:**
- Comprehensive documentation covering every page
- Table of contents with anchor links
- Custom `.manual` styles for readable typography
- Examples with badges rendered inline
- Well-organized with consistent heading hierarchy

**Issues:**

| Severity | Issue | Fix |
|----------|-------|-----|
| Minor | TOC links don't highlight the current section as you scroll | Add scroll-spy with `IntersectionObserver` |
| Minor | Documentation references "left panel" and "right sidebar" from old layout — doesn't match the new tabbed Customer Detail | Update documentation to reflect current tab structure |
| Minor | No search functionality within the manual | Add a Ctrl+F hint or in-page search |
| Polish | Hard-coded color values in inline styles (`style="color: var(--red);"`) | Use badge classes instead |

### 2.16 Partials

#### Activity Feed (`partials/activity_feed.html`)
- Clean and functional
- Empty state present
- **Minor:** Feed items use inline text truncation at 80 chars rather than CSS `text-overflow` — could break with multibyte characters

#### Messages Contacts (`partials/messages_contacts.html`)
- Excellent split-pane design
- Proper ARIA roles (`role="list"`, `role="listitem"`)
- Keyboard accessible (`tabindex="0"`, `onkeydown` handler)
- Empty state with icon and helpful description
- Channel badges differentiated by color
- **Minor:** `onclick` inline handler for active state — should use event delegation
- **Minor:** Loading indicator for thread is text-only "Loading conversation..." — should use skeleton

#### Messages Thread (`partials/messages_thread.html`)
- "Load earlier messages" pagination is implemented
- Delivery failure badges
- Tool calls expandable with input/output
- Message body overflow protection for very long messages
- **Minor:** Thread uses `aria-live="polite"` — appropriate for conversation updates
- **Minor:** AI badge shows "Cal/haiku" or "Cal/sonnet" — clever but might confuse non-technical operators

#### Knowledge Base (`partials/knowledge_base.html`)
- Grouped by source type with visual separation
- Expiration status badges (Active, Expiring Soon, Expired)
- Global settings row for default TTL and expiration policy
- Summary bar with counts
- Proper empty state
- **Minor:** "Set Expiration" inline date input + button is cluttered — could use a popover
- **Minor:** Re-index button has no loading state for what could be a slow operation

---

## 3. Cross-Cutting Issues

### 3.1 No Toast/Flash Notification System (Critical)

This is the single biggest UX gap. Every POST action (deactivate, test SMS, retry trigger, cancel trigger, fire now, change plan, cancel subscription, run scan, KB operations) redirects via 303 with **zero visual confirmation**. The user clicks a button and the page reloads looking identical. Did it work? Did it fail? Nobody knows.

**Recommendation:** Implement a flash message system using session cookies or query parameters. Display a `.toast` element that auto-dismisses after 5 seconds.

### 3.2 Inline Styles Epidemic (Major)

I counted 100+ instances of `style="..."` across templates. Examples:
- `style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;"`
- `style="font-size: 12px;"` (appears 15+ times)
- `style="color: var(--text-muted); text-align: center; padding: 2rem;"` (empty state pattern repeated 6 times)

**Recommendation:** Extract into utility classes:
```css
.flex-between { display: flex; justify-content: space-between; align-items: center; }
.mb-1 { margin-bottom: 1rem; }
.text-center-muted { color: var(--text-muted); text-align: center; padding: 2rem; }
.text-sm { font-size: 12px; }
.text-xs { font-size: 11px; }
```

### 3.3 No Pagination Framework (Major)

Every list page loads all data in one request. The backend has `limit` parameters but no page controls in the UI. This will break as the system scales.

**Recommendation:** Build a reusable pagination partial:
```html
<!-- partials/pagination.html -->
<nav class="pagination" aria-label="Page navigation">
    {% if page > 1 %}<a href="?page={{ page - 1 }}">Previous</a>{% endif %}
    <span>Page {{ page }}</span>
    {% if has_more %}<a href="?page={{ page + 1 }}">Next</a>{% endif %}
</nav>
```

### 3.4 Duplicated Tab Switching JavaScript (Minor)

The tab-switching JS is copy-pasted in `tenant_detail.html`, `billing.html`, and `health.html` — three slightly different implementations. `tenant_detail.html` has the most complete version (with keyboard nav and URL hash), while the others are simpler.

**Recommendation:** Extract to a shared `tabs.js` file included in `base.html`.

### 3.5 Jargon Inconsistency (Minor)

Despite the "Tenant to Customer" cleanup:
- `tenant_edit.html` line 10: "Agent Profile" section title
- `tenant_new.html` line 10: "Agent Profile" section title
- `onboard_wizard.html` line 478: "Create Agent Instance" button
- Backend URLs still use `/tenants/` path segment (acceptable as internal routing)
- Some template file names still use `tenant_` prefix (acceptable)

### 3.6 No Breadcrumb Navigation (Minor)

Deep pages (Customer Detail, Conversation Detail, Edit Customer) have no breadcrumbs. Users must rely on the sidebar or browser back button to navigate.

**Recommendation:** Add a breadcrumb component below the topbar:
```
Customers > Sarah Mitchell > Edit Settings
```

### 3.7 Unicode Icon Inconsistency (Minor)

The sidebar uses Unicode characters for icons: `⌂`, `♦`, `◬`, `↻`, `$`, `♥`, `⚙`, `?`, `←`. These render differently across operating systems and don't align to a consistent visual weight or style.

**Recommendation:** Replace with a lightweight SVG icon set (Lucide, Heroicons, or Phosphor) for consistent rendering.

---

## 4. Empty State Inventory

| Page/Section | Current Empty State | Quality | Recommendation |
|---|---|---|---|
| Dashboard Activity Feed | "No recent activity." | Minimal | Add icon + "When customers start messaging, their conversations will appear here." |
| Dashboard Needs Attention | "All clear." | OK | Add checkmark icon + "All systems running smoothly" |
| Customers Table | "No customers found." in table cell | Minimal | Full-page empty state with illustration + "Get started by onboarding your first agent" CTA |
| Customer Contacts Tab | "No contacts yet." | Adequate | Add "Contacts appear automatically when people text this agent's Twilio number." |
| Customer Listings Tab | "No listings yet." | Adequate | Add "Add listings from the Edit Settings page or the onboarding wizard." |
| Customer Automations Tab | "No scheduled automations." | Adequate | Add "The AI creates automations automatically (follow-ups, reminders, etc.)" |
| Customer Messages Tab | Full empty state with icon, title, description | Excellent | No changes needed |
| Customer KB Tab | Full empty state with icon, title, description | Excellent | No changes needed |
| Messages Thread (no contact selected) | Icon + "Select a contact to view their conversation" | Good | No changes needed |
| Conversations Table | "No conversations found." | Minimal | Add empty state matching the Messages tab pattern |
| Automations Table | "No automations found." | Minimal | Add "Automations are created by the AI when it schedules follow-ups, reminders, and briefings." |
| Health Errors | "No errors found." | Adequate | Add checkmark icon + "No errors in the last 24 hours" |
| Billing Subscriptions | Full text explaining Stripe | Adequate | No changes needed |
| Cost Chart | "No cost data yet." | Minimal | Add "Cost data appears after the first message is processed." |

---

## 5. Loading State Inventory

| HTMX Interaction | Current Loading State | Quality | Recommendation |
|---|---|---|---|
| Dashboard Activity Feed (load + every 15s) | "Loading..." text | Poor | Use `.loading-skeleton` (3 rows) |
| Health Status Dot (load + every 30s) | Yellow dot with "Loading..." title | OK | Adequate |
| Health auto-refresh (every 30s) | None — content swaps silently | Poor | Add subtle refresh indicator in topbar |
| Customer Messages Tab (intersect) | Skeleton loader (3 rows) | Good | No changes needed |
| Customer KB Tab (click) | Skeleton loader (3 rows) | Good | No changes needed |
| Customer Messages Thread (click contact) | "Loading conversation..." text indicator | OK | Use skeleton loader |
| Messages Refresh button | HTMX indicator with "Loading..." | OK | Could use a spinner icon |
| All form submissions | No loading state | Poor | Disable submit button + show spinner |

---

## 6. Error State Inventory

| Action | Can Fail? | Current Error Handling | Ideal |
|---|---|---|---|
| Login | Yes | `.alert-error` with message | Good as-is |
| Create Customer | Yes | `.alert-error` on same page with form preserved | Good |
| Edit Customer | Yes | `.alert-error` on same page | Good |
| Onboard Wizard Submit | Yes | `.alert-error` on wizard page BUT wizard state is lost | Preserve wizard state on error |
| Deactivate Customer | Yes (CSRF) | 403 plain text | Toast with error message |
| Test SMS | Yes | Silently caught, logged, redirect | Toast: "Test SMS sent!" or "Test SMS failed: [reason]" |
| Retry Trigger | Yes (CSRF) | 403 plain text | Toast with feedback |
| Cancel Trigger | Yes (CSRF) | 403 plain text | Toast with feedback |
| Fire Now Trigger | Yes (CSRF) | 403 plain text | Toast with feedback |
| Change Plan | Yes | Silently caught, logged, redirect | Toast: "Plan changed to [name]" or error |
| Cancel Subscription | Yes | Silently caught, logged, redirect | Toast with confirmation |
| Run Health Scan | Yes | Silently caught, logged, redirect | Toast: "Daily check started for [name]" |
| KB Add Document | Yes | 400/500 plain text Response | Inline error in the add form |
| KB Remove | Yes | Silently caught, logged, redirect | Toast: "Document removed" |
| KB Re-index | Yes | Silently caught, logged, redirect | Toast: "Re-indexing started" |
| KB Set Expiration | Yes | 400 plain text for invalid date | Inline error with client-side date validation |
| KB Save Settings | Yes | 400 for invalid | Inline error |

---

## 7. Polish Checklist (Prioritized)

### P0 — Ship Blockers (fix before any demo)

1. **Fix template filename mismatches** — `console.py` references `partials/tenant_messages_tab.html`, `partials/tenant_messages_thread.html`, `partials/tenant_kb_tab.html` but files are named `messages_contacts.html`, `messages_thread.html`, `knowledge_base.html`
2. **Verify KB "Add Document" form action URL** — template uses `/console/tenants/{{ agent.id }}/knowledge-base/add` but backend route is `/console/tenants/{agent_id}/kb/upload`
3. **Implement toast notification system** — every POST action needs user feedback

### P1 — High Impact (next sprint)

4. Add pagination to all table views (Customers, Conversations, Automations, Errors)
5. Add loading skeletons to Dashboard Activity Feed
6. Add success/error flash messages to all form submissions
7. Replace Unicode sidebar icons with SVG icon set
8. Fix jargon: "Agent Profile" -> "Customer Profile" in edit/new forms, "Create Agent Instance" -> "Create Customer"
9. Extract inline styles to CSS utility classes
10. Add "unsaved changes" warning to Edit Customer form

### P2 — Medium Impact (hardening phase)

11. Add sortable columns to Customers table
12. Add breadcrumb navigation to detail pages
13. Extract tab-switching JS to shared module
14. Add bar chart axis labels (Costs, Billing)
15. Improve empty states with icons and helpful descriptions
16. Add "back" navigation to Conversation Detail
17. Fix conversation detail tool execution interleaving logic
18. Add client-side form validation (phone E.164, required fields)
19. Format snake_case values to Title Case in tables (trigger types, etc.)
20. Remove dead templates (`costs.html`, `errors.html`)

### P3 — Polish (ongoing)

21. Add relative timestamps ("2 min ago") to activity feed
22. Make Dashboard pulse cards clickable (link to respective pages)
23. Add scroll-spy to Help page TOC
24. Add "show password" toggle to login
25. Improve Change Plan dropdown (use proper modal instead of `<details>`)
26. Add search/filter to Help page content
27. Pretty-print Raw Agent Record JSON
28. Add character counter to System Prompt Override textarea
29. Update Help page documentation to match current tabbed layout

---

## 8. Recommended Design Tokens

Based on what already exists in `style.css`, here is a proposed formalization:

### Colors (already defined, mostly good)

```css
:root {
    /* Backgrounds */
    --bg:          #121212;    /* Page background */
    --bg-card:     #181818;    /* Card/panel background */
    --bg-hover:    #282828;    /* Hover state background */

    /* Borders */
    --border:      #333333;    /* Default border */
    --border-focus: var(--accent);  /* NEW: Focus ring color */

    /* Text */
    --text:        #FFFFFF;    /* Primary text */
    --text-muted:  #B3B3B3;    /* Secondary text */
    --text-subdued: #A7A7A7;   /* Tertiary text */

    /* Semantic */
    --accent:      #1ED760;    /* Primary action / brand */
    --accent-hover: #1DB954;
    --green:       #1ED760;    /* Success */
    --yellow:      #FFA42B;    /* Warning */
    --red:         #E91429;    /* Error / danger */
    --blue:        #3B82F6;    /* NEW: Info (currently badge-blue uses green, which is confusing) */
}
```

**Issue flagged:** `badge-blue` currently uses green (`rgba(30,215,96,0.15)` with `color: var(--accent)` which is green). This is semantically wrong — "blue" badges appear green. Either rename to `badge-accent` or add an actual blue color.

### Spacing Scale

```css
:root {
    --space-xs:   0.25rem;   /* 4px */
    --space-sm:   0.5rem;    /* 8px */
    --space-md:   0.75rem;   /* 12px */
    --space-lg:   1rem;      /* 16px */
    --space-xl:   1.5rem;    /* 24px */
    --space-2xl:  2rem;      /* 32px */
}
```

### Typography Scale

```css
:root {
    /* Font sizes */
    --text-xs:    11px;   /* Meta, timestamps */
    --text-sm:    12px;   /* Labels, badges, hints */
    --text-base:  14px;   /* Body text, form inputs */
    --text-lg:    16px;   /* Section titles */
    --text-xl:    18px;   /* Page title (topbar) */
    --text-2xl:   20px;   /* Wizard step headers */
    --text-3xl:   24px;   /* Card values */
    --text-4xl:   28px;   /* Manual h1 */

    /* Font weights */
    --font-normal:   400;
    --font-medium:   500;
    --font-semibold: 600;
    --font-bold:     700;

    /* Line heights */
    --leading-tight:  1.25;
    --leading-normal: 1.5;
    --leading-relaxed: 1.7;   /* Manual content */
}
```

### Border Radii

```css
:root {
    --radius-sm:  4px;    /* Badges, small elements */
    --radius-md:  6px;    /* Buttons, inputs, nav items */
    --radius-lg:  8px;    /* Cards, panels, modals */
}
```

### Shadows

Currently no shadows are used. For consumer-grade polish, consider:

```css
:root {
    --shadow-sm:  0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-md:  0 4px 6px rgba(0, 0, 0, 0.3);
    --shadow-lg:  0 10px 15px rgba(0, 0, 0, 0.3);
}
```

Use sparingly: card hover states, dropdowns, modals, toasts.

### Transitions

```css
:root {
    --transition-fast:   0.15s ease;
    --transition-normal: 0.2s ease;
    --transition-slow:   0.3s ease;
}
```

---

## Appendix: File Reference

| File | Role |
|---|---|
| `app/templates/console/base.html` | Layout shell: sidebar, topbar, HTMX include |
| `app/templates/console/login.html` | Standalone login page |
| `app/templates/console/dashboard.html` | Home page with pulse cards + activity feed |
| `app/templates/console/tenants.html` | Customer list table |
| `app/templates/console/tenant_detail.html` | Customer detail with 6 tabs |
| `app/templates/console/tenant_edit.html` | Customer edit form |
| `app/templates/console/tenant_new.html` | New customer form |
| `app/templates/console/onboard_wizard.html` | 7-step onboarding wizard |
| `app/templates/console/onboard_success.html` | Post-onboarding success + checklist |
| `app/templates/console/conversations.html` | Conversations list |
| `app/templates/console/conversation_detail.html` | Conversation thread view |
| `app/templates/console/triggers.html` | Automations list |
| `app/templates/console/billing.html` | Billing: Subscriptions + AI Costs tabs |
| `app/templates/console/costs.html` | DEAD — redirects to billing |
| `app/templates/console/health.html` | System Health: 4 tabs |
| `app/templates/console/errors.html` | DEAD — redirects to health |
| `app/templates/console/manual.html` | Help / user manual |
| `app/templates/console/partials/activity_feed.html` | HTMX partial: activity feed |
| `app/templates/console/partials/messages_contacts.html` | HTMX partial: messages contact list |
| `app/templates/console/partials/messages_thread.html` | HTMX partial: conversation thread |
| `app/templates/console/partials/knowledge_base.html` | HTMX partial: KB items |
| `app/static/console/style.css` | All console CSS (1028 lines) |
| `app/api/console.py` | All console route handlers |
